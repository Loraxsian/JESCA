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

maintenance_bp = Blueprint('maintenance', __name__)


@maintenance_bp.route('/maintenance')
@login_required
@role_required('Admin', 'Administrator', 'Teknisi', 'Staff')
def maintenance():
    """Technician & Maintenance Operations Center."""
    today = date.today()
    threshold = today + timedelta(days=14)

    due_assets_raw = Asset.query.filter(
        Asset.needs_maintenance == True,
        Asset.next_maintenance_date != None,
        Asset.next_maintenance_date <= threshold,
        Asset.status.notin_(['Dalam Perbaikan', 'Afkir'])
    ).order_by(Asset.next_maintenance_date.asc()).all()

    due_assets = [
        a for a in due_assets_raw
        if not (a.last_maintenance_date and a.last_maintenance_date >= today and a.next_maintenance_date > today)
    ]

    in_repair_assets = Asset.query.filter_by(status='Dalam Perbaikan').order_by(Asset.updated_at.desc()).all()
    records = MaintenanceRecord.query.order_by(MaintenanceRecord.service_date.desc(), MaintenanceRecord.id.desc()).all()
    total_records_count = len(records)
    total_maintenance_cost = sum(r.cost or 0.0 for r in records)

    return render_template(
        'maintenance.html',
        due_assets=due_assets,
        in_repair_assets=in_repair_assets,
        records=records,
        total_records_count=total_records_count,
        total_maintenance_cost=total_maintenance_cost,
        date_today=today
    )


@maintenance_bp.route('/assets/<int:asset_id>/maintenance/start', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator', 'Teknisi')
def start_maintenance(asset_id):
    """Technician marks an asset as currently undergoing repair/servicing."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('maintenance.maintenance'))

    old_status = asset.status
    asset.status = 'Dalam Perbaikan'
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal memulai servis aset ID {asset_id}: {e}")
        flash('Terjadi kendala saat mengubah status servis. Silakan coba kembali.', 'danger')
        return redirect(url_for('maintenance.maintenance'))

    log_activity(
        'MULAI_SERVIS',
        asset_code=asset.asset_code,
        asset_name=asset.name,
        details=f"Pengerjaan pemeliharaan dimulai oleh Teknisi {current_user.username}. Status diubah dari '{old_status}' menjadi 'Dalam Perbaikan'."
    )

    flash(f'Aset [{asset.asset_code}] resmi ditandai "Dalam Perbaikan" oleh Teknisi {current_user.username}.', 'info')
    return redirect(url_for('maintenance.maintenance'))


@maintenance_bp.route('/assets/<int:asset_id>/maintenance/complete', methods=['POST'])
@maintenance_bp.route('/assets/<int:asset_id>/complete-maintenance', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator', 'Teknisi')
def complete_maintenance(asset_id):
    """Complete maintenance service, record invoice/proof, reset interval."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('maintenance.maintenance'))

    service_type = request.form.get('service_type', 'Rutin').strip()
    action_taken = request.form.get('action_taken', '').strip() or request.form.get('notes', '').strip() or 'Pemeliharaan rutin selesai dilakukan.'
    cost = parse_currency(request.form.get('cost', '0'))
    s_date_str = request.form.get('service_date', '').strip()

    try:
        service_date = datetime.strptime(s_date_str, '%Y-%m-%d').date() if s_date_str else date.today()
    except Exception:
        service_date = date.today()

    interval_str = request.form.get('interval_days', '').strip()
    try:
        interval = int(interval_str) if interval_str else (asset.maintenance_interval_days or 90)
    except Exception:
        interval = asset.maintenance_interval_days or 90

    # Handle proof file upload
    proof_file = request.files.get('proof_file')
    proof_filename = save_maint_attachment(proof_file) if proof_file else None

    # Create permanent MaintenanceRecord
    rec = MaintenanceRecord(
        asset_id=asset.id,
        service_type=service_type,
        action_taken=action_taken,
        cost=cost,
        proof_file=proof_filename,
        performed_by=current_user.username,
        service_date=service_date,
        next_service_date=service_date + timedelta(days=interval)
    )
    db.session.add(rec)

    # Update asset state
    asset.status = 'Aktif'
    asset.last_maintenance_date = service_date
    asset.maintenance_interval_days = interval
    asset.next_maintenance_date = service_date + timedelta(days=interval)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal menyelesaikan servis aset ID {asset_id}: {e}")
        flash('Terjadi kendala saat menyimpan data servis ke database. Silakan coba kembali.', 'danger')
        return redirect(url_for('maintenance.maintenance'))

    log_activity(
        'MAINTENANCE_SELESAI',
        asset_code=asset.asset_code,
        asset_name=asset.name,
        details=f"Pemeliharaan [{service_type}] selesai dikerjakan oleh {current_user.username}. Biaya: Rp {cost:,.0f}. Jadwal berikutnya: {asset.next_maintenance_date.strftime('%d/%m/%Y')}."
    )

    flash(f'Pemeliharaan untuk [{asset.asset_code}] berhasil disimpan & jadwal servis berikutnya diperbarui ({asset.next_maintenance_date.strftime("%d/%m/%Y")})!', 'success')
    return redirect(request.referrer or url_for('maintenance.maintenance'))


@maintenance_bp.route('/assets/<int:asset_id>/report-issue', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator', 'Teknisi', 'Staff')
def report_asset_issue(asset_id):
    """Staff or other users report an issue/breakdown of an asset directly to technicians & admin."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('maintenance.maintenance'))

    issue_desc = request.form.get('issue_description', '').strip()
    if not issue_desc:
        flash('Deskripsi kendala wajib diisi.', 'danger')
        return redirect(url_for('maintenance.maintenance'))

    fb = SystemFeedback(
        sender_name=current_user.full_name or current_user.username,
        contact=f"User: {current_user.username} ({current_user.role})",
        category='Laporan Kendala Aset',
        message=f"Kendala pada aset [{asset.asset_code}] {asset.name}: {issue_desc}",
        status='Pending',
        created_at=datetime.utcnow()
    )
    db.session.add(fb)
    db.session.commit()

    log_activity(
        'LAPOR_KENDALA',
        asset_code=asset.asset_code,
        asset_name=asset.name,
        details=f"Kendala dilaporkan oleh {current_user.username}: {issue_desc}"
    )

    flash(f'Kendala untuk aset [{asset.asset_code}] berhasil dilaporkan ke Teknisi & Admin.', 'success')
    return redirect(request.referrer or url_for('maintenance.maintenance'))


