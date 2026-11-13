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

assets_bp = Blueprint('assets', __name__)


@assets_bp.route('/assets')
@login_required
def assets():
    """Asset management with searching, filters (category, status, maintenance, vendor, site, warranty)."""
    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()
    status_filter = request.args.get('status', '').strip()
    maintenance_filter = request.args.get('maintenance', '').strip()
    vendor_filter = request.args.get('vendor', '').strip()
    site_filter = request.args.get('site', '').strip()
    warranty_filter = request.args.get('warranty', '').strip()

    query = Asset.query

    if search_query:
        search_fmt = f"%{search_query}%"
        query = query.filter(
            db.or_(
                Asset.asset_code.ilike(search_fmt),
                Asset.name.ilike(search_fmt),
                Asset.location.ilike(search_fmt),
                Asset.description.ilike(search_fmt),
                Asset.borrower.ilike(search_fmt)
            )
        )

    if category_filter:
        query = query.filter(Asset.category == category_filter)

    if status_filter:
        query = query.filter(Asset.status == status_filter)

    if vendor_filter:
        try:
            query = query.filter(Asset.vendor_id == int(vendor_filter))
        except ValueError:
            pass

    if site_filter:
        try:
            query = query.filter(Asset.site_id == int(site_filter))
        except ValueError:
            pass

    today = date.today()
    if warranty_filter == 'active':
        query = query.filter(Asset.warranty_end != None, Asset.warranty_end >= today)
    elif warranty_filter == 'expired':
        query = query.filter(Asset.warranty_end != None, Asset.warranty_end < today)
    elif warranty_filter == 'expiring':
        threshold_30 = today + timedelta(days=30)
        query = query.filter(Asset.warranty_end != None, Asset.warranty_end >= today, Asset.warranty_end <= threshold_30)

    if maintenance_filter == 'due':
        threshold = today + timedelta(days=7)
        query = query.filter(
            Asset.needs_maintenance == True,
            Asset.next_maintenance_date != None,
            Asset.next_maintenance_date <= threshold,
            Asset.status.notin_(['Dalam Perbaikan', 'Afkir']),
            db.or_(
                Asset.last_maintenance_date.is_(None),
                Asset.last_maintenance_date < today,
                Asset.next_maintenance_date <= today
            )
        )
    elif maintenance_filter == 'yes':
        query = query.filter(Asset.needs_maintenance == True)
    elif maintenance_filter == 'no':
        query = query.filter(db.or_(Asset.needs_maintenance == False, Asset.needs_maintenance == None))

    asset_list = query.order_by(Asset.created_at.desc(), Asset.id.desc()).all()
    filtered_value = sum(a.purchase_price or 0.0 for a in asset_list)
    all_vendors = Vendor.query.filter_by(is_active=True).order_by(Vendor.name.asc()).all()
    all_sites = Site.query.filter_by(is_active=True).order_by(Site.name.asc()).all()

    return render_template(
        'assets.html',
        assets=asset_list,
        search_query=search_query,
        category_filter=category_filter,
        status_filter=status_filter,
        maintenance_filter=maintenance_filter,
        vendor_filter=vendor_filter,
        site_filter=site_filter,
        warranty_filter=warranty_filter,
        filtered_value=filtered_value,
        categories=DEFAULT_CATEGORIES,
        statuses=STATUS_CHOICES,
        vendors=all_vendors,
        sites=all_sites,
        category_custom_fields=CATEGORY_CUSTOM_FIELDS,
        today=today,
        date_today=today
    )


@assets_bp.route('/assets/create', methods=['POST'])
@login_required
@role_required('Admin', 'Staff')
def create_asset():
    """Create a new asset with photo upload, maintenance settings, warranty, depreciation, and custom fields."""
    name = request.form.get('name', '').strip()
    category = request.form.get('category', 'Tech').strip()
    purchase_date_str = request.form.get('purchase_date', '').strip()
    purchase_price_str = request.form.get('purchase_price', '0').strip()
    location = request.form.get('location', '').strip() or 'Kantor Pusat'
    status = request.form.get('status', 'Aktif').strip()
    description = request.form.get('description', '').strip()
    custom_code = request.form.get('asset_code', '').strip()

    # Maintenance inputs
    needs_maintenance_raw = request.form.get('needs_maintenance', '0').strip()
    needs_maintenance = (needs_maintenance_raw == '1')
    interval_str = request.form.get('maintenance_interval_days', '').strip()
    next_maint_date_str = request.form.get('next_maintenance_date', '').strip()

    # v2: Warranty & Depreciation
    warranty_start_str = request.form.get('warranty_start', '').strip()
    warranty_end_str = request.form.get('warranty_end', '').strip()
    useful_life_str = request.form.get('useful_life_years', '').strip()
    salvage_value_str = request.form.get('salvage_value', '0').strip()
    vendor_id_str = request.form.get('vendor_id', '').strip()
    site_id_str = request.form.get('site_id', '').strip()

    if not name:
        flash('Nama aset wajib diisi.', 'danger')
        return redirect(url_for('assets.assets'))

    # Dates parsing
    try:
        purchase_date = datetime.strptime(purchase_date_str, '%Y-%m-%d').date() if purchase_date_str else date.today()
    except ValueError:
        purchase_date = date.today()

    warranty_start = None
    if warranty_start_str:
        try:
            warranty_start = datetime.strptime(warranty_start_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    warranty_end = None
    if warranty_end_str:
        try:
            warranty_end = datetime.strptime(warranty_end_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    # Numbers parsing
    try:
        clean_price = purchase_price_str.replace('.', '').replace(',', '.').replace('Rp', '').strip()
        purchase_price = float(clean_price) if clean_price else 0.0
    except ValueError:
        purchase_price = 0.0

    useful_life_years = int(useful_life_str) if useful_life_str.isdigit() else None
    try:
        clean_salvage = salvage_value_str.replace('.', '').replace(',', '.').replace('Rp', '').strip()
        salvage_value = float(clean_salvage) if clean_salvage else 0.0
    except ValueError:
        salvage_value = 0.0

    vendor_id = int(vendor_id_str) if vendor_id_str.isdigit() else None
    site_id = int(site_id_str) if site_id_str.isdigit() else None

    # Custom fields for category
    custom_data = {}
    for cf in CATEGORY_CUSTOM_FIELDS.get(category, []):
        val = request.form.get(f'cf_{cf}', '').strip()
        if val:
            custom_data[cf] = val
    custom_fields_json = json.dumps(custom_data) if custom_data else None

    # Code generation
    if custom_code:
        if Asset.query.filter_by(asset_code=custom_code).first():
            flash(f'Kode aset "{custom_code}" sudah digunakan. Silakan gunakan kode lain atau auto-generate.', 'danger')
            return redirect(url_for('assets.assets'))
        asset_code = custom_code
    else:
        asset_code = generate_asset_code(category)

    # Maintenance interval
    maintenance_interval_days = None
    next_maintenance_date = None
    if needs_maintenance:
        try:
            maintenance_interval_days = int(interval_str) if interval_str else 90
        except ValueError:
            maintenance_interval_days = 90

        if next_maint_date_str:
            try:
                next_maintenance_date = datetime.strptime(next_maint_date_str, '%Y-%m-%d').date()
            except ValueError:
                next_maintenance_date = date.today() + timedelta(days=maintenance_interval_days)
        else:
            next_maintenance_date = date.today() + timedelta(days=maintenance_interval_days)

    photo_file = request.files.get('photo')
    saved_filename = save_uploaded_photo(photo_file)

    new_asset = Asset(
        asset_code=asset_code,
        name=name,
        category=category,
        purchase_date=purchase_date,
        purchase_price=purchase_price,
        location=location,
        status=status,
        description=description,
        image=saved_filename,
        needs_maintenance=needs_maintenance,
        maintenance_interval_days=maintenance_interval_days,
        next_maintenance_date=next_maintenance_date,
        last_maintenance_date=None,
        warranty_start=warranty_start,
        warranty_end=warranty_end,
        useful_life_years=useful_life_years,
        salvage_value=salvage_value,
        vendor_id=vendor_id,
        site_id=site_id,
        custom_fields_json=custom_fields_json
    )

    try:
        db.session.add(new_asset)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        delete_photo_file(saved_filename)
        current_app.logger.error(f"Gagal menyimpan aset baru ke database: {e}")
        flash('Terjadi kendala saat menyimpan aset ke database. Silakan periksa kembali input Anda.', 'danger')
        return redirect(url_for('assets.assets'))

    log_activity(
        'TAMBAH_ASET',
        asset_code=new_asset.asset_code,
        asset_name=new_asset.name,
        details=f"Aset baru ditambahkan ({category}, Lokasi: {location}, Nilai: Rp {purchase_price:,.0f})."
    )

    flash(f'Aset "{new_asset.name}" berhasil ditambahkan dengan kode: {new_asset.asset_code}!', 'success')
    return redirect(url_for('assets.assets'))


@assets_bp.route('/assets/<int:asset_id>/edit', methods=['POST'])
@login_required
@role_required('Admin', 'Staff')
def edit_asset(asset_id):
    """Edit existing asset details with full audit trail logging (old → new values)."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('assets.assets'))

    # Store old values for audit trail
    old_name = asset.name
    old_category = asset.category
    old_location = asset.location
    old_status = asset.status
    old_price = asset.purchase_price or 0.0

    name = request.form.get('name', '').strip()
    category = request.form.get('category', asset.category).strip()
    purchase_date_str = request.form.get('purchase_date', '').strip()
    purchase_price_str = request.form.get('purchase_price', '').strip()
    location = request.form.get('location', '').strip()
    status = request.form.get('status', asset.status).strip()
    description = request.form.get('description', '').strip()
    asset_code = request.form.get('asset_code', asset.asset_code).strip()

    needs_maintenance_raw = request.form.get('needs_maintenance', '0').strip()
    needs_maintenance = (needs_maintenance_raw == '1')
    interval_str = request.form.get('maintenance_interval_days', '').strip()
    next_maint_date_str = request.form.get('next_maintenance_date', '').strip()

    warranty_start_str = request.form.get('warranty_start', '').strip()
    warranty_end_str = request.form.get('warranty_end', '').strip()
    useful_life_str = request.form.get('useful_life_years', '').strip()
    salvage_value_str = request.form.get('salvage_value', '').strip()
    vendor_id_str = request.form.get('vendor_id', '').strip()
    site_id_str = request.form.get('site_id', '').strip()

    if not name:
        flash('Nama aset tidak boleh kosong.', 'danger')
        return redirect(url_for('assets.assets'))

    if asset_code != asset.asset_code:
        existing = Asset.query.filter_by(asset_code=asset_code).first()
        if existing:
            flash(f'Kode aset "{asset_code}" sudah terpakai oleh aset lain.', 'danger')
            return redirect(url_for('assets.assets'))
        asset.asset_code = asset_code

    if purchase_date_str:
        try:
            asset.purchase_date = datetime.strptime(purchase_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    if purchase_price_str:
        try:
            clean_price = purchase_price_str.replace('.', '').replace(',', '.').replace('Rp', '').strip()
            asset.purchase_price = float(clean_price)
        except ValueError:
            pass

    if warranty_start_str:
        try:
            asset.warranty_start = datetime.strptime(warranty_start_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    else:
        asset.warranty_start = None

    if warranty_end_str:
        try:
            asset.warranty_end = datetime.strptime(warranty_end_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    else:
        asset.warranty_end = None

    asset.useful_life_years = int(useful_life_str) if useful_life_str.isdigit() else None
    if salvage_value_str:
        try:
            clean_salvage = salvage_value_str.replace('.', '').replace(',', '.').replace('Rp', '').strip()
            asset.salvage_value = float(clean_salvage)
        except ValueError:
            pass

    asset.vendor_id = int(vendor_id_str) if vendor_id_str.isdigit() else None
    asset.site_id = int(site_id_str) if site_id_str.isdigit() else None

    # Custom fields
    custom_data = {}
    for cf in CATEGORY_CUSTOM_FIELDS.get(category, []):
        val = request.form.get(f'cf_{cf}', '').strip()
        if val:
            custom_data[cf] = val
    asset.custom_fields_json = json.dumps(custom_data) if custom_data else None

    # Maintenance
    asset.needs_maintenance = needs_maintenance
    if needs_maintenance:
        try:
            asset.maintenance_interval_days = int(interval_str) if interval_str else (asset.maintenance_interval_days or 90)
        except ValueError:
            asset.maintenance_interval_days = 90

        if next_maint_date_str:
            try:
                asset.next_maintenance_date = datetime.strptime(next_maint_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        elif not asset.next_maintenance_date:
            asset.next_maintenance_date = date.today() + timedelta(days=asset.maintenance_interval_days)
    else:
        asset.maintenance_interval_days = None
        asset.next_maintenance_date = None

    photo_file = request.files.get('photo')
    if photo_file and photo_file.filename:
        delete_photo_file(asset.image)
        new_photo_name = save_uploaded_photo(photo_file)
        if new_photo_name:
            asset.image = new_photo_name

    asset.name = name
    asset.category = category
    asset.location = location or 'Kantor Pusat'
    asset.status = status
    asset.description = description
    asset.updated_at = datetime.utcnow()

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal memperbarui aset ID {asset_id}: {e}")
        flash('Terjadi kendala saat memperbarui aset di database. Silakan periksa kembali input Anda.', 'danger')
        return redirect(url_for('assets.assets'))

    # Track audit changes old -> new
    changes = []
    if old_name != name:
        changes.append(f"Nama: '{old_name}' → '{name}'")
    if old_category != category:
        changes.append(f"Kategori: '{old_category}' → '{category}'")
    if old_status != status:
        changes.append(f"Status: '{old_status}' → '{status}'")
    if old_location != asset.location:
        changes.append(f"Lokasi: '{old_location}' → '{asset.location}'")
    if abs(old_price - (asset.purchase_price or 0.0)) > 0.01:
        changes.append(f"Nilai: Rp {old_price:,.0f} → Rp {asset.purchase_price:,.0f}")

    detail_str = "; ".join(changes) if changes else "Data aset diperbarui tanpa perubahan nilai utama."

    log_activity(
        'EDIT_ASET',
        asset_code=asset.asset_code,
        asset_name=asset.name,
        details=detail_str
    )

    # Trigger Async Notification if status changed to 'Rusak' or 'Afkir'
    if old_status != status and status in ['Rusak', 'Afkir']:
        wib_time_str = format_wib_datetime()
        status_color = "#dc2626" if status == 'Afkir' else "#d97706"
        status_badge_type = 'danger' if status == 'Afkir' else 'warning'
        rows = [
            ("Kode Aset", f"<span style='font-family: monospace; font-weight: 700; color: #0284c7;'>{asset.asset_code}</span>"),
            ("Nama Aset", f"<strong>{asset.name}</strong>"),
            ("Kategori", asset.category),
            ("Lokasi Terkini", asset.location),
            ("Status Baru", f"<span style='font-size: 11px; padding: 2px 8px; background: #fee2e2; color: {status_color}; border-radius: 4px; font-weight: 700;'>{status}</span>"),
            ("Waktu Pembaruan", f"<strong>{wib_time_str}</strong>"),
        ]
        intro_html = f"Status kondisi aset telah diubah menjadi <strong style='color: {status_color};'>{status}</strong> oleh <strong>{current_user.full_name}</strong>."
        note_text = "Harap segera menindaklanjuti pemeriksaan fisik atau menjadwalkan servis melalui menu Pemeliharaan Aset di sistem JESCA."
        html_alert = build_system_email_html(
            header_title="Peringatan Kondisi Aset Bermasalah",
            badge_text=f"Status: {status}",
            badge_type=status_badge_type,
            intro_html=intro_html,
            rows=rows,
            note_text=note_text
        )
        send_system_email(f"[PERINGATAN ASET] {asset.asset_code} - Status Diubah Menjadi {status}", html_alert)

    flash(f'Perubahan aset [{asset.asset_code}] berhasil disimpan!', 'success')
    return redirect(url_for('assets.assets'))


@assets_bp.route('/assets/<int:asset_id>/delete', methods=['POST'])
@login_required
@role_required('Admin')
def delete_asset(asset_id):
    """Delete an asset record and its image from disk (Admin only)."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('assets.assets'))

    code = asset.asset_code
    name = asset.name

    try:
        delete_photo_file(asset.image)
        db.session.delete(asset)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal menghapus aset ID {asset_id}: {e}")
        flash(f'Aset [{code}] tidak dapat dihapus karena masih terhubung dengan data riwayat/servis/pengadaan.', 'warning')
        return redirect(url_for('assets.assets'))

    log_activity(
        'HAPUS_ASET',
        asset_code=code,
        asset_name=name,
        details=f"Aset [{code}] {name} telah dihapus dari sistem oleh {current_user.username}."
    )

    flash(f'Aset [{code}] - {name} telah berhasil dihapus.', 'info')
    return redirect(url_for('assets.assets'))


@assets_bp.route('/assets/<int:asset_id>/checkout', methods=['POST'])
@login_required
@role_required('Admin', 'Staff')
def checkout_asset(asset_id):
    """Check Out (Pinjam Aset) with server-side validation against Perbaikan/Rusak/Afkir."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('assets.assets'))

    # v2: Guard against borrowing damaged / broken / retired assets
    if asset.status in ['Dalam Perbaikan', 'Afkir', 'Rusak']:
        flash(f'Aset dengan status "{asset.status}" tidak dapat dipinjam.', 'danger')
        return redirect(url_for('assets.assets'))

    # Guard: Alert if overdue for maintenance
    if asset.needs_maintenance and asset.next_maintenance_date and asset.next_maintenance_date <= date.today() and asset.status != 'Afkir':
        flash(f'Aset [{asset.asset_code}] sedang jatuh tempo pemeliharaan ({asset.next_maintenance_date.strftime("%d/%m/%Y")}). Harap lakukan servis teknisi sebelum dipinjamkan.', 'warning')

    if asset.status == 'Dipinjam':
        flash(f'Aset sedang dipinjam oleh {asset.borrower}. Selesaikan check-in terlebih dahulu.', 'warning')
        return redirect(url_for('assets.assets'))

    borrower = request.form.get('borrower', '').strip()
    notes = request.form.get('notes', '').strip()

    if not borrower:
        flash('Nama peminjam wajib diisi.', 'danger')
        return redirect(url_for('assets.assets'))

    now = datetime.utcnow()
    asset.status = 'Dipinjam'
    asset.borrower = borrower
    asset.borrow_date = now

    # Record permanent circulation log
    circ_log = AssetCirculationLog(
        asset_id=asset.id,
        borrower=borrower,
        borrow_date=now,
        checkout_by=current_user.username,
        notes=notes
    )
    try:
        db.session.add(circ_log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal memproses peminjaman aset ID {asset_id}: {e}")
        flash('Terjadi kendala saat memproses peminjaman aset ke database. Silakan coba kembali.', 'danger')
        return redirect(url_for('assets.assets'))

    log_activity(
        'CHECK_OUT',
        asset_code=asset.asset_code,
        asset_name=asset.name,
        details=f"Aset dipinjamkan kepada: {borrower}. Catatan: {notes or '-'}"
    )

    flash(f'Aset [{asset.asset_code}] berhasil dipinjamkan kepada {borrower}.', 'success')
    return redirect(url_for('assets.assets'))


@assets_bp.route('/assets/<int:asset_id>/checkin', methods=['POST'])
@login_required
@role_required('Admin', 'Staff')
def checkin_asset(asset_id):
    """Check In (Pengembalian Aset) with permanent circulation history logging."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('assets.assets'))

    prev_borrower = asset.borrower or 'Peminjam'
    new_status = request.form.get('status', 'Aktif').strip()
    return_notes = request.form.get('notes', '').strip()
    now = datetime.utcnow()

    # Track utilization days & close open circulation log
    days_borrowed = 1
    if asset.borrow_date:
        days_borrowed = max(1, (now - asset.borrow_date).days)
        asset.total_checkout_days = (asset.total_checkout_days or 0) + days_borrowed

    active_circ = AssetCirculationLog.query.filter_by(asset_id=asset.id, return_date=None)\
        .order_by(AssetCirculationLog.id.desc()).first()
    if active_circ:
        active_circ.return_date = now
        active_circ.duration_days = max(1, (now - active_circ.borrow_date).days)
        active_circ.checkin_by = current_user.username
        if return_notes:
            active_circ.notes = (active_circ.notes or '') + f" | Catatan Kembali: {return_notes}"

    asset.status = new_status
    asset.borrower = None
    asset.borrow_date = None

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal memproses pengembalian aset ID {asset_id}: {e}")
        flash('Terjadi kendala saat memproses pengembalian aset ke database. Silakan coba kembali.', 'danger')
        return redirect(url_for('assets.assets'))

    log_activity(
        'CHECK_IN',
        asset_code=asset.asset_code,
        asset_name=asset.name,
        details=f"Aset dikembalikan oleh: {prev_borrower} ({days_borrowed} hari). Status sekarang: {new_status}. Catatan: {return_notes or '-'}"
    )

    flash(f'Aset [{asset.asset_code}] berhasil dikembalikan (Status: {new_status}).', 'success')
    return redirect(url_for('assets.assets'))


@assets_bp.route('/attachments/maintenance/<filename>')
@login_required
def download_maintenance_attachment(filename):
    safe_name = secure_filename(filename)
    return send_from_directory(MAINT_ATTACHMENT_FOLDER, safe_name)


@assets_bp.route('/attachments/po/<filename>')
@login_required
def download_po_attachment(filename):
    safe_name = secure_filename(filename)
    return send_from_directory(PO_ATTACHMENT_FOLDER, safe_name)


@assets_bp.route('/assets/<int:asset_id>/transfer', methods=['POST'])
@login_required
@role_required('Admin', 'Staff')
def transfer_asset(asset_id):
    """Record permanent asset transfer between locations / sites."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('assets.assets'))

    to_location = request.form.get('to_location', '').strip()
    to_site_id_raw = request.form.get('to_site_id', '').strip()
    reason = request.form.get('reason', '').strip()

    if not to_location:
        flash('Lokasi tujuan wajib diisi.', 'danger')
        return redirect(url_for('assets.assets'))

    to_site = None
    to_site_id = None
    if to_site_id_raw.isdigit():
        to_site_id = int(to_site_id_raw)
        to_site = db.session.get(Site, to_site_id)

    from_loc = asset.location or 'Kantor Pusat'
    from_site_name = asset.site.name if asset.site else 'Pusat'

    transfer = AssetTransfer(
        asset_id=asset.id,
        from_location=from_loc,
        to_location=to_location,
        from_site=from_site_name,
        to_site=to_site.name if to_site else None,
        reason=reason,
        transferred_by=current_user.username
    )
    db.session.add(transfer)

    asset.location = to_location
    if to_site_id:
        asset.site_id = to_site_id
    asset.last_transfer_date = date.today()
    asset.last_transfer_from = from_loc

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal mentransfer aset ID {asset_id}: {e}")
        flash('Terjadi kendala saat menyimpan transfer aset. Silakan coba kembali.', 'danger')
        return redirect(url_for('assets.assets'))

    log_activity(
        'TRANSFER_ASET',
        asset_code=asset.asset_code,
        asset_name=asset.name,
        details=f"Aset dipindahkan dari '{from_loc}' ke '{to_location}'. Alasan: {reason or '-'}"
    )

    flash(f'Aset [{asset.asset_code}] berhasil ditransfer ke {to_location}.', 'success')
    return redirect(url_for('assets.assets'))


@assets_bp.route('/assets/bulk-action', methods=['POST'])
@login_required
@role_required('Admin', 'Staff')
def bulk_asset_action():
    """Bulk action on multiple assets: delete, change_status, move_category, export."""
    action = request.form.get('action', '').strip()
    asset_ids_raw = request.form.get('asset_ids', '')

    try:
        asset_ids = [int(x.strip()) for x in asset_ids_raw.split(',') if x.strip().isdigit()]
    except Exception:
        flash('Data aset tidak valid.', 'danger')
        return redirect(url_for('assets.assets'))

    if not asset_ids:
        flash('Tidak ada aset yang dipilih.', 'warning')
        return redirect(url_for('assets.assets'))

    target_assets = Asset.query.filter(Asset.id.in_(asset_ids)).all()
    count = len(target_assets)

    if action == 'delete':
        if current_user.role != 'Admin':
            flash('Hanya Administrator yang dapat menghapus aset secara massal.', 'danger')
            return redirect(url_for('assets.assets'))
        for a in target_assets:
            delete_photo_file(a.image)
            db.session.delete(a)
        db.session.commit()
        log_activity('BULK_DELETE', details=f"{count} aset dihapus secara massal oleh {current_user.username}.")
        flash(f'{count} aset berhasil dihapus dari sistem.', 'info')

    elif action == 'change_status':
        new_status = request.form.get('bulk_status', '').strip()
        if new_status not in STATUS_CHOICES:
            flash('Status yang dipilih tidak valid.', 'danger')
            return redirect(url_for('assets.assets'))
        for a in target_assets:
            a.status = new_status
        db.session.commit()
        log_activity('BULK_STATUS', details=f"Status {count} aset diubah menjadi '{new_status}'.")
        flash(f'Status {count} aset berhasil diubah ke "{new_status}".', 'success')

    elif action == 'move_category':
        new_cat = request.form.get('bulk_category', '').strip()
        valid_cats = [c['name'] for c in DEFAULT_CATEGORIES]
        if new_cat not in valid_cats:
            flash('Kategori tidak valid.', 'danger')
            return redirect(url_for('assets.assets'))
        for a in target_assets:
            a.category = new_cat
        db.session.commit()
        log_activity('BULK_CATEGORY', details=f"Kategori {count} aset dipindahkan ke '{new_cat}'.")
        flash(f'Kategori {count} aset berhasil diubah ke "{new_cat}".', 'success')

    elif action == 'export':
        output = io.StringIO()
        output.write('\ufeff')
        writer = csv.writer(output, delimiter=';')
        writer.writerow(['Kode Aset', 'Nama Aset', 'Kategori', 'Lokasi', 'Status', 'Nilai Perolehan', 'Peminjam'])
        for a in target_assets:
            writer.writerow([
                a.asset_code, a.name, a.category, a.location,
                a.status, f"{a.purchase_price:.2f}", a.borrower or '-'
            ])
        filename = f"jesca_bulk_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    return redirect(url_for('assets.assets'))


@assets_bp.route('/assets/import-csv', methods=['GET', 'POST'])
@login_required
@role_required('Admin', 'Staff')
def import_assets_csv():
    """Download CSV import template (GET) or parse and insert uploaded CSV (POST)."""
    if request.method == 'GET':
        output = io.StringIO()
        output.write('\ufeff')
        writer = csv.writer(output, delimiter=';')
        writer.writerow([
            'Nama Aset', 'Kategori', 'Lokasi', 'Tanggal Perolehan (YYYY-MM-DD)',
            'Nilai Perolehan', 'Status', 'Deskripsi', 'Perlu Maintenance (1/0)', 'Interval Hari'
        ])
        writer.writerow([
            'Laptop Dell XPS 15', 'Tech', 'Ruang IT', '2024-01-15',
            '25000000', 'Aktif', 'RAM 32GB SSD 1TB', '1', '90'
        ])
        writer.writerow([
            'Kursi Ergonomis', 'Furniture', 'Lantai 2', '2024-02-10',
            '1800000', 'Aktif', 'Warna Hitam', '0', ''
        ])
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={"Content-Disposition": "attachment; filename=template_import_jesca.csv"}
        )

    # POST: Process uploaded CSV file
    file = request.files.get('csv_file')
    if not file or file.filename == '':
        flash('File CSV wajib dipilih.', 'danger')
        return redirect(url_for('assets.assets'))

    success_count = 0
    error_rows = []

    try:
        content = file.stream.read().decode('utf-8-sig')
        stream = io.StringIO(content)
        # Support either comma or semicolon delimiter
        first_line = content.split('\n')[0]
        delimiter = ';' if ';' in first_line else ','
        stream.seek(0)
        reader = csv.DictReader(stream, delimiter=delimiter)

        for i, row in enumerate(reader, start=2):
            try:
                name = (row.get('Nama Aset') or row.get('name') or '').strip()
                if not name:
                    error_rows.append(f"Baris {i}: Nama aset kosong")
                    continue

                category = (row.get('Kategori') or row.get('category') or 'Tech').strip()
                location = (row.get('Lokasi') or row.get('location') or 'Kantor Pusat').strip()
                p_date_str = (row.get('Tanggal Perolehan (YYYY-MM-DD)') or row.get('purchase_date') or '').strip()
                try:
                    p_date = datetime.strptime(p_date_str, '%Y-%m-%d').date() if p_date_str else date.today()
                except ValueError:
                    p_date = date.today()

                p_price_str = (row.get('Nilai Perolehan') or row.get('purchase_price') or '0').strip()
                clean_price = p_price_str.replace('.', '').replace(',', '.').replace('Rp', '').strip()
                try:
                    p_price = float(clean_price) if clean_price else 0.0
                except ValueError:
                    p_price = 0.0

                status = (row.get('Status') or row.get('status') or 'Aktif').strip()
                if status not in STATUS_CHOICES:
                    status = 'Aktif'

                description = (row.get('Deskripsi') or row.get('description') or '').strip()
                maint_flag = (row.get('Perlu Maintenance (1/0)') or row.get('needs_maintenance') or '0').strip()
                needs_maint = maint_flag in ['1', 'true', 'True', 'Ya', 'ya']

                int_str = (row.get('Interval Hari') or row.get('maintenance_interval_days') or '90').strip()
                interval = int(int_str) if int_str.isdigit() else 90

                asset_code = generate_asset_code(category)

                new_asset = Asset(
                    asset_code=asset_code,
                    name=name,
                    category=category,
                    purchase_date=p_date,
                    purchase_price=p_price,
                    location=location,
                    status=status,
                    description=description,
                    needs_maintenance=needs_maint,
                    maintenance_interval_days=interval if needs_maint else None,
                    next_maintenance_date=date.today() + timedelta(days=interval) if needs_maint else None
                )
                db.session.add(new_asset)
                db.session.flush()
                success_count += 1
            except Exception as row_err:
                error_rows.append(f"Baris {i}: {str(row_err)}")

        db.session.commit()
        log_activity('IMPORT_CSV', details=f"Import CSV: {success_count} aset berhasil, {len(error_rows)} gagal.")

        if error_rows:
            flash(f'Import selesai: {success_count} aset ditambahkan. {len(error_rows)} baris dilewati: ' + ' | '.join(error_rows[:3]), 'warning')
        else:
            flash(f'Sukses! {success_count} aset berhasil diimpor ke sistem.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Gagal memproses file CSV: {str(e)}', 'danger')

    return redirect(url_for('assets.assets'))


@assets_bp.route('/assets/export/pdf')
@login_required
@role_required('Admin', 'Administrator', 'Auditor')
def export_assets_pdf():
    """Generate formal PDF asset inventory report."""
    if not HAVE_REPORTLAB:
        flash('Modul reportlab belum terinstall untuk ekspor PDF.', 'warning')
        return redirect(url_for('assets.assets'))

    assets_list = Asset.query.order_by(Asset.asset_code.asc()).all()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        topMargin=25,
        bottomMargin=25,
        leftMargin=25,
        rightMargin=25
    )
    styles = getSampleStyleSheet()
    elements = []

    title_text = "LAPORAN INVENTARIS ASET"
    sub_text = f"JESCA &bull; Jessica Assets Management System | Tanggal Cetak: {datetime.now().strftime('%d %B %Y %H:%M')} | Dicetak oleh: {current_user.full_name}"

    elements.append(Paragraph(f"<b><font size=15 color='#0f172a'>{title_text}</font></b>", styles['Normal']))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(f"<font size=8.5 color='#475569'>{sub_text}</font>", styles['Normal']))
    elements.append(Spacer(1, 14))

    table_data = [
        ['No', 'Kode Aset', 'Nama Aset', 'Kategori', 'Lokasi', 'Status', 'Nilai Perolehan', 'Nilai Buku', 'Jadwal Servis']
    ]

    for idx, a in enumerate(assets_list, 1):
        maint_str = a.next_maintenance_date.strftime('%d/%m/%Y') if a.next_maintenance_date else '-'
        table_data.append([
            str(idx),
            a.asset_code,
            a.name[:32],
            a.category,
            a.location[:18],
            a.status,
            f"Rp {a.purchase_price:,.0f}".replace(',', '.'),
            f"Rp {a.current_book_value:,.0f}".replace(',', '.'),
            maint_str
        ])

    col_widths = [26, 85, 175, 75, 95, 75, 105, 105, 75]
    pdf_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    pdf_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), rl_colors.HexColor('#1e293b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), rl_colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 7.5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor('#f8fafc')]),
        ('GRID', (0, 0), (-1, -1), 0.5, rl_colors.HexColor('#cbd5e1')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('ALIGN', (2, 0), (4, -1), 'LEFT'),
        ('ALIGN', (5, 0), (5, -1), 'CENTER'),
        ('ALIGN', (6, 0), (7, -1), 'RIGHT'),
        ('ALIGN', (8, 0), (8, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
    ]))
    elements.append(pdf_table)

    doc.build(elements)
    buf.seek(0)

    log_activity('EXPORT_PDF', details=f"Ekspor laporan inventaris PDF ({len(assets_list)} aset).")
    filename = f"jesca_inventaris_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(
        buf.getvalue(),
        mimetype='application/pdf',
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@assets_bp.route('/assets/<int:asset_id>/attachments/upload', methods=['POST'])
@login_required
@role_required('Admin', 'Staff')
def upload_attachment(asset_id):
    """Upload documents linked to an asset (manual, invoice, warranty certificate)."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('assets.assets'))

    file = request.files.get('attachment_file')
    file_type = request.form.get('file_type', 'other').strip()

    if not file or file.filename == '':
        flash('File lampiran wajib dipilih.', 'danger')
        return redirect(url_for('assets.assets'))

    if not allowed_attachment(file.filename):
        flash('Format file tidak didukung. Format diizinkan: PDF, DOCX, XLSX, JPG, PNG, TXT.', 'danger')
        return redirect(url_for('assets.assets'))

    orig_name = secure_filename(file.filename)
    ext = orig_name.rsplit('.', 1)[1].lower() if '.' in orig_name else ''
    clean_base = orig_name.rsplit('.', 1)[0][:30]
    unique_name = f"att_{asset.id}_{int(datetime.utcnow().timestamp())}_{clean_base}_{uuid.uuid4().hex[:4]}.{ext}"
    filepath = os.path.join(ATTACHMENT_FOLDER, unique_name)
    file.save(filepath)
    file_size = os.path.getsize(filepath)

    att = AssetAttachment(
        asset_id=asset.id,
        filename=unique_name,
        original_name=orig_name,
        file_type=file_type,
        file_size=file_size,
        uploaded_by=current_user.username
    )
    db.session.add(att)
    db.session.commit()

    log_activity(
        'UPLOAD_LAMPIRAN',
        asset_code=asset.asset_code,
        asset_name=asset.name,
        details=f"Dokumen '{orig_name}' ({file_type}) diupload oleh {current_user.username}."
    )

    flash(f'Dokumen "{orig_name}" berhasil dilampirkan ke aset [{asset.asset_code}].', 'success')
    return redirect(request.referrer or url_for('assets.assets'))


@assets_bp.route('/assets/<int:asset_id>/attachments/<int:att_id>/download')
@login_required
def download_attachment(asset_id, att_id):
    """Download an asset attachment."""
    att = db.session.get(AssetAttachment, att_id)
    if not att or att.asset_id != asset_id:
        flash('Lampiran tidak ditemukan.', 'danger')
        return redirect(url_for('assets.assets'))
    return send_from_directory(
        ATTACHMENT_FOLDER,
        att.filename,
        as_attachment=True,
        download_name=att.original_name
    )


@assets_bp.route('/assets/<int:asset_id>/attachments/<int:att_id>/delete', methods=['POST'])
@login_required
@role_required('Admin', 'Staff')
def delete_attachment(asset_id, att_id):
    """Delete an asset attachment."""
    att = db.session.get(AssetAttachment, att_id)
    if not att or att.asset_id != asset_id:
        flash('Lampiran tidak ditemukan.', 'danger')
        return redirect(url_for('assets.assets'))

    filepath = os.path.join(ATTACHMENT_FOLDER, att.filename)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception:
            pass

    orig_name = att.original_name
    db.session.delete(att)
    db.session.commit()

    flash(f'Lampiran "{orig_name}" berhasil dihapus.', 'info')
    return redirect(request.referrer or url_for('assets.assets'))


@assets_bp.route('/vendors')
@login_required
def vendors():
    """List vendors & suppliers with asset counts."""
    vendor_list = Vendor.query.order_by(Vendor.name.asc()).all()
    return render_template('vendors.html', vendors=vendor_list)


@assets_bp.route('/vendors/create', methods=['POST'])
@login_required
@role_required('Admin', 'Staff')
def create_vendor():
    name = request.form.get('name', '').strip()
    contact_person = request.form.get('contact_person', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    address = request.form.get('address', '').strip()
    notes = request.form.get('notes', '').strip()

    if not name:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'error', 'message': 'Nama vendor wajib diisi.'}), 400
        flash('Nama vendor wajib diisi.', 'danger')
        return redirect(url_for('assets.vendors'))

    new_v = Vendor(
        name=name,
        contact_person=contact_person,
        phone=phone,
        email=email,
        address=address,
        notes=notes,
        is_active=True
    )
    try:
        db.session.add(new_v)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal menambahkan vendor {name}: {e}")
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'error', 'message': 'Gagal menyimpan vendor ke database.'}), 500
        flash('Terjadi kendala saat menambahkan vendor. Silakan coba kembali.', 'danger')
        return redirect(url_for('assets.vendors'))

    log_activity('TAMBAH_VENDOR', details=f"Vendor baru ditambahkan: '{name}' oleh {current_user.username}.")
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success', 'vendor': new_v.to_dict()})

    flash(f'Vendor "{name}" berhasil ditambahkan!', 'success')
    return redirect(url_for('assets.vendors'))


@assets_bp.route('/vendors/<int:vendor_id>/edit', methods=['POST'])
@login_required
@role_required('Admin', 'Staff')
def edit_vendor(vendor_id):
    v = db.session.get(Vendor, vendor_id)
    if not v:
        flash('Vendor tidak ditemukan.', 'danger')
        return redirect(url_for('assets.vendors'))

    name = request.form.get('name', '').strip()
    if not name:
        flash('Nama vendor tidak boleh kosong.', 'danger')
        return redirect(url_for('assets.vendors'))

    v.name = name
    v.contact_person = request.form.get('contact_person', '').strip()
    v.phone = request.form.get('phone', '').strip()
    v.email = request.form.get('email', '').strip()
    v.address = request.form.get('address', '').strip()
    v.notes = request.form.get('notes', '').strip()
    v.is_active = bool(request.form.get('is_active'))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal memperbarui vendor ID {vendor_id}: {e}")
        flash('Terjadi kendala saat memperbarui vendor. Silakan coba kembali.', 'danger')
        return redirect(url_for('assets.vendors'))

    log_activity('EDIT_VENDOR', details=f"Data vendor '{name}' diperbarui.")
    flash(f'Vendor "{name}" berhasil diperbarui!', 'success')
    return redirect(url_for('assets.vendors'))


@assets_bp.route('/vendors/<int:vendor_id>/delete', methods=['POST'])
@login_required
@role_required('Admin')
def delete_vendor(vendor_id):
    v = db.session.get(Vendor, vendor_id)
    if not v:
        flash('Vendor tidak ditemukan.', 'danger')
        return redirect(url_for('assets.vendors'))

    v_name = v.name
    try:
        # Unlink assets referencing this vendor
        Asset.query.filter_by(vendor_id=v.id).update({'vendor_id': None})
        db.session.delete(v)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal menghapus vendor ID {vendor_id}: {e}")
        flash(f'Vendor "{v_name}" tidak dapat dihapus karena masih terhubung dengan transaksi.', 'warning')
        return redirect(url_for('assets.vendors'))

    log_activity('HAPUS_VENDOR', details=f"Vendor '{v_name}' dihapus oleh {current_user.username}.")
    flash(f'Vendor "{v_name}" berhasil dihapus.', 'info')
    return redirect(url_for('assets.vendors'))


@assets_bp.route('/sites')
@login_required
@role_required('Admin', 'Administrator')
def sites():
    site_list = Site.query.order_by(Site.name.asc()).all()
    return render_template('sites.html', sites=site_list)


@assets_bp.route('/sites/create', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator')
def create_site():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()

    if not name:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'error', 'message': 'Nama lokasi/site wajib diisi.'}), 400
        flash('Nama lokasi/site wajib diisi.', 'danger')
        return redirect(url_for('assets.sites'))

    if Site.query.filter_by(name=name).first():
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'error', 'message': f'Site "{name}" sudah terdaftar.'}), 400
        flash(f'Site "{name}" sudah terdaftar.', 'warning')
        return redirect(url_for('assets.sites'))

    s = Site(name=name, description=description, is_active=True)
    try:
        db.session.add(s)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal menambahkan site {name}: {e}")
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'error', 'message': 'Gagal menyimpan site ke database.'}), 500
        flash('Terjadi kendala saat menambahkan site. Silakan coba kembali.', 'danger')
        return redirect(url_for('assets.sites'))

    log_activity('TAMBAH_SITE', details=f"Lokasi/Site '{name}' ditambahkan.")
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success', 'site': {'id': s.id, 'name': s.name, 'description': s.description}})

    flash(f'Site "{name}" berhasil ditambahkan!', 'success')
    return redirect(url_for('assets.sites'))


@assets_bp.route('/sites/<int:site_id>/edit', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator')
def edit_site(site_id):
    s = db.session.get(Site, site_id)
    if not s:
        flash('Site tidak ditemukan.', 'danger')
        return redirect(url_for('assets.sites'))

    name = request.form.get('name', '').strip()
    if not name:
        flash('Nama site tidak boleh kosong.', 'danger')
        return redirect(url_for('assets.sites'))

    s.name = name
    s.description = request.form.get('description', '').strip()
    s.is_active = bool(request.form.get('is_active'))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal memperbarui site ID {site_id}: {e}")
        flash('Terjadi kendala saat memperbarui site. Silakan coba kembali.', 'danger')
        return redirect(url_for('assets.sites'))

    log_activity('EDIT_SITE', details=f"Data site '{name}' diperbarui.")
    flash(f'Site "{name}" berhasil diperbarui!', 'success')
    return redirect(url_for('assets.sites'))


@assets_bp.route('/sites/<int:site_id>/delete', methods=['POST'])
@login_required
@role_required('Admin')
def delete_site(site_id):
    s = db.session.get(Site, site_id)
    if not s:
        flash('Site tidak ditemukan.', 'danger')
        return redirect(url_for('assets.sites'))

    s_name = s.name
    try:
        # Unlink assets referencing this site
        Asset.query.filter_by(site_id=s.id).update({'site_id': None})
        db.session.delete(s)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal menghapus site ID {site_id}: {e}")
        flash(f'Site "{s_name}" tidak dapat dihapus karena masih terhubung dengan transaksi.', 'warning')
        return redirect(url_for('assets.sites'))

    log_activity('HAPUS_SITE', details=f"Site '{s_name}' dihapus oleh {current_user.username}.")
    flash(f'Site "{s_name}" berhasil dihapus.', 'info')
    return redirect(url_for('assets.sites'))


@assets_bp.route('/assets/export/excel')
@login_required
@role_required('Admin', 'Administrator', 'Auditor', 'Staff')
def export_assets_excel():
    """Export all asset inventory data to native Excel (.xlsx) format with auto-fit columns and professional styling."""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        flash('Modul openpyxl belum terpasang. Mengalihkan ke ekspor CSV...', 'warning')
        return redirect(url_for('assets.export_assets_csv'))

    assets_all = Asset.query.order_by(Asset.asset_code.asc()).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Inventaris Aset"

    # Styling definitions
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")  # Deep Navy Blue
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=10)
    data_font_bold = Font(name="Calibri", size=10, bold=True)

    thin_border_side = Side(style='thin', color="D1D5DB")
    thin_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)

    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    white_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

    headers = [
        'No', 'Kode Aset', 'Nama Aset', 'Kategori', 'Lokasi',
        'Tanggal Perolehan', 'Nilai Perolehan (IDR)', 'Nilai Buku (IDR)', 'Status',
        'Peminjam', 'Vendor / Supplier', 'Lokasi Cabang (Site)', 'Mulai Garansi', 'Akhir Garansi',
        'Perlu Servis Rutin', 'Interval (Hari)', 'Jadwal Servis Berikutnya', 'Keterangan'
    ]

    ws.append(headers)
    ws.row_dimensions[1].height = 26

    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border

    center_cols = {1, 2, 4, 6, 9, 13, 14, 15, 16, 17}
    currency_cols = {7, 8}

    for idx, a in enumerate(assets_all, 1):
        row_num = idx + 1
        ws.row_dimensions[row_num].height = 20
        row_fill = zebra_fill if idx % 2 == 0 else white_fill

        purchase_val = float(a.purchase_price or 0.0)
        book_val = float(a.current_book_value or 0.0)
        p_date = a.purchase_date.strftime('%d/%m/%Y') if a.purchase_date else '-'
        w_start = a.warranty_start.strftime('%d/%m/%Y') if a.warranty_start else '-'
        w_end = a.warranty_end.strftime('%d/%m/%Y') if a.warranty_end else '-'
        next_maint = a.next_maintenance_date.strftime('%d/%m/%Y') if a.next_maintenance_date else '-'
        desc = (a.description or '').replace('\r', '').replace('\n', ' ').strip() or '-'

        row_data = [
            idx,
            a.asset_code,
            a.name,
            a.category,
            a.location,
            p_date,
            purchase_val,
            book_val,
            a.status,
            a.borrower or '-',
            a.vendor.name if a.vendor else '-',
            a.site.name if a.site else '-',
            w_start,
            w_end,
            'Ya' if a.needs_maintenance else 'Tidak',
            a.maintenance_interval_days or '-',
            next_maint,
            desc
        ]

        ws.append(row_data)

        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=row_num, column=col_num)
            cell.font = data_font_bold if col_num == 2 else data_font
            cell.fill = row_fill
            cell.border = thin_border

            if col_num in currency_cols:
                cell.number_format = '#,##0'
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_num in center_cols:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    # Auto-fit column widths with padding (no '###' truncation)
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val_str = str(cell.value or '')
            if cell.number_format == '#,##0' and isinstance(cell.value, (int, float)):
                val_str = f"{int(cell.value):,}"
            max_len = max(max_len, len(val_str))
        ws.column_dimensions[col_letter].width = max(max_len + 5, 14)

    # Freeze top row
    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    log_activity('EXPORT_EXCEL', details=f"Ekspor Excel (.xlsx) {len(assets_all)} data inventaris aset.")
    filename = f"jesca_inventaris_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        buf.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@assets_bp.route('/assets/export/csv')
@login_required
@role_required('Admin', 'Administrator', 'Auditor', 'Staff')
def export_assets_csv():
    assets_all = Asset.query.order_by(Asset.asset_code.asc()).all()

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')

    writer.writerow([
        'No', 'Kode Aset', 'Nama Aset', 'Kategori', 'Lokasi',
        'Tanggal Perolehan', 'Nilai Perolehan (IDR)', 'Nilai Buku (IDR)', 'Status',
        'Peminjam', 'Vendor / Supplier', 'Lokasi Cabang (Site)', 'Mulai Garansi', 'Akhir Garansi',
        'Perlu Servis Rutin', 'Interval (Hari)', 'Jadwal Servis Berikutnya', 'Keterangan'
    ])

    for idx, a in enumerate(assets_all, 1):
        writer.writerow([
            idx,
            a.asset_code,
            a.name,
            a.category,
            a.location,
            a.purchase_date.strftime('%d/%m/%Y') if a.purchase_date else '-',
            f"{int(round(a.purchase_price or 0))}",
            f"{int(round(a.current_book_value or 0))}",
            a.status,
            a.borrower or '-',
            a.vendor.name if a.vendor else '-',
            a.site.name if a.site else '-',
            a.warranty_start.strftime('%d/%m/%Y') if a.warranty_start else '-',
            a.warranty_end.strftime('%d/%m/%Y') if a.warranty_end else '-',
            'Ya' if a.needs_maintenance else 'Tidak',
            a.maintenance_interval_days or '-',
            a.next_maintenance_date.strftime('%d/%m/%Y') if a.next_maintenance_date else '-',
            (a.description or '').replace('\r', '').replace('\n', ' ').strip() or '-'
        ])

    log_activity('EXPORT_CSV', details=f"Ekspor CSV {len(assets_all)} data inventaris aset.")
    filename = f"jesca_assets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


