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
from services.tunnel_service import start_quick_tunnel, stop_quick_tunnel, _QUICK_TUNNEL_INFO, _QUICK_TUNNEL_PROC

api_bp = Blueprint('api', __name__)


@api_bp.route('/api/assets/<int:asset_id>/circulation')
@login_required
def api_asset_circulation(asset_id):
    """Return past borrow/circulation history for an asset."""
    logs = AssetCirculationLog.query.filter_by(asset_id=asset_id)\
        .order_by(AssetCirculationLog.borrow_date.desc()).all()
    data = []
    for l in logs:
        data.append({
            'id': l.id,
            'borrower': l.borrower,
            'borrow_date': l.borrow_date.strftime('%d/%m/%Y %H:%M') if l.borrow_date else '-',
            'return_date': l.return_date.strftime('%d/%m/%Y %H:%M') if l.return_date else None,
            'duration_days': l.duration_days or 0,
            'notes': l.notes or '',
            'checkout_by': l.checkout_by or '-',
            'checkin_by': l.checkin_by or '-'
        })
    return jsonify({'status': 'success', 'data': data})


@api_bp.route('/api/assets/<int:asset_id>/attachments', methods=['GET'])
@login_required
def api_asset_attachments(asset_id):
    """AJAX endpoint listing all attachments for an asset."""
    attachments = AssetAttachment.query.filter_by(asset_id=asset_id).order_by(AssetAttachment.uploaded_at.desc()).all()
    return jsonify({
        'status': 'success',
        'data': [{
            'id': a.id,
            'original_name': a.original_name,
            'file_type': a.file_type,
            'file_size': a.file_size,
            'uploaded_by': a.uploaded_by,
            'uploaded_at': a.uploaded_at.strftime('%Y-%m-%d %H:%M'),
            'download_url': url_for('assets.download_attachment', asset_id=asset_id, att_id=a.id)
        } for a in attachments]
    })


@api_bp.route('/api/vendors', methods=['GET'])
@login_required
def api_vendors():
    v_list = Vendor.query.filter_by(is_active=True).order_by(Vendor.name.asc()).all()
    return jsonify({'status': 'success', 'data': [v.to_dict() for v in v_list]})


@api_bp.route('/api/sites', methods=['GET'])
@login_required
def api_sites():
    s_list = Site.query.filter_by(is_active=True).order_by(Site.name.asc()).all()
    return jsonify({'status': 'success', 'data': [s.to_dict() for s in s_list]})


@api_bp.route('/api/assets/<int:asset_id>/qrcode')
def api_asset_qrcode(asset_id):
    """Generate QR Code image pointing directly to the asset's scan summary URL."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        return jsonify({'error': 'Not found'}), 404

    setting = SystemSetting.query.get(1)
    if setting and setting.app_base_url:
        scan_url = f"{setting.app_base_url.rstrip('/')}{url_for('main.scan_asset_summary', asset_code=asset.asset_code)}"
    else:
        scan_url = url_for('main.scan_asset_summary', asset_code=asset.asset_code, _external=True)

    if HAVE_QRCODE:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(scan_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return Response(buf.getvalue(), mimetype='image/png')
    else:
        api_url = f"https://quickchart.io/qr?text={quote(scan_url)}&size=250&margin=2"
        return redirect(api_url)


@api_bp.route('/api/generate-code', methods=['GET'])
@login_required
def api_generate_code():
    category = request.args.get('category', 'Tech').strip()
    code = generate_asset_code(category)
    prefix = get_category_prefix(category)
    return jsonify({
        'status': 'success',
        'category': category,
        'prefix': prefix,
        'code': code
    })


@api_bp.route('/api/assets/<int:asset_id>', methods=['GET'])
@login_required
def api_get_asset(asset_id):
    asset = db.session.get(Asset, asset_id)
    if not asset:
        return jsonify({'status': 'error', 'message': 'Asset not found'}), 404
    return jsonify({'status': 'success', 'data': asset.to_dict()})


@api_bp.route('/api/assets/warranty-alerts', methods=['GET'])
@login_required
def api_warranty_alerts():
    today = date.today()
    threshold = today + timedelta(days=30)
    alerts = Asset.query.filter(
        Asset.warranty_end != None,
        Asset.warranty_end <= threshold
    ).order_by(Asset.warranty_end.asc()).all()
    return jsonify({
        'status': 'success',
        'count': len(alerts),
        'data': [a.to_dict() for a in alerts]
    })


@api_bp.route('/api/assets/cache-summary', methods=['GET'])
@login_required
def api_assets_cache_summary():
    """Lightweight asset summary list for offline browser caching (IndexedDB)."""
    try:
        assets = Asset.query.with_entities(
            Asset.id, Asset.asset_code, Asset.name, Asset.category, Asset.location, Asset.status
        ).order_by(Asset.asset_code.asc()).all()
        data = [
            {
                'id': a[0],
                'code': a[1],
                'name': a[2],
                'category': a[3],
                'location': a[4] or 'Kantor Pusat',
                'status': a[5] or 'Aktif'
            } for a in assets
        ]
        return jsonify({'status': 'success', 'count': len(data), 'data': data})
    except Exception as e:
        current_app.logger.error(f"Error fetching assets cache summary: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@api_bp.route('/api/stock-opname/sync', methods=['POST'])
@login_required
def api_stock_opname_sync():
    """Receives single or batch stock opname verification records (online or synced from offline cache)."""
    payload = request.get_json(silent=True) or {}
    items = payload.get('items', [])
    if not items and 'asset_code' in payload:
        items = [payload]

    if not items:
        return jsonify({'status': 'error', 'message': 'Tidak ada data opname yang dikirim.'}), 400

    synced_records = []

    for item in items:
        code = str(item.get('asset_code', '')).strip()
        if not code:
            continue
        condition = str(item.get('physical_condition', 'Sesuai & Baik')).strip()
        notes = str(item.get('notes', '')).strip()
        location_checked = str(item.get('location_checked', '')).strip()
        is_offline = bool(item.get('is_offline', True))
        scanned_at_str = item.get('scanned_at')

        try:
            scanned_at = datetime.fromisoformat(scanned_at_str) if scanned_at_str else datetime.utcnow()
        except Exception:
            scanned_at = datetime.utcnow()

        asset = Asset.query.filter_by(asset_code=code).first()

        rec = StockOpnameRecord(
            asset_id=asset.id if asset else None,
            asset_code=code,
            asset_name=asset.name if asset else item.get('asset_name', 'Tidak Terdaftar'),
            physical_condition=condition,
            location_checked=location_checked or (asset.location if asset else None),
            notes=notes,
            verified_by=current_user.username,
            is_offline_sync=is_offline,
            scanned_at=scanned_at,
            synced_at=datetime.utcnow()
        )
        db.session.add(rec)
        synced_records.append(code)

    try:
        db.session.commit()
        if synced_records:
            log_activity(
                'STOK_OPNAME',
                details=f"Verifikasi stok opname {len(synced_records)} unit ({', '.join(synced_records[:5])}{'...' if len(synced_records)>5 else ''}) oleh {current_user.username}."
            )
        return jsonify({
            'status': 'success',
            'synced_count': len(synced_records),
            'synced_codes': synced_records
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error syncing stock opname: {e}")
        return jsonify({'status': 'error', 'message': f'Gagal menyimpan ke database: {e}'}), 500


@api_bp.route('/api/v1/assets', methods=['GET'])
@api_key_required
def api_v1_assets():
    """REST API endpoint returning all assets as JSON."""
    all_a = Asset.query.order_by(Asset.asset_code.asc()).all()
    return jsonify({
        'status': 'success',
        'count': len(all_a),
        'data': [a.to_dict() for a in all_a]
    })


@api_bp.route('/api/v1/assets/<asset_code>', methods=['GET'])
@api_key_required
def api_v1_asset_detail(asset_code):
    """REST API endpoint returning single asset details."""
    asset = Asset.query.filter_by(asset_code=asset_code).first()
    if not asset:
        return jsonify({'status': 'error', 'message': f'Asset with code {asset_code} not found'}), 404
    return jsonify({'status': 'success', 'data': asset.to_dict()})


