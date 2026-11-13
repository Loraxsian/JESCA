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
    generate_asset_code, generate_po_number, get_client_ip, is_ip_allowed
)
from services.audit_service import log_activity, log_po_history, get_overdue_returns, get_maintenance_notifications
from services.email_service import build_system_email_html, send_system_email
from services.backup_service import upload_to_remote_backup
from services.tunnel_service import start_quick_tunnel, stop_quick_tunnel, _QUICK_TUNNEL_INFO, _QUICK_TUNNEL_PROC

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/history')
@login_required
@role_required('Admin')
def history():
    action_filter = request.args.get('action', '').strip()
    search_query = request.args.get('search', '').strip()

    query = ActivityLog.query
    if action_filter:
        query = query.filter(ActivityLog.action == action_filter)

    if search_query:
        search_fmt = f"%{search_query}%"
        query = query.filter(
            db.or_(
                ActivityLog.username.ilike(search_fmt),
                ActivityLog.asset_code.ilike(search_fmt),
                ActivityLog.asset_name.ilike(search_fmt),
                ActivityLog.details.ilike(search_fmt)
            )
        )

    logs = query.order_by(ActivityLog.created_at.desc()).limit(200).all()

    distinct_actions = [
        'TAMBAH_ASET', 'EDIT_ASET', 'HAPUS_ASET', 'TRANSFER_ASET',
        'CHECK_OUT', 'CHECK_IN', 'MAINTENANCE_SELESAI', 'UPLOAD_LAMPIRAN',
        'IMPORT_CSV', 'EXPORT_CSV', 'EXPORT_PDF', 'BULK_DELETE', 'BULK_STATUS', 'BULK_CATEGORY',
        'BACKUP', 'RESTORE', 'LOGIN', 'LOGOUT', 'GANTI_PASSWORD',
        'TAMBAH_USER', 'EDIT_USER', 'RESET_PASSWORD_USER', 'HAPUS_USER', 'GENERATE_API_KEY'
    ]

    return render_template(
        'history.html',
        logs=logs,
        action_filter=action_filter,
        search_query=search_query,
        distinct_actions=distinct_actions
    )


@admin_bp.route('/history/clear', methods=['POST'])
@login_required
@admin_required
def clear_history():
    """Clear activity logs with self-auditing entry preserved."""
    count = ActivityLog.query.count()

    # Log entry created FIRST, delete old, then save the clearance log
    clear_entry = ActivityLog(
        user_id=current_user.id,
        username=current_user.username,
        action='CLEAR_LOGS',
        details=f"Pembersihan riwayat: {count} entri log dibersihkan oleh {current_user.username}.",
        created_at=datetime.utcnow()
    )

    ActivityLog.query.delete()
    db.session.add(clear_entry)
    db.session.commit()

    flash(f'Seluruh riwayat aktivitas ({count} entri) telah dibersihkan. Aksi pembersihan ini telah dicatat.', 'info')
    return redirect(url_for('admin.history'))


@admin_bp.route('/reports/audit')
@login_required
@role_required('Admin', 'Auditor')
def audit_report():
    """Audit-ready report with period filters & CSV export."""
    from_date_str = request.args.get('from', '').strip()
    to_date_str = request.args.get('to', '').strip()
    export_format = request.args.get('format', 'html').strip()

    query = ActivityLog.query
    if from_date_str:
        try:
            from_d = datetime.strptime(from_date_str, '%Y-%m-%d')
            query = query.filter(ActivityLog.created_at >= from_d)
        except ValueError:
            pass

    if to_date_str:
        try:
            to_d = datetime.strptime(to_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(ActivityLog.created_at <= to_d)
        except ValueError:
            pass

    logs = query.order_by(ActivityLog.created_at.desc()).all()

    if export_format == 'csv':
        output = io.StringIO()
        output.write('\ufeff')
        writer = csv.writer(output, delimiter=';')
        writer.writerow(['Waktu', 'Username', 'Aksi', 'Kode Aset', 'Nama Aset', 'Detail Perubahan'])
        for l in logs:
            writer.writerow([
                l.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                l.username,
                l.action,
                l.asset_code or '-',
                l.asset_name or '-',
                l.details or '-'
            ])
        filename = f"jesca_audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    return render_template(
        'audit_report.html',
        logs=logs,
        from_date=from_date_str,
        to_date=to_date_str
    )


@admin_bp.route('/admin/backups')
@login_required
@admin_required
def admin_backups():
    """Backup & Restore management dashboard for Administrator."""
    backup_files = []
    if os.path.exists(BACKUP_FOLDER):
        for f in sorted(os.listdir(BACKUP_FOLDER), reverse=True):
            if f.endswith('.db'):
                fp = os.path.join(BACKUP_FOLDER, f)
                backup_files.append({
                    'name': f,
                    'size': os.path.getsize(fp),
                    'created': datetime.fromtimestamp(os.path.getctime(fp))
                })
    show_modal = session.pop('show_import_modal', False)
    import_report = session.get('import_report')
    setting = SystemSetting.get_settings()
    return render_template(
        'admin_backups.html',
        backups=backup_files,
        import_report=import_report,
        show_import_modal=show_modal,
        setting=setting
    )


@admin_bp.route('/admin/backup', methods=['POST'])
@login_required
@admin_required
def manual_backup():
    """Create manual snapshot backup of SQLite database with optional remote copy."""
    filename = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    dst = os.path.join(BACKUP_FOLDER, filename)
    shutil.copy2(db_path, dst)

    remote_msg = ""
    setting = SystemSetting.get_settings()
    if setting.remote_backup_enabled and setting.remote_backup_host:
        ok, r_info = upload_to_remote_backup(dst, setting)
        remote_msg = f" Salinan remote: {r_info}."

    log_activity('BACKUP', details=f"Manual backup database dibuat: {filename}.{remote_msg}")
    flash(f'Backup database berhasil dibuat: {filename}.{remote_msg}', 'success')
    return redirect(url_for('admin.admin_backups'))


@admin_bp.route('/admin/backup-remote/config', methods=['POST'])
@login_required
@admin_required
@sudo_required
def save_remote_backup_config():
    """Save remote backup configuration (FTP/SFTP) from Backup & Restore page."""
    setting = SystemSetting.get_settings()
    setting.remote_backup_enabled = (request.form.get('remote_backup_enabled') == '1')
    setting.remote_backup_protocol = request.form.get('remote_backup_protocol', 'ftp').strip().lower()
    setting.remote_backup_host = request.form.get('remote_backup_host', '').strip()

    port_str = request.form.get('remote_backup_port', '').strip()
    default_port = 22 if setting.remote_backup_protocol == 'sftp' else 21
    setting.remote_backup_port = int(port_str) if port_str.isdigit() else default_port

    setting.remote_backup_user = request.form.get('remote_backup_user', '').strip()
    new_pass = request.form.get('remote_backup_pass', '').strip()
    if new_pass:
        setting.remote_backup_pass = new_pass

    path_val = request.form.get('remote_backup_path', '').strip() or '/'
    setting.remote_backup_path = path_val

    db.session.commit()
    log_activity(
        'CONFIG_REMOTE_BACKUP',
        details=f"Pengaturan remote backup diperbarui: {setting.remote_backup_protocol.upper()} ke {setting.remote_backup_host} (Aktif: {setting.remote_backup_enabled})"
    )
    flash('Pengaturan remote backup berhasil disimpan.', 'success')
    return redirect(url_for('admin.admin_backups'))


@admin_bp.route('/admin/backup-remote/test', methods=['POST'])
@login_required
@admin_required
@sudo_required
def test_remote_backup_connection():
    """AJAX test connection to FTP/SFTP remote backup destination."""
    protocol = request.form.get('protocol', 'ftp').strip().lower()
    host = request.form.get('host', '').strip()
    port_str = request.form.get('port', '').strip()
    default_port = 22 if protocol == 'sftp' else 21
    port = int(port_str) if port_str.isdigit() else default_port
    user = request.form.get('user', '').strip()
    password = request.form.get('password', '').strip()

    if not password:
        setting = SystemSetting.get_settings()
        password = setting.remote_backup_pass or ''

    if not host:
        return jsonify({'status': 'error', 'message': 'Host / IP server tujuan wajib diisi.'}), 400

    try:
        if protocol == 'ftp':
            import ftplib
            ftp = ftplib.FTP()
            ftp.connect(host, port, timeout=10)
            ftp.login(user, password)
            welcome = ftp.getwelcome()
            ftp.quit()
            return jsonify({'status': 'ok', 'message': f'Koneksi FTP berhasil terhubung ke {host}:{port}! Server: {welcome[:50]}'})
        elif protocol == 'sftp':
            try:
                import paramiko
            except ImportError:
                return jsonify({'status': 'error', 'message': "Modul SFTP (paramiko) belum terpasang. Gunakan protokol FTP."}), 400
            transport = paramiko.Transport((host, port))
            transport.connect(username=user, password=password)
            transport.close()
            return jsonify({'status': 'ok', 'message': f'Koneksi SFTP berhasil terhubung ke {host}:{port}!'})
        else:
            return jsonify({'status': 'error', 'message': f'Protokol {protocol} tidak didukung.'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Uji koneksi gagal: {str(e)}'}), 400


@admin_bp.route('/admin/restore/<filename>', methods=['POST'])
@login_required
@admin_required
def restore_backup(filename):
    """Restore SQLite database from backup file with safety snapshot."""
    safe_name = secure_filename(filename)
    src = os.path.join(BACKUP_FOLDER, safe_name)

    if not os.path.exists(src) or not safe_name.endswith('.db'):
        flash('File backup tidak ditemukan atau tidak valid.', 'danger')
        return redirect(url_for('admin.admin_backups'))

    # Safety: take snapshot before overwrite
    safety_snap = f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(db_path, os.path.join(BACKUP_FOLDER, safety_snap))

    # Overwrite current db
    shutil.copy2(src, db_path)

    log_activity('RESTORE', details=f"Database dipulihkan dari file: {safe_name}")
    flash(f'Database berhasil dipulihkan dari {safe_name}. Snapshot pra-restore: {safety_snap}.', 'success')
    return redirect(url_for('admin.admin_backups'))


@admin_bp.route('/admin/import-db', methods=['POST'])
@login_required
@admin_required
@sudo_required
def import_db_merge():
    """Smart DB Import: merge an old JESCA .db file into the current database.
    - Handles ID conflicts by remapping foreign keys
    - Preserves original asset codes when no conflict exists
    - Auto-renumbers conflicting codes
    - Creates a safety snapshot before any write
    - Stores reconciliation report in session for modal display
    """
    import sqlite3 as _sqlite3
    import tempfile as _tempfile

    uploaded = request.files.get('db_file')
    if not uploaded or uploaded.filename == '':
        flash('Pilih file .db terlebih dahulu.', 'danger')
        return redirect(url_for('admin.admin_backups'))

    if not uploaded.filename.lower().endswith('.db'):
        flash('File harus berformat .db (SQLite database).', 'danger')
        return redirect(url_for('admin.admin_backups'))

    # Save upload to temp file
    tmp_fd, tmp_path = _tempfile.mkstemp(suffix='.db', prefix='jesca_import_')
    os.close(tmp_fd)
    try:
        uploaded.save(tmp_path)

        # Validate that it's a real SQLite file
        try:
            test_conn = _sqlite3.connect(tmp_path)
            test_conn.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1").fetchall()
            test_conn.close()
        except Exception:
            flash('File yang diunggah bukan database SQLite yang valid.', 'danger')
            return redirect(url_for('admin.admin_backups'))

        # ── Step 1: Safety snapshot BEFORE any merge ──────────────────────
        snap_name = f"pre_merge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        snap_path = os.path.join(BACKUP_FOLDER, snap_name)
        shutil.copy2(db_path, snap_path)

        # ── Step 2: Open source DB (read-only via sqlite3 directly) ───────
        src = _sqlite3.connect(f'file:{tmp_path}?mode=ro', uri=True)
        src.row_factory = _sqlite3.Row

        report = {
            'summary': {
                'safety_snapshot': snap_name,
                'total_sites_new': 0,
                'total_vendors_new': 0,
                'total_assets_imported': 0,
                'assets_kept_code': 0,
                'assets_renumbered': 0,
                'total_pos_imported': 0,
                'total_maintenance_imported': 0,
                'total_circulation_imported': 0,
            },
            'changes': []
        }

        # Helper: get table names in source DB
        src_tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

        # ── Step 3: Merge SITES ──────────────────────────────────────────
        site_id_map = {}  # src_id → dst_id
        if 'sites' in src_tables:
            for row in src.execute("SELECT * FROM sites").fetchall():
                existing = Site.query.filter(
                    db.func.lower(Site.name) == row['name'].strip().lower()
                ).first()
                if existing:
                    site_id_map[row['id']] = existing.id
                else:
                    new_site = Site(
                        name=row['name'],
                        description=row['description'] if 'description' in row.keys() else None,
                        is_active=bool(row['is_active']) if 'is_active' in row.keys() else True
                    )
                    db.session.add(new_site)
                    db.session.flush()
                    site_id_map[row['id']] = new_site.id
                    report['summary']['total_sites_new'] += 1
                    report['changes'].append({
                        'type': 'Lokasi',
                        'name': row['name'],
                        'old_code': '-',
                        'new_code': '-',
                        'status': 'new',
                        'reason': 'Lokasi baru ditambahkan'
                    })

        # ── Step 4: Merge VENDORS ─────────────────────────────────────────
        vendor_id_map = {}  # src_id → dst_id
        if 'vendors' in src_tables:
            for row in src.execute("SELECT * FROM vendors").fetchall():
                existing = Vendor.query.filter(
                    db.func.lower(Vendor.name) == row['name'].strip().lower()
                ).first()
                if existing:
                    vendor_id_map[row['id']] = existing.id
                else:
                    new_vendor = Vendor(
                        name=row['name'],
                        contact_person=row['contact_person'] if 'contact_person' in row.keys() else None,
                        phone=row['phone'] if 'phone' in row.keys() else None,
                        email=row['email'] if 'email' in row.keys() else None,
                        address=row['address'] if 'address' in row.keys() else None,
                        notes=row['notes'] if 'notes' in row.keys() else None,
                        is_active=bool(row['is_active']) if 'is_active' in row.keys() else True
                    )
                    db.session.add(new_vendor)
                    db.session.flush()
                    vendor_id_map[row['id']] = new_vendor.id
                    report['summary']['total_vendors_new'] += 1
                    report['changes'].append({
                        'type': 'Vendor',
                        'name': row['name'],
                        'old_code': '-',
                        'new_code': '-',
                        'status': 'new',
                        'reason': 'Vendor baru ditambahkan'
                    })

        # ── Step 5: Merge ASSETS ─────────────────────────────────────────
        asset_id_map = {}  # src_id → dst_id
        if 'assets' in src_tables:
            src_asset_cols = [desc[0] for desc in src.execute("SELECT * FROM assets LIMIT 0").description] if src.execute("SELECT COUNT(*) FROM assets").fetchone()[0] > 0 else []
            # Re-fetch columns properly
            cur = src.execute("SELECT * FROM assets LIMIT 0")
            src_asset_cols = [d[0] for d in cur.description] if cur.description else []

            for row in src.execute("SELECT * FROM assets ORDER BY id ASC").fetchall():
                row_dict = dict(row)
                orig_code = row_dict.get('asset_code', '')
                category  = row_dict.get('category', 'Lainnya')

                # Check if code already exists in destination
                conflict = Asset.query.filter_by(asset_code=orig_code).first()
                if conflict:
                    new_code = generate_asset_code(category)
                    status_val = 'renumbered'
                    reason_val = f'Kode {orig_code} sudah ada, diberikan kode baru'
                    report['summary']['assets_renumbered'] += 1
                else:
                    new_code = orig_code
                    status_val = 'kept'
                    reason_val = 'Kode asli dipertahankan (tidak ada konflik)'
                    report['summary']['assets_kept_code'] += 1

                # Map foreign keys
                mapped_vendor_id = vendor_id_map.get(row_dict.get('vendor_id')) if row_dict.get('vendor_id') else None
                mapped_site_id   = site_id_map.get(row_dict.get('site_id')) if row_dict.get('site_id') else None

                # Parse date helpers
                def _parse_date(val):
                    if not val:
                        return None
                    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d'):
                        try:
                            from datetime import datetime as _dt
                            return _dt.strptime(str(val), fmt).date()
                        except Exception:
                            continue
                    return None

                def _parse_datetime(val):
                    if not val:
                        return None
                    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S'):
                        try:
                            from datetime import datetime as _dt
                            return _dt.strptime(str(val), fmt)
                        except Exception:
                            continue
                    return None

                new_asset = Asset(
                    asset_code=new_code,
                    name=row_dict.get('name', 'Asset'),
                    category=category,
                    purchase_date=_parse_date(row_dict.get('purchase_date')) or date.today(),
                    purchase_price=float(row_dict.get('purchase_price') or 0),
                    location=row_dict.get('location') or 'Kantor Pusat',
                    status=row_dict.get('status') or 'Aktif',
                    description=row_dict.get('description'),
                    image=None,  # don't copy image files
                    borrower=row_dict.get('borrower'),
                    borrow_date=_parse_datetime(row_dict.get('borrow_date')),
                    needs_maintenance=bool(row_dict.get('needs_maintenance', 0)),
                    maintenance_interval_days=row_dict.get('maintenance_interval_days'),
                    next_maintenance_date=_parse_date(row_dict.get('next_maintenance_date')),
                    last_maintenance_date=_parse_date(row_dict.get('last_maintenance_date')),
                    warranty_start=_parse_date(row_dict.get('warranty_start')),
                    warranty_end=_parse_date(row_dict.get('warranty_end')),
                    useful_life_years=row_dict.get('useful_life_years'),
                    salvage_value=float(row_dict.get('salvage_value') or 0),
                    total_checkout_days=int(row_dict.get('total_checkout_days') or 0),
                    custom_fields_json=row_dict.get('custom_fields_json'),
                    vendor_id=mapped_vendor_id,
                    site_id=mapped_site_id,
                    last_transfer_date=_parse_date(row_dict.get('last_transfer_date')),
                    last_transfer_from=row_dict.get('last_transfer_from'),
                )
                db.session.add(new_asset)
                db.session.flush()
                asset_id_map[row_dict['id']] = new_asset.id
                report['summary']['total_assets_imported'] += 1
                report['changes'].append({
                    'type': 'Aset',
                    'name': row_dict.get('name', ''),
                    'old_code': orig_code,
                    'new_code': new_code,
                    'status': status_val,
                    'reason': reason_val
                })

        # ── Step 6: Merge PURCHASE ORDERS ────────────────────────────────
        po_id_map = {}  # src_id → dst_id
        if 'purchase_orders' in src_tables:
            for row in src.execute("SELECT * FROM purchase_orders ORDER BY id ASC").fetchall():
                row_dict = dict(row)
                orig_po = row_dict.get('po_number', '')

                conflict_po = PurchaseOrder.query.filter_by(po_number=orig_po).first()
                if conflict_po:
                    new_po_number = generate_po_number()
                    po_status_val = 'renumbered'
                    po_reason = f'Nomor PO {orig_po} sudah ada'
                else:
                    new_po_number = orig_po
                    po_status_val = 'kept'
                    po_reason = 'Nomor PO asli dipertahankan'

                def _parse_date(val):
                    if not val:
                        return None
                    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
                        try:
                            from datetime import datetime as _dt
                            return _dt.strptime(str(val), fmt).date()
                        except Exception:
                            continue
                    return None

                def _parse_datetime(val):
                    if not val:
                        return None
                    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S'):
                        try:
                            from datetime import datetime as _dt
                            return _dt.strptime(str(val), fmt)
                        except Exception:
                            continue
                    return None

                new_po = PurchaseOrder(
                    po_number=new_po_number,
                    title=row_dict.get('title', ''),
                    description=row_dict.get('description'),
                    status=row_dict.get('status', 'Draft'),
                    priority=row_dict.get('priority', 'Normal'),
                    requested_by=row_dict.get('requested_by', ''),
                    approved_by=row_dict.get('approved_by'),
                    vendor_id=vendor_id_map.get(row_dict.get('vendor_id')) if row_dict.get('vendor_id') else None,
                    notes=row_dict.get('notes'),
                    created_at=_parse_datetime(row_dict.get('created_at')) or datetime.utcnow(),
                    updated_at=_parse_datetime(row_dict.get('updated_at')) or datetime.utcnow(),
                )
                db.session.add(new_po)
                db.session.flush()
                po_id_map[row_dict['id']] = new_po.id
                report['summary']['total_pos_imported'] += 1
                report['changes'].append({
                    'type': 'Purchase Order',
                    'name': row_dict.get('title', orig_po),
                    'old_code': orig_po,
                    'new_code': new_po_number,
                    'status': po_status_val,
                    'reason': po_reason
                })

        # ── Step 7: Merge PO ITEMS (children of PO) ──────────────────────
        if 'po_items' in src_tables and po_id_map:
            for row in src.execute("SELECT * FROM po_items ORDER BY id ASC").fetchall():
                row_dict = dict(row)
                mapped_po_id = po_id_map.get(row_dict.get('po_id'))
                if not mapped_po_id:
                    continue  # orphan — skip
                new_item = POItem(
                    po_id=mapped_po_id,
                    item_name=row_dict.get('item_name', ''),
                    specification=row_dict.get('specification'),
                    category=row_dict.get('category', ''),
                    quantity=int(row_dict.get('quantity') or 1),
                    unit=row_dict.get('unit', 'unit'),
                    unit_price=float(row_dict.get('unit_price') or 0),
                    notes=row_dict.get('notes'),
                )
                db.session.add(new_item)

        # ── Step 8: Merge PO HISTORIES ────────────────────────────────────
        if 'po_histories' in src_tables and po_id_map:
            for row in src.execute("SELECT * FROM po_histories ORDER BY id ASC").fetchall():
                row_dict = dict(row)
                mapped_po_id = po_id_map.get(row_dict.get('po_id'))
                if not mapped_po_id:
                    continue
                def _parse_datetime_h(val):
                    if not val:
                        return datetime.utcnow()
                    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S'):
                        try:
                            from datetime import datetime as _dt
                            return _dt.strptime(str(val), fmt)
                        except Exception:
                            continue
                    return datetime.utcnow()
                new_hist = PurchaseOrderHistory(
                    po_id=mapped_po_id,
                    changed_by=row_dict.get('changed_by', ''),
                    old_status=row_dict.get('old_status', ''),
                    new_status=row_dict.get('new_status', ''),
                    notes=row_dict.get('notes'),
                    created_at=_parse_datetime_h(row_dict.get('created_at')),
                )
                db.session.add(new_hist)

        # ── Step 9: Merge MAINTENANCE RECORDS ────────────────────────────
        if 'maintenance_records' in src_tables and asset_id_map:
            for row in src.execute("SELECT * FROM maintenance_records ORDER BY id ASC").fetchall():
                row_dict = dict(row)
                mapped_asset_id = asset_id_map.get(row_dict.get('asset_id'))
                if not mapped_asset_id:
                    continue
                def _pd(val):
                    if not val:
                        return date.today()
                    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
                        try:
                            from datetime import datetime as _dt
                            return _dt.strptime(str(val), fmt).date()
                        except Exception:
                            continue
                    return date.today()
                new_mr = MaintenanceRecord(
                    asset_id=mapped_asset_id,
                    service_type=row_dict.get('service_type', 'Rutin'),
                    action_taken=row_dict.get('action_taken', ''),
                    cost=float(row_dict.get('cost') or 0),
                    proof_file=None,  # don't copy files
                    performed_by=row_dict.get('performed_by', ''),
                    service_date=_pd(row_dict.get('service_date')),
                    next_service_date=_pd(row_dict.get('next_service_date')) if row_dict.get('next_service_date') else None,
                )
                db.session.add(new_mr)
                report['summary']['total_maintenance_imported'] += 1

        # ── Step 10: Merge ASSET CIRCULATION LOGS ─────────────────────────
        if 'asset_circulation_logs' in src_tables and asset_id_map:
            for row in src.execute("SELECT * FROM asset_circulation_logs ORDER BY id ASC").fetchall():
                row_dict = dict(row)
                mapped_asset_id = asset_id_map.get(row_dict.get('asset_id'))
                if not mapped_asset_id:
                    continue
                def _pdt(val):
                    if not val:
                        return datetime.utcnow()
                    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S'):
                        try:
                            from datetime import datetime as _dt
                            return _dt.strptime(str(val), fmt)
                        except Exception:
                            continue
                    return datetime.utcnow()
                new_circ = AssetCirculationLog(
                    asset_id=mapped_asset_id,
                    borrower=row_dict.get('borrower', ''),
                    borrow_date=_pdt(row_dict.get('borrow_date')),
                    return_date=_pdt(row_dict.get('return_date')) if row_dict.get('return_date') else None,
                    duration_days=int(row_dict.get('duration_days') or 0),
                    notes=row_dict.get('notes'),
                    checkout_by=row_dict.get('checkout_by', ''),
                    checkin_by=row_dict.get('checkin_by'),
                )
                db.session.add(new_circ)
                report['summary']['total_circulation_imported'] += 1

        src.close()

        # ── Step 11: Commit everything ────────────────────────────────────
        db.session.commit()

        # ── Step 12: Log activity ─────────────────────────────────────────
        s = report['summary']
        log_activity(
            'IMPORT_DB_MERGE',
            details=(
                f"Smart Import DB '{uploaded.filename}': "
                f"{s['total_assets_imported']} aset "
                f"({s['assets_kept_code']} kode dipertahankan, {s['assets_renumbered']} direnomor), "
                f"{s['total_pos_imported']} PO, "
                f"{s['total_vendors_new']} vendor baru, "
                f"{s['total_sites_new']} lokasi baru. "
                f"Snapshot: {snap_name}"
            )
        )

        # ── Step 13: Store report in session (PRG pattern) ────────────────
        session['import_report'] = report
        session['show_import_modal'] = True
        flash(
            f"Import berhasil! {s['total_assets_imported']} aset, "
            f"{s['total_pos_imported']} PO diimpor. "
            f"Snapshot keamanan: {snap_name}",
            'success'
        )

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"import_db_merge error: {e}")
        flash(f'Import gagal: {str(e)}', 'danger')

    finally:
        # Clean up temp file
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    return redirect(url_for('admin.admin_backups'))


@admin_bp.route('/admin/import-report/csv')
@login_required
@admin_required
def import_report_csv():
    """Download reconciliation report from last import as CSV."""
    import csv as _csv
    report = session.get('import_report')
    if not report:
        flash('Tidak ada laporan impor yang tersedia.', 'warning')
        return redirect(url_for('admin.admin_backups'))

    output = io.StringIO()
    output.write('\ufeff')  # BOM for Excel
    writer = _csv.writer(output, delimiter=';')
    writer.writerow(['Tipe', 'Nama', 'Kode Lama', 'Kode Baru', 'Status', 'Keterangan'])
    for change in report.get('changes', []):
        status_label = {
            'renumbered': 'Direnomor',
            'kept': 'Kode Dipertahankan',
            'new': 'Baru Ditambahkan'
        }.get(change.get('status', ''), change.get('status', ''))
        writer.writerow([
            change.get('type', ''),
            change.get('name', ''),
            change.get('old_code', '-'),
            change.get('new_code', '-'),
            status_label,
            change.get('reason', '')
        ])

    filename = f"jesca_import_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@admin_bp.route('/admin/optimize-db', methods=['POST'])
@login_required
@admin_required
@sudo_required
def optimize_database():
    """Optimize SQLite database via VACUUM, PRAGMA optimize, and Integrity Check."""
    import sqlite3 as _sqlite3

    if not os.path.exists(db_path):
        flash('Berkas basis data tidak ditemukan.', 'danger')
        return redirect(url_for('admin.admin_backups'))

    try:
        size_before = os.path.getsize(db_path)

        # Connect to SQLite for integrity check and vacuum
        conn = _sqlite3.connect(db_path)
        cur = conn.cursor()

        # Step 1: Integrity check
        integrity_rows = cur.execute("PRAGMA integrity_check").fetchall()
        integrity_ok = all(row[0] == 'ok' for row in integrity_rows)
        if not integrity_ok:
            error_details = "; ".join(row[0] for row in integrity_rows)
            conn.close()
            log_activity('OPTIMIZE_DB_FAIL', details=f"Integritas database bermasalah: {error_details}")
            flash(f'Pemeriksaan integritas gagal: {error_details}', 'danger')
            return redirect(url_for('admin.admin_backups'))

        # Step 2: PRAGMA optimize
        cur.execute("PRAGMA optimize")
        conn.commit()

        # Step 3: VACUUM in autocommit mode
        conn.isolation_level = None
        cur.execute("VACUUM")
        conn.close()

        size_after = os.path.getsize(db_path)
        saved_bytes = max(0, size_before - size_after)
        saved_kb = round(saved_bytes / 1024, 2)
        final_size_kb = round(size_after / 1024, 2)

        log_activity(
            'OPTIMIZE_DB',
            details=(
                f"Optimasi basis data selesai. Status integritas: Sehat (OK). "
                f"Ukuran akhir: {final_size_kb} KB. Ruang dibebaskan: {saved_kb} KB."
            )
        )
        flash(
            f"Optimasi berhasil! Status integritas: Sehat (OK). "
            f"Ukuran database: {final_size_kb} KB (ruang dibebaskan: {saved_kb} KB).",
            'success'
        )
    except Exception as e:
        current_app.logger.exception(f"optimize_database error: {e}")
        flash(f'Gagal melakukan optimasi basis data: {str(e)}', 'danger')

    return redirect(url_for('admin.admin_backups'))


@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
@sudo_required
def system_settings():
    """System settings, system health diagnostics, and dynamic SMTP setup."""
    setting = SystemSetting.get_settings()

    if request.method == 'POST':
        mail_enabled = request.form.get('mail_enabled') == '1'
        mail_server = request.form.get('mail_server', '').strip()
        mail_port = int(request.form.get('mail_port', 587) or 587)
        encryption = request.form.get('encryption', 'tls')
        mail_username = request.form.get('mail_username', '').strip()
        mail_password_input = request.form.get('mail_password', '').strip()
        mail_sender_name = request.form.get('mail_sender_name', 'JESCA Notification').strip()
        mail_target_admins = request.form.get('mail_target_admins', '').strip()

        setting.mail_enabled = mail_enabled
        setting.mail_server = mail_server or 'smtp.gmail.com'
        setting.mail_port = mail_port
        setting.mail_use_tls = (encryption == 'tls')
        setting.mail_use_ssl = (encryption == 'ssl')
        setting.mail_username = mail_username
        setting.mail_sender_name = mail_sender_name or 'JESCA Notification'
        setting.mail_target_admins = mail_target_admins

        # Network & Domain settings
        app_base_url = request.form.get('app_base_url', '').strip()
        enforce_https_requested = (request.form.get('enforce_https') == '1')

        # Validasi Cerdas Base URL & Enforce HTTPS
        is_local_target = False
        if app_base_url:
            clean_url = app_base_url if '://' in app_base_url else f"http://{app_base_url}"
            try:
                from urllib.parse import urlparse
                host_only = (urlparse(clean_url).hostname or '').lower()
            except Exception:
                host_only = ''
            if host_only in ('localhost', '127.0.0.1', '::1') or \
               host_only.startswith(('192.168.', '10.', '172.16.', '172.17.', '172.18.', '172.19.', '172.20.', '172.21.', '172.22.', '172.23.', '172.24.', '172.25.', '172.26.', '172.27.', '172.28.', '172.29.', '172.30.', '172.31.')):
                is_local_target = True

        if is_local_target:
            if app_base_url.lower().startswith('https://'):
                app_base_url = 'http://' + app_base_url[8:]
                flash('Peringatan: Alamat IP lokal atau localhost tidak memiliki sertifikat SSL. Protokol otomatis disesuaikan ke http:// agar sistem tidak terkunci.', 'warning')
            if enforce_https_requested:
                enforce_https_requested = False
                flash('Peringatan: Fitur "Paksa Jalur Aman (Enforce HTTPS)" dinonaktifkan otomatis untuk alamat IP lokal demi mencegah browser gagal memuat sistem.', 'warning')

        if app_base_url:
            setting.app_base_url = app_base_url.rstrip('/')
        setting.enforce_https = enforce_https_requested
        setting.ip_whitelist_enabled = (request.form.get('ip_whitelist_enabled') == '1')
        setting.allowed_ip_ranges = request.form.get('allowed_ip_ranges', '').strip()

        if mail_password_input:
            setting.mail_password = encrypt_smtp_password(mail_password_input)

        db.session.commit()
        log_activity('EDIT_SETTINGS', details=f"Pengaturan sistem diperbarui oleh {current_user.username}. SMTP: {'Aktif' if mail_enabled else 'Nonaktif'}, Whitelist: {'Aktif' if setting.ip_whitelist_enabled else 'Nonaktif'}.")
        flash('Pengaturan sistem, jaringan, dan SMTP berhasil disimpan!', 'success')
        return redirect(url_for('admin.system_settings'))

    # Calculate system diagnostic metrics
    db_size_bytes = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    if db_size_bytes > 1024 * 1024:
        db_size_str = f"{db_size_bytes / (1024 * 1024):.2f} MB"
    else:
        db_size_str = f"{db_size_bytes / 1024:.1f} KB"

    # Count assets, users, categories, vendors, sites
    total_assets = Asset.query.count()
    total_users = User.query.count()
    total_vendors = Vendor.query.count()
    total_sites = Site.query.count()
    total_pos = PurchaseOrder.query.count()

    import platform
    import sys
    runtime_info = {
        'python_version': platform.python_version(),
        'platform': platform.platform(),
        'is_docker': os.path.exists('/.dockerenv'),
        'db_size': db_size_str,
        'client_ip': get_client_ip(),
        'counts': {
            'assets': total_assets,
            'users': total_users,
            'vendors': total_vendors,
            'sites': total_sites,
            'pos': total_pos
        }
    }

    return render_template(
        'settings.html',
        setting=setting,
        has_password=bool(setting.mail_password),
        runtime=runtime_info,
        app_version=APP_VERSION,
        github_repo=GITHUB_REPO
    )


@admin_bp.route('/api/system/quick-tunnel/status', methods=['GET'])
@login_required
@role_required('Admin')
def api_quick_tunnel_status():
    global _QUICK_TUNNEL_PROC, _QUICK_TUNNEL_INFO
    with _QUICK_TUNNEL_LOCK:
        if _QUICK_TUNNEL_PROC and _QUICK_TUNNEL_PROC.poll() is not None:
            _QUICK_TUNNEL_PROC = None
            _QUICK_TUNNEL_INFO = {
                'active': False,
                'public_url': None,
                'expires_in': None,
                'started_at': None
            }
        return jsonify(_QUICK_TUNNEL_INFO)


@admin_bp.route('/api/system/quick-tunnel/start', methods=['POST'])
@login_required
@role_required('Admin')
def api_quick_tunnel_start():
    port = 5000
    host_header = request.headers.get('Host', '')
    if host_header and ':' in host_header:
        p = host_header.split(':')[1]
        if p.isdigit():
            port = int(p)
    result = start_quick_tunnel(port=port)
    return jsonify(result)


@admin_bp.route('/api/system/quick-tunnel/stop', methods=['POST'])
@login_required
@role_required('Admin')
def api_quick_tunnel_stop():
    result = stop_quick_tunnel()
    return jsonify(result)


@admin_bp.route('/settings/test-smtp', methods=['POST'])
@login_required
@role_required('Admin')
@sudo_required
def test_smtp_connection():
    """Send test email to test recipient to verify SMTP credentials and handshake."""
    test_target = request.form.get('test_email', '').strip()
    if not test_target:
        flash('Masukkan alamat email tujuan uji coba.', 'warning')
        return redirect(url_for('admin.system_settings'))

    setting = SystemSetting.get_settings()
    if not setting.mail_server or not setting.mail_username:
        flash('Server SMTP dan Username pengirim belum dikonfigurasi.', 'danger')
        return redirect(url_for('admin.system_settings'))

    decrypted_pwd = decrypt_smtp_password(setting.mail_password)

    try:
        sender_addr = setting.mail_username
        sender_name = setting.mail_sender_name or "JESCA Notification"

        msg = MIMEMultipart('alternative')
        msg['Subject'] = "[UJI KONEKSI] Tes Pengiriman Email JESCA"
        msg['From'] = f"{sender_name} <{sender_addr}>"
        msg['To'] = test_target

        wib_time_str = format_wib_datetime()
        enc_label = "SSL / SMTPS" if setting.mail_use_ssl else ("STARTTLS" if setting.mail_use_tls else "None")
        rows = [
            ("Server Host", f"<span style='font-family: monospace; font-weight: 600;'>{setting.mail_server}</span> <span style='font-size: 11px; padding: 2px 6px; background: #e0f2fe; color: #0369a1; border-radius: 4px; font-family: monospace;'>Port {setting.mail_port}</span>"),
            ("Protokol Keamanan", f"<span style='font-size: 11px; padding: 2px 8px; background: #dcfce7; color: #15803d; border-radius: 4px; font-weight: 600;'>{enc_label}</span>"),
            ("Akun Pengirim", f"<span style='font-family: monospace;'>{setting.mail_username}</span>"),
            ("Waktu Pengujian", f"<strong>{wib_time_str}</strong>"),
            ("Status Koneksi", "<span style='display: inline-block; width: 8px; height: 8px; background: #22c55e; border-radius: 50%; margin-right: 6px;'></span><strong style='color: #15803d;'>Berhasil (250 OK / Authenticated)</strong>")
        ]
        intro_html = f"Halo <strong>{current_user.full_name}</strong>,<br>Konfigurasi Dynamic SMTP JESCA Anda telah berhasil terhubung dengan server email dan siap digunakan untuk pengiriman notifikasi otomatis."
        note_text = "Sistem kini siap mengirimkan notifikasi instan untuk perubahan kondisi aset bermasalah dan pengajuan Purchase Order."
        html = build_system_email_html(
            header_title="Hasil Uji Coba Koneksi Server Email (SMTP)",
            badge_text="Koneksi Berhasil",
            badge_type="success",
            intro_html=intro_html,
            rows=rows,
            note_text=note_text
        )
        msg.attach(MIMEText(html, 'html', 'utf-8'))

        if setting.mail_use_ssl:
            server = smtplib.SMTP_SSL(setting.mail_server, setting.mail_port or 465, timeout=12)
        else:
            server = smtplib.SMTP(setting.mail_server, setting.mail_port or 587, timeout=12)
            if setting.mail_use_tls:
                server.starttls()

        if decrypted_pwd:
            try:
                server.login(setting.mail_username, decrypted_pwd)
            except (smtplib.SMTPAuthenticationError, smtplib.SMTPServerDisconnected) as auth_err:
                err_text = str(auth_err)
                if '535' in err_text or 'BadCredentials' in err_text or isinstance(auth_err, smtplib.SMTPServerDisconnected):
                    raise Exception("Kredensial email atau App Password salah/ditolak oleh Gmail. Pastikan Anda menggunakan 16 karakter 'App Password' (bukan password login akun biasa) dari myaccount.google.com/apppasswords.")
                raise Exception(f"Autentikasi ditolak: {err_text}")

        server.sendmail(sender_addr, [test_target], msg.as_string())
        server.quit()

        log_activity('TEST_SMTP', details=f"Uji koneksi SMTP sukses terkirim ke {test_target}.")
        flash(f'Berhasil! Email uji coba berhasil dikirim ke {test_target}.', 'success')
    except Exception as e:
        current_app.logger.error(f"SMTP Test Connection Error: {e}")
        flash(f'Koneksi SMTP gagal: {str(e)}', 'danger')

    return redirect(url_for('admin.system_settings'))


@admin_bp.route('/api/system/check-update')
@login_required
@role_required('Admin')
@sudo_required
def api_check_update():
    """
    Check GitHub API for the latest version.
    Supports /releases/latest, fallback to /releases, and fallback to /tags
    so it works even if a GitHub Release has not been formally published yet.
    """
    import urllib.request
    import urllib.error
    import json as _json

    def semver_tuple(v):
        try:
            parts = re.findall(r'\d+', str(v))
            nums = [int(x) for x in parts[:4]]
            while len(nums) < 4:
                nums.append(0)
            return tuple(nums)
        except Exception:
            return (0, 0, 0, 0)

    def fetch_github_endpoint(endpoint):
        api_url = f'https://api.github.com/repos/{GITHUB_REPO}/{endpoint}'
        req = urllib.request.Request(
            api_url,
            headers={
                'User-Agent': f'JESCA-UpdateChecker/{APP_VERSION}',
                'Accept': 'application/vnd.github+json'
            }
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return _json.loads(response.read().decode())

    latest_tag = ''
    release_name = ''
    release_body = ''
    release_url = f'https://github.com/{GITHUB_REPO}/releases'
    published_at = ''

    try:
        # Step 1: Try /releases/latest first
        try:
            data = fetch_github_endpoint('releases/latest')
            latest_tag = data.get('tag_name', '').lstrip('v')
            release_name = data.get('name', f"JESCA v{latest_tag}")
            release_body = data.get('body', '')
            release_url = data.get('html_url', release_url)
            published_at = data.get('published_at', '')
        except urllib.error.HTTPError as http_err:
            if http_err.code == 404:
                # Step 2: Fallback to list of all releases (e.g. if latest is pre-release)
                try:
                    releases = fetch_github_endpoint('releases')
                    if releases and isinstance(releases, list):
                        rel = releases[0]
                        latest_tag = rel.get('tag_name', '').lstrip('v')
                        release_name = rel.get('name', f"JESCA v{latest_tag}")
                        release_body = rel.get('body', '')
                        release_url = rel.get('html_url', release_url)
                        published_at = rel.get('published_at', '')
                except urllib.error.HTTPError:
                    pass

            if not latest_tag:
                # Step 3: Fallback to /tags (pushed git tags like v2.3.0)
                try:
                    tags = fetch_github_endpoint('tags')
                    if tags and isinstance(tags, list):
                        # Sort by semver descending
                        sorted_tags = sorted(
                            tags,
                            key=lambda t: semver_tuple(t.get('name', '')),
                            reverse=True
                        )
                        top_tag = sorted_tags[0]
                        tag_name = top_tag.get('name', '')
                        latest_tag = tag_name.lstrip('v')
                        release_name = f"JESCA Rilis Tag {tag_name}"
                        release_body = f"Pembaruan versi {tag_name} tersedia di repositori GitHub."
                        release_url = f"https://github.com/{GITHUB_REPO}/tree/{tag_name}"
                except urllib.error.HTTPError as tag_err:
                    if tag_err.code == 403:
                        return jsonify({
                            'status': 'error',
                            'message': 'Batas pengecekan GitHub API tercapai (Rate Limit). Silakan coba lagi beberapa saat.',
                            'update_available': False
                        }), 429
                    raise tag_err

        if not latest_tag:
            # If no tags or releases found on GitHub, current version is up to date
            latest_tag = APP_VERSION
            release_name = f"JESCA v{APP_VERSION} (Rilis Stabil)"
            release_body = "Sistem telah menggunakan versi codebase saat ini."

        current_tuple = semver_tuple(APP_VERSION)
        latest_tuple = semver_tuple(latest_tag)
        update_available = latest_tuple > current_tuple

        return jsonify({
            'status': 'ok',
            'current_version': APP_VERSION,
            'latest_version': latest_tag,
            'release_name': release_name,
            'release_notes': release_body[:600] if release_body else '',
            'release_url': release_url,
            'published_at': published_at,
            'update_available': update_available
        })

    except urllib.error.HTTPError as e:
        if e.code == 403:
            return jsonify({
                'status': 'error',
                'message': 'Batas pengecekan GitHub API tercapai (Rate Limit 60 req/jam). Silakan tunggu beberapa menit.',
                'update_available': False
            }), 429
        return jsonify({
            'status': 'error',
            'message': f'Respons GitHub ({e.code}): {e.reason}',
            'update_available': False
        }), 502
    except urllib.error.URLError as e:
        return jsonify({
            'status': 'error',
            'message': f'Koneksi internet server terputus: {str(e.reason)}',
            'update_available': False
        }), 503
    except Exception as e:
        current_app.logger.error(f"Check update error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'update_available': False
        }), 500


@admin_bp.route('/system/update', methods=['POST'])
@login_required
@role_required('Admin')
@sudo_required
def system_self_update():
    """
    Safe self-update route with Hybrid Git / Direct Archive Fallback:
    1. If .git directory exists: attempts `git pull origin main`.
    2. If .git is missing (e.g. downloaded as ZIP) or git pull fails:
       Automatically downloads the latest codebase archive from GitHub,
       safely extracts updated files while strictly preserving data/,
       uploads/, attachments/, backups/, and .env.
    3. Runs `pip install -r requirements.txt --quiet --no-cache-dir`.
    4. Triggers graceful reload on Gunicorn.
    """
    import subprocess
    import shutil
    import tarfile
    import tempfile
    import urllib.request

    base = os.path.abspath(os.path.dirname(__file__))
    git_dir = os.path.join(base, '.git')
    has_git = os.path.exists(git_dir) and (shutil.which('git') is not None)

    log_lines = []

    def run_cmd(cmd, cwd=None):
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=cwd or base, timeout=120
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if stdout:
            log_lines.append(stdout)
        if stderr:
            log_lines.append(f'[stderr] {stderr}')
        return result.returncode

    try:
        log_lines.append('[INFO] Memulai proses update otomatis JESCA...')
        update_success = False

        # Attempt 1: Git Pull (jika folder .git ada dan binary git terpasang)
        if has_git:
            log_lines.append('[STEP 1/3] Menarik perubahan terbaru dari repositori Git...')
            rc = run_cmd(['git', 'pull', 'origin', 'main'])
            if rc == 0:
                update_success = True
                log_lines.append('[SUCCESS] Git pull berhasil.')
            else:
                log_lines.append('[WARNING] Git pull mengalami kendala. Beralih ke mode Auto-Download langsung dari GitHub...')

        # Attempt 2: Fallback ke Direct Archive Download (jika bukan git clone / download ZIP)
        if not update_success:
            log_lines.append('[STEP 1/3] Mengunduh arsip rilis terbaru langsung dari GitHub (Mode Tanpa Git)...')
            archive_url = f'https://codeload.github.com/{GITHUB_REPO}/tar.gz/main'
            req = urllib.request.Request(
                archive_url,
                headers={'User-Agent': f'JESCA-Updater/{APP_VERSION}'}
            )

            with tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False) as tmp_archive:
                tmp_archive_path = tmp_archive.name
                try:
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        tmp_archive.write(resp.read())
                    tmp_archive.flush()

                    log_lines.append('[INFO] Arsip rilis berhasil diunduh. Mengekstrak pembaruan sistem secara aman...')
                    with tarfile.open(tmp_archive_path, 'r:gz') as tar:
                        for member in tar.getmembers():
                            # Path format: JESCA-main/<relative_path>
                            rel_path = member.name.partition('/')[2]
                            if not rel_path:
                                continue

                            # Proteksi ketat: JANGAN PERNAH menimpa data pengguna
                            protected_prefixes = ('data/', 'static/uploads/', 'static/attachments/', 'backups/', '.env')
                            if any(rel_path == p.rstrip('/') or rel_path.startswith(p) for p in protected_prefixes):
                                continue

                            target_path = os.path.join(base, rel_path)
                            if member.isdir():
                                os.makedirs(target_path, exist_ok=True)
                            else:
                                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                                with tar.extractfile(member) as src_f, open(target_path, 'wb') as dst_f:
                                    shutil.copyfileobj(src_f, dst_f)

                    update_success = True
                    log_lines.append('[SUCCESS] Seluruh berkas pembaruan berhasil diekstrak (database dan berkas unggahan tetap aman).')
                finally:
                    if os.path.exists(tmp_archive_path):
                        try:
                            os.remove(tmp_archive_path)
                        except Exception:
                            pass

        if not update_success:
            return jsonify({
                'status': 'error',
                'message': 'Gagal mengunduh pembaruan dari GitHub.',
                'log': '\n'.join(log_lines)
            }), 500

        # Step 2: pip install requirements
        log_lines.append('[STEP 2/3] Memeriksa & memperbarui dependensi Python...')
        req_file = os.path.join(base, 'requirements.txt')
        if os.path.exists(req_file):
            rc = run_cmd(['pip', 'install', '-r', req_file, '--quiet', '--no-cache-dir'])
            if rc != 0:
                log_lines.append('[WARNING] pip install ada catatan peringatan, melanjutkan proses reload...')
            else:
                log_lines.append('[SUCCESS] Dependensi Python terverifikasi mutakhir.')

        # Step 3: Graceful restart
        log_lines.append('[STEP 3/3] Mengirim sinyal graceful reload ke Gunicorn...')
        restarted = False

        # Try gunicorn HUP signal via PID file
        gunicorn_pid_file = '/tmp/gunicorn.pid'
        if os.path.exists(gunicorn_pid_file):
            try:
                with open(gunicorn_pid_file) as f:
                    pid = int(f.read().strip())
                os.kill(pid, 1)  # SIGHUP = 1
                log_lines.append(f'[SUCCESS] SIGHUP terkirim ke Gunicorn PID {pid}.')
                restarted = True
            except Exception as e:
                log_lines.append(f'[WARNING] Gagal mengirim SIGHUP: {e}')

        # Fallback: find gunicorn master process
        if not restarted:
            try:
                result = subprocess.run(
                    ['pgrep', '-f', 'gunicorn.*app:app'],
                    capture_output=True, text=True, timeout=5
                )
                pids = result.stdout.strip().split('\n')
                master_pid = int(pids[0]) if pids and pids[0] else None
                if master_pid:
                    os.kill(master_pid, 1)  # SIGHUP
                    log_lines.append(f'[SUCCESS] SIGHUP terkirim ke Gunicorn master PID {master_pid}.')
                    restarted = True
            except Exception as e:
                log_lines.append(f'[WARNING] Tidak bisa menemukan proses Gunicorn: {e}')

        # Fallback: touch reload trigger
        if not restarted:
            trigger = os.path.join(base, '.reload_trigger')
            try:
                with open(trigger, 'w') as f:
                    f.write(datetime.utcnow().isoformat())
                log_lines.append(f'[INFO] File trigger restart dibuat: {trigger}.')
            except Exception:
                pass

        log_activity('SYSTEM_UPDATE', details=f'Update otomatis JESCA berhasil dijalankan oleh {current_user.username}.')
        log_lines.append('[SUCCESS] Update selesai dengan sukses! Sistem siap digunakan.')
        return jsonify({'status': 'ok', 'message': 'Pembaruan sistem berhasil.', 'log': '\n'.join(log_lines)})

    except subprocess.TimeoutExpired:
        return jsonify({'status': 'error', 'message': 'Update timeout setelah 120 detik.', 'log': '\n'.join(log_lines)}), 500
    except Exception as e:
        current_app.logger.error(f'System self-update error: {e}')
        return jsonify({'status': 'error', 'message': str(e), 'log': '\n'.join(log_lines)}), 500

    except subprocess.TimeoutExpired:
        return jsonify({'status': 'error', 'message': 'Update timeout setelah 120 detik.', 'log': '\n'.join(log_lines)}), 500
    except Exception as e:
        current_app.logger.error(f'System self-update error: {e}')
        return jsonify({'status': 'error', 'message': str(e), 'log': '\n'.join(log_lines)}), 500


@admin_bp.route('/accounts')
@login_required
@admin_required
def accounts():
    all_users = User.query.order_by(User.created_at.asc()).all()
    return render_template(
        'accounts.html',
        users=all_users,
        roles=ROLE_CHOICES
    )


@admin_bp.route('/users')
@login_required
@admin_required
def users_redirect():
    return redirect(url_for('admin.accounts'))


@admin_bp.route('/accounts/create', methods=['POST'])
@login_required
@admin_required
def create_account():
    username = request.form.get('username', '').strip()
    full_name = request.form.get('full_name', '').strip()
    role = request.form.get('role', 'Staff').strip()
    password = request.form.get('password', '').strip()

    if not username or not password:
        flash('Username dan password wajib diisi.', 'danger')
        return redirect(url_for('admin.accounts'))

    is_valid, err_msg = validate_password(password)
    if not is_valid:
        flash(err_msg, 'danger')
        return redirect(url_for('admin.accounts'))

    if User.query.filter_by(username=username).first():
        flash(f'Username "{username}" sudah terdaftar.', 'danger')
        return redirect(url_for('admin.accounts'))

    new_user = User(
        username=username,
        full_name=full_name or username,
        role=role,
        is_active=True,
        force_password_change=True  # Force change on first login
    )
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()

    log_activity(
        'TAMBAH_USER',
        details=f"Akun baru dibuat oleh Admin: {username} ({full_name}) dengan role {role}."
    )

    flash(f'Akun baru "{username}" ({role}) berhasil dibuat! Pengguna wajib mengganti password saat pertama kali masuk.', 'success')
    return redirect(url_for('admin.accounts'))


@admin_bp.route('/accounts/<int:user_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_account(user_id):
    target_user = db.session.get(User, user_id)
    if not target_user:
        flash('Pengguna tidak ditemukan.', 'danger')
        return redirect(url_for('admin.accounts'))

    full_name = request.form.get('full_name', '').strip()
    role = request.form.get('role', target_user.role).strip()
    is_active = bool(request.form.get('is_active'))

    if target_user.id == current_user.id and role != 'Admin':
        flash('Anda tidak dapat mengubah role akun Anda sendiri dari Admin.', 'danger')
        return redirect(url_for('admin.accounts'))

    target_user.full_name = full_name or target_user.username
    target_user.role = role
    target_user.is_active = is_active

    remove_avatar = request.form.get('remove_avatar') == '1'
    if remove_avatar and target_user.profile_image:
        delete_avatar_file(target_user.profile_image)
        target_user.profile_image = None

    avatar_file = request.files.get('avatar_file')
    if avatar_file and avatar_file.filename != '':
        saved_name = save_avatar_file(avatar_file)
        if saved_name:
            if target_user.profile_image:
                delete_avatar_file(target_user.profile_image)
            target_user.profile_image = saved_name

    db.session.commit()

    log_activity(
        'EDIT_USER',
        details=f"Data akun {target_user.username} diperbarui: Role {role}, Status Aktif: {is_active}."
    )

    flash(f'Data akun "{target_user.username}" berhasil diperbarui!', 'success')
    return redirect(url_for('admin.accounts'))


@admin_bp.route('/accounts/<int:user_id>/change-password', methods=['POST'])
@login_required
@admin_required
def admin_change_user_password(user_id):
    target_user = db.session.get(User, user_id)
    if not target_user:
        flash('Pengguna tidak ditemukan.', 'danger')
        return redirect(url_for('admin.accounts'))

    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()

    is_valid, err_msg = validate_password(new_password)
    if not is_valid:
        flash(err_msg, 'danger')
        return redirect(url_for('admin.accounts'))

    if new_password != confirm_password:
        flash('Konfirmasi password tidak cocok.', 'danger')
        return redirect(url_for('admin.accounts'))

    target_user.set_password(new_password)
    target_user.force_password_change = True  # Require change after reset
    db.session.commit()

    log_activity(
        'RESET_PASSWORD_USER',
        details=f"Password akun {target_user.username} direset oleh {current_user.username}."
    )

    flash(f'Password untuk akun "{target_user.username}" berhasil diubah!', 'success')
    return redirect(url_for('admin.accounts'))


@admin_bp.route('/accounts/<int:user_id>/generate-api-key', methods=['POST'])
@login_required
@admin_required
def generate_api_key(user_id):
    """Generate or rotate REST API key for user."""
    target_user = db.session.get(User, user_id)
    if not target_user:
        flash('Pengguna tidak ditemukan.', 'danger')
        return redirect(url_for('admin.accounts'))

    new_key = f"jesca_{secrets.token_hex(24)}"
    target_user.api_key = new_key
    db.session.commit()

    log_activity('GENERATE_API_KEY', details=f"API Key baru dibuat untuk {target_user.username}.")
    flash(f'API Key baru untuk {target_user.username} berhasil dibuat: {new_key}', 'success')
    return redirect(url_for('admin.accounts'))


@admin_bp.route('/accounts/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_account(user_id):
    if user_id == current_user.id:
        flash('Anda tidak dapat menghapus akun Anda sendiri.', 'danger')
        return redirect(url_for('admin.accounts'))

    target_user = db.session.get(User, user_id)
    if not target_user:
        flash('Pengguna tidak ditemukan.', 'danger')
        return redirect(url_for('admin.accounts'))

    u_name = target_user.username
    try:
        db.session.delete(target_user)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal menghapus akun user {u_name}: {e}")
        flash(f'Akun "{u_name}" tidak dapat dihapus karena masih terhubung dengan data riwayat transaksi.', 'warning')
        return redirect(url_for('admin.accounts'))

    log_activity('HAPUS_USER', details=f"Akun {u_name} dihapus oleh {current_user.username}.")
    flash(f'Akun "{u_name}" telah berhasil dihapus.', 'info')
    return redirect(url_for('admin.accounts'))


