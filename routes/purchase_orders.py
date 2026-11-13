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

po_bp = Blueprint('po', __name__)


@po_bp.route('/purchase-orders')
@login_required
@role_required('Admin', 'Administrator', 'Staff', 'Auditor')
def purchase_orders():
    """List purchase orders with status filtering, search, and summary badges."""
    status_filter = request.args.get('status', '').strip().upper()
    search_query = request.args.get('search', '').strip()
    from_date = request.args.get('from', '').strip()
    to_date = request.args.get('to', '').strip()

    query = PurchaseOrder.query

    # Staff can only view their own purchase orders
    if current_user.role == 'Staff':
        query = query.filter(PurchaseOrder.requested_by == current_user.username)

    if status_filter:
        query = query.filter(PurchaseOrder.status == status_filter)

    if search_query:
        s_fmt = f"%{search_query}%"
        query = query.filter(
            db.or_(
                PurchaseOrder.po_number.ilike(s_fmt),
                PurchaseOrder.title.ilike(s_fmt),
                PurchaseOrder.requested_by.ilike(s_fmt)
            )
        )

    if from_date:
        try:
            d_from = datetime.strptime(from_date, '%Y-%m-%d')
            query = query.filter(PurchaseOrder.created_at >= d_from)
        except Exception:
            pass

    if to_date:
        try:
            d_to = datetime.strptime(to_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(PurchaseOrder.created_at <= d_to)
        except Exception:
            pass

    orders = query.order_by(PurchaseOrder.created_at.desc()).all()

    # Base query for counts
    base_count = PurchaseOrder.query
    if current_user.role == 'Staff':
        base_count = base_count.filter(PurchaseOrder.requested_by == current_user.username)

    counts = {
        'total': base_count.count(),
        'draft': base_count.filter_by(status='DRAFT').count(),
        'submitted': base_count.filter_by(status='SUBMITTED').count(),
        'approved': base_count.filter_by(status='APPROVED').count(),
        'ordered': base_count.filter_by(status='ORDERED').count(),
        'received': base_count.filter_by(status='RECEIVED').count(),
        'closed': base_count.filter_by(status='CLOSED').count(),
        'rejected': base_count.filter_by(status='REJECTED').count()
    }

    return render_template(
        'purchase_orders.html',
        orders=orders,
        counts=counts,
        current_status=status_filter,
        search_query=search_query,
        from_date=from_date,
        to_date=to_date
    )


@po_bp.route('/purchase-orders/create', methods=['GET', 'POST'])
@login_required
@role_required('Admin', 'Administrator', 'Staff')
def create_purchase_order():
    """Create a new Purchase Order with dynamic items."""
    if request.method == 'GET':
        vendors = Vendor.query.filter_by(is_active=True).order_by(Vendor.name.asc()).all()
        return render_template(
            'purchase_order_form.html',
            is_edit=False,
            po=None,
            vendors=vendors,
            categories=DEFAULT_CATEGORIES
        )

    title = request.form.get('title', '').strip()
    vendor_id = request.form.get('vendor_id', '').strip() or None
    notes = request.form.get('notes', '').strip()
    action = request.form.get('action', 'save_draft').strip()

    if not title:
        flash('Judul pengajuan Purchase Order wajib diisi.', 'danger')
        return redirect(url_for('po.create_purchase_order'))

    # Extract dynamic items arrays
    item_names = request.form.getlist('item_name[]')
    categories = request.form.getlist('category[]')
    quantities = request.form.getlist('quantity[]')
    unit_prices = request.form.getlist('unit_price[]')
    specifications = request.form.getlist('specification[]')

    valid_items = []
    total_est = 0.0

    for i in range(len(item_names)):
        name = item_names[i].strip()
        if not name:
            continue
        cat = categories[i].strip() if i < len(categories) and categories[i].strip() else 'Tech'
        try:
            qty = max(1, int(quantities[i])) if i < len(quantities) else 1
        except Exception:
            qty = 1
        price = parse_currency(unit_prices[i]) if i < len(unit_prices) else 0.0
        spec = specifications[i].strip() if i < len(specifications) else ''

        subtotal = qty * price
        total_est += subtotal
        valid_items.append({
            'item_name': name,
            'category': cat,
            'quantity': qty,
            'unit_price': price,
            'specification': spec
        })

    if not valid_items:
        flash('Minimal tambahkan satu item barang yang diajukan.', 'danger')
        return redirect(url_for('po.create_purchase_order'))

    po_number = generate_po_number()
    status = 'SUBMITTED' if action == 'submit_now' else 'DRAFT'
    submitted_at = datetime.utcnow() if status == 'SUBMITTED' else None

    po = PurchaseOrder(
        po_number=po_number,
        title=title,
        status=status,
        requested_by=current_user.username,
        vendor_id=int(vendor_id) if vendor_id else None,
        notes=notes,
        estimated_total=total_est,
        submitted_at=submitted_at
    )
    db.session.add(po)
    db.session.flush()

    for item_data in valid_items:
        po_item = POItem(
            po_id=po.id,
            item_name=item_data['item_name'],
            category=item_data['category'],
            quantity=item_data['quantity'],
            unit_price=item_data['unit_price'],
            specification=item_data['specification']
        )
        db.session.add(po_item)

    db.session.commit()

    if status == 'SUBMITTED':
        log_po_history(po, 'SUBMIT', f"Pengajuan PO '{po.title}' dibuat dan diajukan ke Admin.")
        log_activity('SUBMIT_PO', details=f"PO [{po.po_number}] '{po.title}' berhasil diajukan untuk persetujuan Admin.")
        flash(f'Purchase Order [{po.po_number}] berhasil diajukan untuk persetujuan Admin!', 'success')
    else:
        log_po_history(po, 'DRAFT', f"Draft PO '{po.title}' disimpan.")
        log_activity('BUAT_PO_DRAFT', details=f"Draft PO [{po.po_number}] '{po.title}' disimpan.")
        flash(f'Draft Purchase Order [{po.po_number}] berhasil disimpan!', 'success')

    return redirect(url_for('po.purchase_order_detail', po_id=po.id))


@po_bp.route('/purchase-orders/<int:po_id>')
@login_required
@role_required('Admin', 'Administrator', 'Staff', 'Auditor')
def purchase_order_detail(po_id):
    """View detailed information, approval timeline, items, and conversion tools for a PO."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        flash('Purchase Order tidak ditemukan.', 'danger')
        return redirect(url_for('po.purchase_orders'))

    # Staff can only view their own PO
    if current_user.role == 'Staff' and po.requested_by != current_user.username:
        flash('Anda tidak memiliki izin melihat Purchase Order pengguna lain.', 'danger')
        return redirect(url_for('po.purchase_orders'))

    sites = Site.query.filter_by(is_active=True).order_by(Site.name.asc()).all()
    categories = DEFAULT_CATEGORIES

    return render_template(
        'purchase_order_detail.html',
        po=po,
        sites=sites,
        categories=categories
    )


@po_bp.route('/purchase-orders/<int:po_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('Admin', 'Administrator', 'Staff')
def edit_purchase_order(po_id):
    """Edit a PO when in DRAFT (or Admin edit if SUBMITTED)."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        flash('Purchase Order tidak ditemukan.', 'danger')
        return redirect(url_for('po.purchase_orders'))

    # Permission check
    if current_user.role == 'Staff' and po.requested_by != current_user.username:
        flash('Anda tidak memiliki hak mengedit PO ini.', 'danger')
        return redirect(url_for('po.purchase_orders'))

    # Can only edit if DRAFT, or Admin if SUBMITTED
    can_edit = (po.status == 'DRAFT') or (current_user.role in ['Admin', 'Administrator'] and po.status in ['DRAFT', 'SUBMITTED', 'REJECTED'])
    if not can_edit:
        flash(f'Purchase Order dengan status "{po.status}" tidak dapat diedit lagi.', 'warning')
        return redirect(url_for('po.purchase_order_detail', po_id=po.id))

    if request.method == 'GET':
        vendors = Vendor.query.filter_by(is_active=True).order_by(Vendor.name.asc()).all()
        return render_template(
            'purchase_order_form.html',
            is_edit=True,
            po=po,
            vendors=vendors,
            categories=DEFAULT_CATEGORIES
        )

    title = request.form.get('title', '').strip()
    vendor_id = request.form.get('vendor_id', '').strip() or None
    notes = request.form.get('notes', '').strip()
    action = request.form.get('action', 'save_draft').strip()

    if not title:
        flash('Judul PO wajib diisi.', 'danger')
        return redirect(url_for('po.edit_purchase_order', po_id=po.id))

    item_names = request.form.getlist('item_name[]')
    categories = request.form.getlist('category[]')
    quantities = request.form.getlist('quantity[]')
    unit_prices = request.form.getlist('unit_price[]')
    specifications = request.form.getlist('specification[]')

    valid_items = []
    total_est = 0.0

    for i in range(len(item_names)):
        name = item_names[i].strip()
        if not name:
            continue
        cat = categories[i].strip() if i < len(categories) and categories[i].strip() else 'Tech'
        try:
            qty = max(1, int(quantities[i])) if i < len(quantities) else 1
        except Exception:
            qty = 1
        price = parse_currency(unit_prices[i]) if i < len(unit_prices) else 0.0
        spec = specifications[i].strip() if i < len(specifications) else ''

        total_est += (qty * price)
        valid_items.append({
            'item_name': name,
            'category': cat,
            'quantity': qty,
            'unit_price': price,
            'specification': spec
        })

    if not valid_items:
        flash('Minimal satu item barang harus diisi.', 'danger')
        return redirect(url_for('po.edit_purchase_order', po_id=po.id))

    po.title = title
    po.vendor_id = int(vendor_id) if vendor_id else None
    po.notes = notes
    po.estimated_total = total_est

    if action == 'submit_now':
        po.status = 'SUBMITTED'
        po.submitted_at = datetime.utcnow()
        po.rejection_reason = None

    # Replace items
    for old_item in list(po.items):
        db.session.delete(old_item)
    db.session.flush()

    for item_data in valid_items:
        new_item = POItem(
            po_id=po.id,
            item_name=item_data['item_name'],
            category=item_data['category'],
            quantity=item_data['quantity'],
            unit_price=item_data['unit_price'],
            specification=item_data['specification']
        )
        db.session.add(new_item)

    db.session.commit()
    log_po_history(po, 'EDIT', f"Perubahan rincian PO dan estimasi total (Rp {po.estimated_total:,.0f}) disimpan.")
    log_activity('EDIT_PO', details=f"PO [{po.po_number}] diperbarui oleh {current_user.username}.")
    flash(f'Perubahan pada Purchase Order [{po.po_number}] berhasil disimpan.', 'success')
    return redirect(url_for('po.purchase_order_detail', po_id=po.id))


@po_bp.route('/purchase-orders/<int:po_id>/submit', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator', 'Staff')
def submit_purchase_order(po_id):
    """Submit a DRAFT or REJECTED PO to Admin for approval."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        flash('PO tidak ditemukan.', 'danger')
        return redirect(url_for('po.purchase_orders'))

    if current_user.role == 'Staff' and po.requested_by != current_user.username:
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('po.purchase_orders'))

    if po.status not in ['DRAFT', 'REJECTED']:
        flash(f'PO dengan status "{po.status}" tidak dapat diajukan.', 'warning')
        return redirect(url_for('po.purchase_order_detail', po_id=po.id))

    if not po.items:
        flash('PO tidak memiliki item barang. Tambahkan item sebelum mengajukan.', 'danger')
        return redirect(url_for('po.purchase_order_detail', po_id=po.id))

    po.status = 'SUBMITTED'
    po.submitted_at = datetime.utcnow()
    po.rejection_reason = None
    db.session.commit()

    log_po_history(po, 'SUBMIT', f"Diajukan kembali untuk persetujuan Admin.")
    log_activity('SUBMIT_PO', details=f"PO [{po.po_number}] diajukan oleh {current_user.username}.")

    # Async email notification for PO submission
    wib_time_str = format_wib_datetime()
    rows = [
        ("Nomor PO", f"<span style='font-family: monospace; font-weight: 700; color: #2563eb;'>{po.po_number}</span>"),
        ("Judul Pengadaan", f"<strong>{po.title}</strong>"),
        ("Pemohon", po.requested_by),
        ("Estimasi Biaya", f"<strong style='color: #0f172a;'>Rp {po.estimated_total:,.0f}</strong>".replace(',', '.')),
        ("Jumlah Item", f"{po.total_items_quantity} unit"),
        ("Waktu Pengajuan", f"<strong>{wib_time_str}</strong>"),
    ]
    intro_html = "Pengajuan Purchase Order baru telah diserahkan dan saat ini membutuhkan peninjauan serta persetujuan Administrator."
    note_text = "Silakan masuk ke sistem JESCA melalui menu Purchase Order untuk memeriksa rincian pengadaan dan menentukan persetujuan."
    html_po = build_system_email_html(
        header_title="Pengajuan Purchase Order Baru",
        badge_text="Menunggu Persetujuan",
        badge_type="primary",
        intro_html=intro_html,
        rows=rows,
        note_text=note_text
    )
    send_system_email(f"[PERLU PERSETUJUAN] PO {po.po_number} - {po.title}", html_po)

    flash(f'Purchase Order [{po.po_number}] berhasil diajukan untuk persetujuan Admin!', 'success')
    return redirect(url_for('po.purchase_order_detail', po_id=po.id))


@po_bp.route('/purchase-orders/<int:po_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_purchase_order(po_id):
    """Admin approves a submitted PO (with self-approval detection)."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        flash('PO tidak ditemukan.', 'danger')
        return redirect(url_for('po.purchase_orders'))

    if po.status != 'SUBMITTED':
        flash(f'Hanya PO dengan status SUBMITTED yang dapat disetujui (Status saat ini: {po.status}).', 'warning')
        return redirect(url_for('po.purchase_order_detail', po_id=po.id))

    is_self = (po.requested_by == current_user.username)
    po.is_self_approved = is_self
    po.status = 'APPROVED'
    po.approved_by = current_user.username
    po.approved_at = datetime.utcnow()
    po.rejection_reason = None
    db.session.commit()

    self_text = " (Self-Approved oleh Admin Pemohon)" if is_self else ""
    log_po_history(po, 'APPROVE', f"Disetujui oleh {current_user.username}{self_text}.")
    log_activity('APPROVE_PO', details=f"PO [{po.po_number}] disetujui oleh Administrator {current_user.username}{self_text}.")
    flash(f'Purchase Order [{po.po_number}] telah berhasil disetujui (Approved){self_text}!', 'success')
    return redirect(url_for('po.purchase_order_detail', po_id=po.id))


@po_bp.route('/purchase-orders/<int:po_id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_purchase_order(po_id):
    """Admin rejects a submitted PO with a mandatory reason."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        flash('PO tidak ditemukan.', 'danger')
        return redirect(url_for('po.purchase_orders'))

    if po.status != 'SUBMITTED':
        flash('Hanya PO dengan status SUBMITTED yang dapat ditolak.', 'warning')
        return redirect(url_for('po.purchase_order_detail', po_id=po.id))

    reason = request.form.get('rejection_reason', '').strip()
    if not reason:
        reason = 'Pengajuan ditolak oleh Administrator tanpa rincian spesifik.'

    po.status = 'REJECTED'
    po.approved_by = current_user.username
    po.rejection_reason = reason
    db.session.commit()

    log_po_history(po, 'REJECT', f"Ditolak oleh Admin {current_user.username}. Alasan: {reason}")
    log_activity('REJECT_PO', details=f"PO [{po.po_number}] ditolak oleh {current_user.username}. Alasan: {reason}")
    flash(f'Purchase Order [{po.po_number}] telah ditolak. Alasan: {reason}', 'warning')
    return redirect(url_for('po.purchase_order_detail', po_id=po.id))


@po_bp.route('/purchase-orders/<int:po_id>/order', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator', 'Staff')
def order_purchase_order(po_id):
    """Mark an approved PO as ORDERED with order proof upload."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        flash('PO tidak ditemukan.', 'danger')
        return redirect(url_for('po.purchase_orders'))

    if po.status != 'APPROVED':
        flash('Hanya PO dengan status APPROVED yang dapat ditandai ORDERED.', 'warning')
        return redirect(url_for('po.purchase_order_detail', po_id=po.id))

    order_notes = request.form.get('order_notes', '').strip()
    proof_file = request.files.get('order_proof')
    proof_name = None
    if proof_file and proof_file.filename:
        proof_name = save_po_attachment(proof_file)
        if proof_name:
            po.order_proof = proof_name

    po.status = 'ORDERED'
    po.ordered_at = datetime.utcnow()
    po.order_notes = order_notes
    db.session.commit()

    log_po_history(po, 'ORDER', notes=f"Telah dipesan ke vendor. Catatan: {order_notes or '-'}", attachment=po.order_proof)
    log_activity('ORDER_PO', details=f"PO [{po.po_number}] ditandai telah dipesan ke vendor oleh {current_user.username}.")
    flash(f'PO [{po.po_number}] berhasil ditandai telah dipesan ke vendor (Ordered)!', 'info')
    return redirect(url_for('po.purchase_order_detail', po_id=po.id))


@po_bp.route('/purchase-orders/<int:po_id>/receive', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator', 'Staff')
def receive_purchase_order(po_id):
    """Mark goods as RECEIVED with mandatory delivery receipt proof (Surat Jalan/BAST)."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        flash('PO tidak ditemukan.', 'danger')
        return redirect(url_for('po.purchase_orders'))

    if po.status not in ['ORDERED', 'APPROVED']:
        flash('Hanya PO yang sudah dipesan/disetujui yang dapat ditandai diterima.', 'warning')
        return redirect(url_for('po.purchase_order_detail', po_id=po.id))

    receipt_notes = request.form.get('receipt_notes', '').strip()
    proof_file = request.files.get('receipt_proof')

    if not proof_file or not proof_file.filename:
        if not po.receipt_proof:
            flash('Unggah berkas bukti penerimaan barang fisik (Surat Jalan / BAST / Foto Barang) wajib dilampirkan sebelum status dapat diubah menjadi RECEIVED.', 'danger')
            return redirect(url_for('po.purchase_order_detail', po_id=po.id))
    else:
        saved_name = save_po_attachment(proof_file)
        if saved_name:
            po.receipt_proof = saved_name

    po.status = 'RECEIVED'
    po.received_at = datetime.utcnow()
    po.receipt_notes = receipt_notes
    for item in po.items:
        item.quantity_received = item.quantity

    db.session.commit()

    log_po_history(po, 'RECEIVE', notes=f"Barang fisik tiba di lokasi. Catatan: {receipt_notes or '-'}", attachment=po.receipt_proof)
    log_activity('RECEIVE_PO', details=f"Barang untuk PO [{po.po_number}] dinyatakan telah tiba oleh {current_user.username}.")
    flash(f'Barang untuk PO [{po.po_number}] telah tiba dan bukti penerimaan tersimpan! Anda sekarang dapat mengonversi item menjadi aset resmi.', 'success')
    return redirect(url_for('po.purchase_order_detail', po_id=po.id))


@po_bp.route('/purchase-orders/<int:po_id>/cancel', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator', 'Staff')
def cancel_purchase_order(po_id):
    """Cancel a purchase order."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        flash('PO tidak ditemukan.', 'danger')
        return redirect(url_for('po.purchase_orders'))

    if current_user.role == 'Staff':
        if po.requested_by != current_user.username or po.status != 'DRAFT':
            flash('Staff hanya dapat membatalkan draft PO miliknya sendiri.', 'danger')
            return redirect(url_for('po.purchase_order_detail', po_id=po.id))
    elif po.status in ['CLOSED', 'RECEIVED']:
        flash('PO yang sudah diterima/selesai tidak dapat dibatalkan.', 'warning')
        return redirect(url_for('po.purchase_order_detail', po_id=po.id))

    po.status = 'CANCELLED'
    db.session.commit()

    log_po_history(po, 'CANCEL', f"Dibatalkan oleh {current_user.username}.")
    log_activity('CANCEL_PO', details=f"PO [{po.po_number}] dibatalkan oleh {current_user.username}.")
    flash(f'Purchase Order [{po.po_number}] telah dibatalkan.', 'info')
    return redirect(url_for('po.purchase_order_detail', po_id=po.id))


@po_bp.route('/purchase-orders/<int:po_id>/items/<int:item_id>/convert', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator', 'Staff')
def convert_po_item_to_asset(po_id, item_id):
    """
    Convert 1 unit of a received PO item into a real company asset.
    Strictly requires verified delivery proof (Surat Jalan/BAST) before conversion.
    """
    po = db.session.get(PurchaseOrder, po_id)
    item = db.session.get(POItem, item_id)

    if not po or not item or item.po_id != po.id:
        flash('Data PO atau Item tidak valid.', 'danger')
        return redirect(url_for('po.purchase_orders'))

    if po.status != 'RECEIVED':
        flash('Item hanya dapat dikonversi menjadi aset setelah PO berstatus RECEIVED (Barang Tiba).', 'warning')
        return redirect(url_for('po.purchase_order_detail', po_id=po.id))

    # Strict physical proof guard
    if not po.receipt_proof:
        flash('Barang tidak dapat dikonversi menjadi aset resmi sebelum berkas bukti penerimaan (Surat Jalan/BAST) diunggah.', 'danger')
        return redirect(url_for('po.purchase_order_detail', po_id=po.id))

    if item.remaining_to_convert <= 0:
        flash('Semua unit untuk item ini sudah dikonversi menjadi aset.', 'info')
        return redirect(url_for('po.purchase_order_detail', po_id=po.id))

    name = request.form.get('name', '').strip() or item.item_name
    category = request.form.get('category', '').strip() or item.category
    location = request.form.get('location', '').strip()
    site_id_str = request.form.get('site_id', '').strip()
    site_id = int(site_id_str) if site_id_str.isdigit() else None
    
    # Safe currency parsing to prevent unit_price inflation
    raw_price = request.form.get('purchase_price')
    purchase_price = parse_currency(raw_price) if raw_price is not None else float(item.unit_price or 0.0)

    p_date_str = request.form.get('purchase_date', '').strip()
    try:
        purchase_date = datetime.strptime(p_date_str, '%Y-%m-%d').date() if p_date_str else date.today()
    except Exception:
        purchase_date = date.today()

    description = request.form.get('description', '').strip() or (item.specification or '')

    # Maintenance optional
    needs_maintenance = request.form.get('needs_maintenance') == 'on'
    interval_days = None
    next_maint = None
    if needs_maintenance:
        try:
            interval_days = int(request.form.get('maintenance_interval_days', '90'))
            next_maint = date.today() + timedelta(days=interval_days)
        except Exception:
            interval_days = 90
            next_maint = date.today() + timedelta(days=90)

    # Optional photo upload
    photo_file = request.files.get('image')
    image_filename = save_uploaded_photo(photo_file) if photo_file else None

    # Auto-generate unique asset code
    asset_code = generate_asset_code(category)

    new_asset = Asset(
        asset_code=asset_code,
        name=name,
        category=category,
        location=location or 'Kantor Pusat',
        site_id=site_id,
        vendor_id=po.vendor_id,
        po_id=po.id,
        po_item_id=item.id,
        purchase_price=purchase_price,
        purchase_date=purchase_date,
        description=f"[Pengadaan via {po.po_number}] {description}".strip(),
        image=image_filename,
        status='Aktif',
        needs_maintenance=needs_maintenance,
        maintenance_interval_days=interval_days,
        next_maintenance_date=next_maint
    )
    db.session.add(new_asset)

    # Update item converted count
    item.converted_count = (item.converted_count or 0) + 1
    if item.converted_count >= item.quantity:
        item.is_converted = True

    # Check if all items in this PO are converted
    db.session.flush()
    if po.is_all_converted:
        po.status = 'CLOSED'
        po.closed_at = datetime.utcnow()
        log_po_history(po, 'CLOSE', f"Seluruh unit item tuntas dikonversi. PO otomatis ditutup (Closed).")
        msg = f"Aset [{new_asset.asset_code}] '{new_asset.name}' berhasil dibuat! Seluruh item PO [{po.po_number}] telah tuntas dikonversi, PO otomatis ditutup (Closed)."
    else:
        log_po_history(po, 'CONVERT_ITEM', f"Unit #{item.converted_count} '{new_asset.name}' [{new_asset.asset_code}] resmi didaftarkan.")
        msg = f"Aset [{new_asset.asset_code}] '{new_asset.name}' berhasil dibuat (Unit {item.converted_count}/{item.quantity}). Sisa {item.remaining_to_convert} unit untuk item ini."

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        delete_photo_file(image_filename)
        current_app.logger.error(f"Gagal mengonversi item PO #{item.id}: {e}")
        flash('Terjadi kendala saat menyimpan konversi aset ke database. Silakan coba kembali.', 'danger')
        return redirect(url_for('po.purchase_order_detail', po_id=po.id))

    log_activity(
        'TAMBAH_ASET_PO',
        asset_code=new_asset.asset_code,
        asset_name=new_asset.name,
        details=f"Dikonversi dari PO [{po.po_number}] Item #{item.id} (Nilai: Rp {purchase_price:,.0f}) oleh {current_user.username}."
    )
    flash(msg, 'success')
    return redirect(url_for('po.purchase_order_detail', po_id=po.id))


@po_bp.route('/purchase-orders/export/csv')
@login_required
@role_required('Admin', 'Administrator', 'Auditor')
def export_purchase_orders_csv():
    """Export all purchase orders as CSV."""
    query = PurchaseOrder.query.order_by(PurchaseOrder.created_at.desc())
    if current_user.role == 'Staff':
        query = query.filter(PurchaseOrder.requested_by == current_user.username)

    orders = query.all()

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')
    writer.writerow([
        'No', 'Nomor PO', 'Judul Pengadaan', 'Status', 'Pemohon', 'Disetujui Oleh',
        'Vendor / Rekanan', 'Estimasi Nilai Total (IDR)', 'Jumlah Item', 'Tanggal Pengajuan',
        'Tanggal Disetujui', 'Tanggal Dipesan', 'Tanggal Diterima', 'Tanggal Selesai'
    ])

    for idx, o in enumerate(orders, 1):
        writer.writerow([
            idx,
            o.po_number,
            o.title,
            o.status,
            o.requested_by,
            o.approved_by or '-',
            o.vendor.name if o.vendor else '-',
            f"{int(round(o.estimated_total or 0))}",
            o.total_items_quantity,
            o.created_at.strftime('%Y-%m-%d %H:%M') if o.created_at else '-',
            o.approved_at.strftime('%Y-%m-%d %H:%M') if o.approved_at else '-',
            o.ordered_at.strftime('%Y-%m-%d %H:%M') if o.ordered_at else '-',
            o.received_at.strftime('%Y-%m-%d %H:%M') if o.received_at else '-',
            o.closed_at.strftime('%Y-%m-%d %H:%M') if o.closed_at else '-'
        ])

    log_activity('EXPORT_PO_CSV', details=f"Ekspor CSV {len(orders)} data Purchase Order.")
    filename = f"jesca_purchase_orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@po_bp.route('/purchase-orders/export/pdf')
@login_required
@role_required('Admin', 'Administrator', 'Auditor')
def export_purchase_orders_pdf():
    """Generate formal PDF report of all purchase orders."""
    if not HAVE_REPORTLAB:
        flash('Modul reportlab belum terinstall untuk ekspor PDF.', 'warning')
        return redirect(url_for('po.purchase_orders'))

    query = PurchaseOrder.query.order_by(PurchaseOrder.created_at.desc())
    if current_user.role == 'Staff':
        query = query.filter(PurchaseOrder.requested_by == current_user.username)

    orders = query.all()

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

    title_text = "REKAPITULASI PURCHASE ORDER"
    sub_text = f"JESCA &bull; Jessica Assets Management System | Tanggal Cetak: {datetime.now().strftime('%d %B %Y %H:%M')} | Dicetak oleh: {current_user.full_name}"

    elements.append(Paragraph(f"<b><font size=15 color='#0f172a'>{title_text}</font></b>", styles['Normal']))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(f"<font size=8.5 color='#475569'>{sub_text}</font>", styles['Normal']))
    elements.append(Spacer(1, 14))

    table_data = [
        ['No', 'Nomor PO', 'Judul Pengadaan', 'Pemohon', 'Vendor', 'Status', 'Total Item', 'Estimasi Nilai', 'Tanggal']
    ]

    for idx, o in enumerate(orders, 1):
        table_data.append([
            str(idx),
            o.po_number,
            o.title[:32],
            o.requested_by,
            (o.vendor.name if o.vendor else '-')[:22],
            o.status,
            str(o.total_items_quantity),
            f"Rp {o.estimated_total:,.0f}".replace(',', '.'),
            o.created_at.strftime('%d/%m/%Y') if o.created_at else '-'
        ])

    col_widths = [26, 95, 175, 75, 115, 75, 60, 95, 75]
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
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
        ('TOPPADDING', (0, 0), (-1, -1), 4.5),
    ]))
    elements.append(pdf_table)

    doc.build(elements)
    buf.seek(0)

    log_activity('EXPORT_PO_PDF', details=f"Ekspor PDF rekapitulasi {len(orders)} Purchase Order.")
    filename = f"jesca_po_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(
        buf.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@po_bp.route('/purchase-orders/<int:po_id>/print')
@login_required
@role_required('Admin', 'Administrator', 'Staff', 'Auditor')
def print_purchase_order_pdf(po_id):
    """Generate formal individual Purchase Order sheet in PDF format."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        flash('PO tidak ditemukan.', 'danger')
        return redirect(url_for('po.purchase_orders'))

    if not HAVE_REPORTLAB:
        flash('Modul reportlab belum terinstall.', 'warning')
        return redirect(url_for('po.purchase_order_detail', po_id=po.id))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=25,
        bottomMargin=25,
        leftMargin=25,
        rightMargin=25
    )
    styles = getSampleStyleSheet()
    elements = []

    # Header
    elements.append(Paragraph(f"<b><font size=16 color='#0284c7'>JESCA — PURCHASE ORDER RESMI</font></b>", styles['Normal']))
    elements.append(Paragraph(f"<b><font size=11 color='#1e293b'>Nomor: {po.po_number}</font></b>", styles['Normal']))
    elements.append(Paragraph(f"<font size=8 color='#64748b'>Status: <b>{po.status}</b> | Tanggal Terbit: {po.created_at.strftime('%d %B %Y') if po.created_at else '-'}</font>", styles['Normal']))
    elements.append(Spacer(1, 12))

    # Meta table (Vendor & Requester Info)
    meta_data = [
        [
            Paragraph(f"<b>Diterbitkan Oleh:</b><br/>{current_user.full_name}<br/>Pemohon: {po.requested_by}<br/>Disetujui: {po.approved_by or '-'}", styles['Normal']),
            Paragraph(f"<b>Vendor / Supplier:</b><br/><b>{po.vendor.name if po.vendor else 'Belum ditentukan'}</b><br/>Kontak: {po.vendor.contact_person if po.vendor and po.vendor.contact_person else '-'}<br/>Telp: {po.vendor.phone if po.vendor and po.vendor.phone else '-'}", styles['Normal'])
        ]
    ]
    meta_table = Table(meta_data, colWidths=[270, 270])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), rl_colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, rl_colors.HexColor('#cbd5e1')),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 14))

    # Items table
    item_rows = [
        ['No', 'Nama Barang', 'Kategori', 'Qty', 'Harga Satuan (IDR)', 'Total (IDR)']
    ]
    for idx, itm in enumerate(po.items, 1):
        item_rows.append([
            str(idx),
            Paragraph(f"<b>{itm.item_name}</b><br/><font size=7 color='#64748b'>{itm.specification or '-'}</font>", styles['Normal']),
            itm.category,
            str(itm.quantity),
            f"Rp {itm.unit_price:,.0f}".replace(',', '.'),
            f"Rp {itm.total_price:,.0f}".replace(',', '.')
        ])

    item_rows.append([
        '', '', '', '', Paragraph("<b>TOTAL ESTIMASI:</b>", styles['Normal']),
        Paragraph(f"<b>Rp {po.total_calculated:,.0f}</b>".replace(',', '.'), styles['Normal'])
    ])

    items_table = Table(item_rows, colWidths=[30, 220, 70, 40, 90, 90], repeatRows=1)
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), rl_colors.HexColor('#0284c7')),
        ('TEXTCOLOR', (0, 0), (-1, 0), rl_colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -2), 0.5, rl_colors.HexColor('#cbd5e1')),
        ('LINEBELOW', (0, -1), (-1, -1), 1, rl_colors.HexColor('#0284c7')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('ALIGN', (4, 1), (5, -1), 'RIGHT'),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 20))

    if po.notes:
        elements.append(Paragraph(f"<b>Catatan Tambahan:</b> {po.notes}", styles['Normal']))
        elements.append(Spacer(1, 14))

    # Signatures
    sig_data = [
        [
            Paragraph(f"Diajukan Oleh,<br/><br/><br/><b>({po.requested_by})</b><br/>Staff Pemohon", styles['Normal']),
            Paragraph(f"Disetujui Oleh,<br/><br/><br/><b>({po.approved_by or '..............................'})</b><br/>Administrator", styles['Normal']),
            Paragraph("Diterima Vendor,<br/><br/><br/><b>(..............................)</b><br/>Tanda Tangan & Cap", styles['Normal'])
        ]
    ]
    sig_table = Table(sig_data, colWidths=[180, 180, 180])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(sig_table)

    doc.build(elements)
    buf.seek(0)

    log_activity('PRINT_PO', details=f"Cetak PDF dokumen resmi PO [{po.po_number}].")
    filename = f"PO_{po.po_number.replace('/', '_')}.pdf"
    return Response(
        buf.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'inline; filename={filename}'}
    )


