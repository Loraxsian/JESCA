import os
import re
import csv
import io
import json
import uuid
import shutil
import secrets
import smtplib
import socket
import subprocess
import traceback
from datetime import datetime, date, timedelta
from urllib.parse import quote

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, Response, send_from_directory, session, current_app
)
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename

from config import (
    APP_VERSION, GITHUB_REPO, BASE_DIR, DATA_DIR, UPLOAD_FOLDER, AVATAR_FOLDER,
    ATTACHMENT_FOLDER, PO_ATTACHMENT_FOLDER, MAINT_ATTACHMENT_FOLDER,
    BACKUP_FOLDER, QRCODE_FOLDER, ALLOWED_EXTENSIONS, ALLOWED_ATTACHMENT_EXTENSIONS,
    CATEGORY_CUSTOM_FIELDS, CATEGORY_PREFIX_MAP, DEFAULT_CATEGORIES,
    STATUS_CHOICES, ROLE_CHOICES, db_path
)
from extensions import (
    db, HAVE_QRCODE, qrcode, HAVE_REPORTLAB, rl_colors, A4, landscape,
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, getSampleStyleSheet
)
from i18n import get_current_lang, translate as i18n_translate, SUPPORTED_LANGUAGES
from models import (
    SystemSetting, Site, Vendor, User, Asset, ActivityLog, AssetAttachment,
    AssetTransfer, PurchaseOrder, POItem, PurchaseOrderHistory,
    MaintenanceRecord, AssetCirculationLog, SystemFeedback, StockOpnameRecord
)
from utils.decorators import admin_required, role_required, api_key_required, is_sudo_active, sudo_required
from utils.helpers import (
    validate_password, allowed_file, allowed_attachment,
    save_uploaded_photo, delete_photo_file, save_po_attachment, save_maint_attachment,
    save_avatar_file, delete_avatar_file, encrypt_smtp_password, decrypt_smtp_password,
    get_wib_now, format_wib_datetime, parse_currency, get_category_prefix,
    generate_asset_code, generate_po_number
)
from services.audit_service import log_activity, log_po_history, get_overdue_returns, get_maintenance_notifications
from services.email_service import build_system_email_html, send_system_email
from services.backup_service import upload_to_remote_backup
from services.tunnel_service import start_quick_tunnel, stop_quick_tunnel, get_quick_tunnel_status

main_bp = Blueprint('main', __name__)


@main_bp.route('/robots.txt')
def robots():
    """Prevent web crawlers from indexing internal inventory data."""
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


@main_bp.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'version': APP_VERSION,
        'release_stage': 'Stable Version',
        'app': 'JESCA Asset Management System',
        'timestamp': datetime.utcnow().isoformat()
    })


@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))


@main_bp.route('/set-lang/<lang>')
def set_language(lang):
    """Simpan preferensi bahasa (ID / EN) di session & cookie via Python."""
    chosen = lang.lower().strip()
    if chosen not in SUPPORTED_LANGUAGES:
        chosen = 'id'
    session['jesca_lang'] = chosen
    next_url = request.referrer or url_for('main.dashboard')
    resp = redirect(next_url)
    resp.set_cookie('jesca_lang', chosen, max_age=365 * 24 * 3600, samesite='Lax')
    return resp


@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Dashboard view with statistics, charts, depreciation, underutilization, and alerts."""
    all_assets = Asset.query.all()
    total_assets = len(all_assets)
    total_value = sum(a.purchase_price or 0.0 for a in all_assets)
    total_book_value = sum(a.current_book_value for a in all_assets)

    # Status counts
    active_count = sum(1 for a in all_assets if a.status == 'Aktif')
    borrowed_count = sum(1 for a in all_assets if a.status == 'Dipinjam')
    maintenance_count = sum(1 for a in all_assets if a.status == 'Dalam Perbaikan')
    broken_count = sum(1 for a in all_assets if a.status == 'Rusak')
    retired_count = sum(1 for a in all_assets if a.status == 'Afkir')
    attention_count = maintenance_count + broken_count

    # Category breakdown for Chart.js
    category_query = db.session.query(
        Asset.category,
        db.func.count(Asset.id).label('total_count'),
        db.func.sum(Asset.purchase_price).label('total_val')
    ).group_by(Asset.category).all()

    category_labels = [row[0] for row in category_query]
    category_counts = [int(row[1]) for row in category_query]
    category_values = [float(row[2] or 0) for row in category_query]

    # Status breakdown
    status_labels = STATUS_CHOICES
    status_counts = [sum(1 for a in all_assets if a.status == st) for st in status_labels]

    # Underutilized assets: owned > 90 days but checkout time < 10%
    underutilized = []
    today = date.today()
    for a in all_assets:
        if a.status == 'Aktif' and a.purchase_date:
            days_owned = (today - a.purchase_date).days
            if days_owned > 90:
                util_pct = ((a.total_checkout_days or 0) / days_owned) * 100
                if util_pct < 10.0:
                    underutilized.append({
                        'asset': a,
                        'utilization_pct': round(util_pct, 1),
                        'days_owned': days_owned
                    })

    # Overdue returns
    overdue_returns = get_overdue_returns()

    # Recent items (scrollable list) with privacy-aware role filtering
    recent_assets = Asset.query.order_by(Asset.created_at.desc(), Asset.id.desc()).limit(20).all()
    if current_user.role == 'Staff':
        recent_logs = ActivityLog.query.filter_by(username=current_user.username)\
            .order_by(ActivityLog.created_at.desc()).limit(25).all()
    elif current_user.role == 'Teknisi':
        recent_logs = ActivityLog.query.filter(
            (ActivityLog.action.like('%MAINTENANCE%')) | 
            (ActivityLog.username == current_user.username)
        ).order_by(ActivityLog.created_at.desc()).limit(25).all()
    else:
        recent_logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(25).all()
    active_percentage = round((active_count / total_assets * 100), 1) if total_assets > 0 else 0
    maintenance_alerts = get_maintenance_notifications()

    return render_template(
        'dashboard.html',
        total_assets=total_assets,
        total_value=total_value,
        total_book_value=total_book_value,
        active_count=active_count,
        borrowed_count=borrowed_count,
        attention_count=attention_count,
        active_percentage=active_percentage,
        category_query=category_query,
        category_labels=category_labels,
        category_counts=category_counts,
        category_values=category_values,
        status_labels=status_labels,
        status_counts=status_counts,
        recent_assets=recent_assets,
        recent_logs=recent_logs,
        maintenance_alerts=maintenance_alerts,
        underutilized=underutilized,
        overdue_returns=overdue_returns,
        categories=DEFAULT_CATEGORIES,
        statuses=STATUS_CHOICES,
        is_default_admin_password=bool(current_user.role == 'Admin' and current_user.check_password('Admin123')),
        pending_pos=PurchaseOrder.query.filter_by(status='SUBMITTED').order_by(PurchaseOrder.created_at.desc()).all() if current_user.role in ['Admin', 'Administrator'] else []
    )


@main_bp.route('/submit-feedback', methods=['POST'])
@main_bp.route('/api/public/feedback', methods=['POST'])
def submit_public_feedback():
    """Receives feedback, suggestions, and bug reports from the public login modal or authenticated users."""
    sender_name = request.form.get('name', '').strip() or (request.json.get('name', '').strip() if request.is_json else '')
    contact = request.form.get('contact', '').strip() or (request.json.get('contact', '').strip() if request.is_json else '')
    category = request.form.get('category', 'Saran Fitur Baru').strip() or (request.json.get('category', 'Saran Fitur Baru').strip() if request.is_json else '')
    message = request.form.get('message', '').strip() or (request.json.get('message', '').strip() if request.is_json else '')

    if not message:
        return jsonify({'status': 'error', 'message': 'Pesan masukan atau laporan wajib diisi.'}), 400

    try:
        fb = SystemFeedback(
            sender_name=sender_name or 'Anonim',
            contact=contact or '-',
            category=category or 'Saran Fitur Baru',
            message=message,
            status='Pending',
            created_at=datetime.utcnow()
        )
        db.session.add(fb)
        db.session.commit()

        log_activity(
            'FEEDBACK_MASUK',
            details=f"Pesan/laporan publik diterima [{category}] dari {sender_name or 'Anonim'}: {message[:60]}"
        )

        return jsonify({'status': 'ok', 'message': 'Masukan atau laporan berhasil dikirim. Terima kasih atas partisipasi Anda!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'Gagal menyimpan data: {str(e)}'}), 500


@main_bp.route('/feedback/<int:feedback_id>/resolve', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator', 'Teknisi')
def resolve_feedback(feedback_id):
    """Mark a feedback / bug report as resolved."""
    fb = db.session.get(SystemFeedback, feedback_id)
    if not fb:
        flash('Laporan tidak ditemukan.', 'danger')
        return redirect(request.referrer or url_for('main.dashboard'))

    fb.status = 'Resolved'
    fb.resolved_by = current_user.username
    fb.resolved_at = datetime.utcnow()
    fb.resolution_notes = request.form.get('notes', 'Ditandai selesai via notifikasi.')
    db.session.commit()

    log_activity(
        'RESOLVE_FEEDBACK',
        details=f"Laporan #{fb.id} [{fb.category}] ditandai selesai oleh {current_user.username}."
    )

    flash(f'Laporan #{fb.id} ({fb.category}) berhasil ditandai selesai.', 'success')
    return redirect(request.referrer or url_for('main.feedbacks_list'))


@main_bp.route('/feedbacks')
@login_required
@role_required('Admin', 'Administrator', 'Teknisi')
def feedbacks_list():
    """Feedback & Bug Report Helpdesk Center for Admin and Technicians."""
    category_filter = request.args.get('category', '').strip()
    status_filter = request.args.get('status', 'Pending').strip()
    search_query = request.args.get('search', '').strip()

    query = SystemFeedback.query

    if status_filter and status_filter != 'all':
        query = query.filter_by(status=status_filter)

    if category_filter:
        query = query.filter_by(category=category_filter)

    if search_query:
        query = query.filter(
            db.or_(
                SystemFeedback.message.ilike(f"%{search_query}%"),
                SystemFeedback.sender_name.ilike(f"%{search_query}%"),
                SystemFeedback.contact.ilike(f"%{search_query}%"),
                SystemFeedback.category.ilike(f"%{search_query}%")
            )
        )

    feedbacks = query.order_by(SystemFeedback.created_at.desc()).all()

    total_count = SystemFeedback.query.count()
    pending_count = SystemFeedback.query.filter_by(status='Pending').count()
    resolved_count = SystemFeedback.query.filter_by(status='Resolved').count()

    categories = [
        'Laporan Bug / Eror',
        'Laporan Kendala Aset',
        'Kendala Login / Akun',
        'Saran Fitur Baru',
        'Pertanyaan Inventaris'
    ]

    return render_template(
        'feedbacks.html',
        feedbacks=feedbacks,
        current_status=status_filter,
        current_category=category_filter,
        search_query=search_query,
        total_count=total_count,
        pending_count=pending_count,
        resolved_count=resolved_count,
        categories=categories
    )


@main_bp.route('/feedback/<int:feedback_id>/delete', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator')
def delete_feedback(feedback_id):
    """Admin removes a feedback record."""
    fb = db.session.get(SystemFeedback, feedback_id)
    if fb:
        log_activity('HAPUS_FEEDBACK', details=f"Laporan #{fb.id} ({fb.category}) dihapus oleh {current_user.username}")
        db.session.delete(fb)
        db.session.commit()
        flash(f'Laporan #{feedback_id} berhasil dihapus.', 'info')
    return redirect(request.referrer or url_for('main.feedbacks_list'))


@main_bp.route('/scan/<path:asset_code>')
def scan_asset_summary(asset_code):
    """Public Asset Summary Page with sanitized, public-safe data only."""
    asset = Asset.query.filter_by(asset_code=asset_code).first()
    today = date.today()
    days_to_maint = None
    is_overdue = False

    if asset and asset.needs_maintenance and asset.next_maintenance_date:
        days_to_maint = (asset.next_maintenance_date - today).days
        is_overdue = days_to_maint < 0

    return render_template(
        'scan_summary.html',
        asset=asset,
        asset_code=asset_code,
        days_to_maint=days_to_maint,
        is_overdue=is_overdue,
        today=today,
        public_only=True
    )


