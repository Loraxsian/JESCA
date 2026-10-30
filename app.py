import os
import re
import csv
import io
import json
import uuid
import shutil
import secrets
from functools import wraps
from datetime import datetime, date, timedelta
from urllib.parse import quote

from flask import (
    Flask, render_template, request, redirect, url_for, flash, jsonify, Response, send_from_directory, session
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, login_required, logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# Optional QR Code library
try:
    import qrcode
    HAVE_QRCODE = True
except ImportError:
    HAVE_QRCODE = False

# Optional PDF export
try:
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    HAVE_REPORTLAB = True
except ImportError:
    HAVE_REPORTLAB = False

# Optional background scheduler
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    HAVE_SCHEDULER = True
except ImportError:
    HAVE_SCHEDULER = False

# ==========================================
# Application Configuration
# ==========================================
app = Flask(__name__)

# Base directories
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
AVATAR_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'avatars')
ATTACHMENT_FOLDER = os.path.join(BASE_DIR, 'static', 'attachments')
PO_ATTACHMENT_FOLDER = os.path.join(BASE_DIR, 'static', 'attachments', 'po')
MAINT_ATTACHMENT_FOLDER = os.path.join(BASE_DIR, 'static', 'attachments', 'maintenance')
BACKUP_FOLDER = os.path.join(BASE_DIR, 'backups')
QRCODE_FOLDER = os.path.join(BASE_DIR, 'static', 'qrcodes')

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(AVATAR_FOLDER, exist_ok=True)
os.makedirs(ATTACHMENT_FOLDER, exist_ok=True)
os.makedirs(PO_ATTACHMENT_FOLDER, exist_ok=True)
os.makedirs(MAINT_ATTACHMENT_FOLDER, exist_ok=True)
os.makedirs(BACKUP_FOLDER, exist_ok=True)
os.makedirs(QRCODE_FOLDER, exist_ok=True)

# App configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'jesca-super-secret-key-change-in-production-2024')
db_path = os.path.join(DATA_DIR, 'jesca.db')
env_db_url = os.environ.get('DATABASE_URL')
if env_db_url and env_db_url.startswith('sqlite:///data/'):
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
elif env_db_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = env_db_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # Max 5MB upload
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config['SESSION_REFRESH_EACH_REQUEST'] = True

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
ALLOWED_ATTACHMENT_EXTENSIONS = {'pdf', 'docx', 'doc', 'jpg', 'jpeg', 'png', 'xlsx', 'xls', 'txt'}

# Category-specific custom fields
CATEGORY_CUSTOM_FIELDS = {
    'Tech': ['serial_number', 'ip_address', 'mac_address', 'os_version'],
    'Vehicle': ['plate_number', 'chassis_number', 'bpkb_number', 'color'],
    'Tools': ['serial_number', 'power_watt'],
    'Furniture': ['material', 'color'],
    'Office': ['serial_number', 'model_number'],
}

# Extensions initialization
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Silakan login terlebih dahulu untuk mengakses sistem JESCA.'
login_manager.login_message_category = 'warning'

# Category Prefix Mapping for Auto-Coding
CATEGORY_PREFIX_MAP = {
    'Tech': 'Tech',
    'Tools': 'Tools',
    'Furniture': 'Furn',
    'Vehicle': 'Vehicle',
    'Office': 'Office',
    'Elektronik': 'Elek',
    'Mesin': 'Mesin'
}

DEFAULT_CATEGORIES = [
    {'name': 'Tech', 'label': 'Teknologi & IT', 'prefix': 'Tech', 'icon': 'bi-laptop'},
    {'name': 'Tools', 'label': 'Peralatan & Perkakas', 'prefix': 'Tools', 'icon': 'bi-tools'},
    {'name': 'Furniture', 'label': 'Furnitur & Perabot', 'prefix': 'Furn', 'icon': 'bi-lamp'},
    {'name': 'Vehicle', 'label': 'Kendaraan Operasional', 'prefix': 'Vehicle', 'icon': 'bi-car-front'},
    {'name': 'Office', 'label': 'Perlengkapan Kantor', 'prefix': 'Office', 'icon': 'bi-printer'},
]

STATUS_CHOICES = ['Aktif', 'Dipinjam', 'Dalam Perbaikan', 'Rusak', 'Afkir']
ROLE_CHOICES = ['Admin', 'Staff', 'Auditor', 'Teknisi']


# ==========================================
# Database Models
# ==========================================
class Site(db.Model):
    """Physical location / branch that holds assets."""
    __tablename__ = 'sites'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description or '',
            'is_active': self.is_active,
            'asset_count': Asset.query.filter_by(site_id=self.id).count() if 'Asset' in globals() else 0
        }


class Vendor(db.Model):
    """Supplier / vendor for asset procurement."""
    __tablename__ = 'vendors'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    contact_person = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'contact_person': self.contact_person or '',
            'phone': self.phone or '',
            'email': self.email or '',
            'address': self.address or '',
            'notes': self.notes or '',
            'is_active': self.is_active,
            'asset_count': Asset.query.filter_by(vendor_id=self.id).count() if 'Asset' in globals() else 0
        }


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), default='Administrator')
    role = db.Column(db.String(30), default='Admin')  # Admin, Staff, Auditor, Teknisi
    profile_image = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # v2: security fields
    force_password_change = db.Column(db.Boolean, default=False)
    api_key = db.Column(db.String(64), nullable=True, unique=True, index=True)
    last_login = db.Column(db.DateTime, nullable=True)
    failed_login_count = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'full_name': self.full_name,
            'role': self.role,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else ''
        }


class Asset(db.Model):
    __tablename__ = 'assets'

    id = db.Column(db.Integer, primary_key=True)
    asset_code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=False, index=True)
    purchase_date = db.Column(db.Date, nullable=False, default=date.today)
    purchase_price = db.Column(db.Float, default=0.0)
    location = db.Column(db.String(100), default='Kantor Pusat')
    status = db.Column(db.String(50), default='Aktif')  # Aktif, Dipinjam, Dalam Perbaikan, Rusak, Afkir
    description = db.Column(db.Text, nullable=True)
    image = db.Column(db.String(255), nullable=True)  # filename in static/uploads
    borrower = db.Column(db.String(100), nullable=True)  # Current borrower name
    borrow_date = db.Column(db.DateTime, nullable=True)  # Date when borrowed

    # Maintenance Scheduling
    needs_maintenance = db.Column(db.Boolean, default=False)
    maintenance_interval_days = db.Column(db.Integer, nullable=True)  # e.g., 30, 90, 180, 365
    next_maintenance_date = db.Column(db.Date, nullable=True)
    last_maintenance_date = db.Column(db.Date, nullable=True)

    # v2: Warranty
    warranty_start = db.Column(db.Date, nullable=True)
    warranty_end = db.Column(db.Date, nullable=True)

    # v2: Depreciation (straight-line)
    useful_life_years = db.Column(db.Integer, nullable=True)
    salvage_value = db.Column(db.Float, default=0.0)

    # v2: Utilization tracking
    total_checkout_days = db.Column(db.Integer, default=0)

    # v2: Custom fields (JSON string)
    custom_fields_json = db.Column(db.Text, nullable=True)

    # v2: Relations
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendors.id'), nullable=True)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=True)
    po_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=True)
    po_item_id = db.Column(db.Integer, db.ForeignKey('po_items.id'), nullable=True)

    # Relationships to models
    vendor = db.relationship('Vendor', backref='assets', lazy=True)
    site = db.relationship('Site', backref='assets', lazy=True)
    purchase_order = db.relationship('PurchaseOrder', backref='assets', foreign_keys=[po_id], lazy=True)
    po_item = db.relationship('POItem', backref='assets', foreign_keys=[po_item_id], lazy=True)

    # v2: Transfer tracking
    last_transfer_date = db.Column(db.Date, nullable=True)
    last_transfer_from = db.Column(db.String(100), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    attachments = db.relationship('AssetAttachment', backref='asset', lazy=True, cascade='all, delete-orphan')
    transfers = db.relationship('AssetTransfer', backref='asset', lazy=True, cascade='all, delete-orphan')

    @property
    def custom_fields(self):
        """Return parsed custom fields dict."""
        if self.custom_fields_json:
            try:
                return json.loads(self.custom_fields_json)
            except Exception:
                return {}
        return {}

    @property
    def current_book_value(self):
        """Straight-line depreciation: (cost - salvage) / useful_life_years."""
        if not self.useful_life_years or self.useful_life_years <= 0:
            return self.purchase_price or 0.0
        if not self.purchase_date:
            return self.purchase_price or 0.0
        
        # Jika tanggal perolehan hari ini atau di masa depan, belum ada penyusutan
        if self.purchase_date >= date.today():
            return self.purchase_price or 0.0

        years_elapsed = (date.today() - self.purchase_date).days / 365.25
        salvage = self.salvage_value or 0.0
        cost = self.purchase_price or 0.0
        annual_dep = (cost - salvage) / self.useful_life_years
        book_value = cost - (annual_dep * years_elapsed)
        
        # Nilai buku tidak boleh lebih besar dari harga beli dan tidak boleh lebih kecil dari nilai residu
        return round(min(cost, max(book_value, salvage)), 2)

    @property
    def warranty_status(self):
        """Returns warranty status dict or None."""
        if not self.warranty_end:
            return None
        today = date.today()
        days_left = (self.warranty_end - today).days
        if days_left < 0:
            return {'status': 'expired', 'days': days_left, 'label': f'Expired {-days_left} hari lalu', 'color': 'danger'}
        elif days_left <= 30:
            return {'status': 'expiring', 'days': days_left, 'label': f'Berakhir {days_left} hari lagi', 'color': 'warning'}
        else:
            return {'status': 'active', 'days': days_left, 'label': f'Aktif ({days_left} hari)', 'color': 'success'}

    def to_dict(self):
        today = date.today()
        days_to_maint = None
        is_overdue = False
        if self.needs_maintenance and self.next_maintenance_date:
            days_to_maint = (self.next_maintenance_date - today).days
            is_overdue = days_to_maint < 0

        return {
            'id': self.id,
            'asset_code': self.asset_code,
            'name': self.name,
            'category': self.category,
            'purchase_date': self.purchase_date.strftime('%Y-%m-%d') if self.purchase_date else '',
            'purchase_price': self.purchase_price,
            'location': self.location,
            'status': self.status,
            'description': self.description or '',
            'image': self.image or '',
            'image_url': f"/static/uploads/{self.image}" if self.image else None,
            'borrower': self.borrower or '',
            'borrow_date': self.borrow_date.strftime('%Y-%m-%d %H:%M') if self.borrow_date else '',
            'needs_maintenance': bool(self.needs_maintenance),
            'maintenance_interval_days': self.maintenance_interval_days,
            'next_maintenance_date': self.next_maintenance_date.strftime('%Y-%m-%d') if self.next_maintenance_date else '',
            'last_maintenance_date': self.last_maintenance_date.strftime('%Y-%m-%d') if self.last_maintenance_date else '',
            'days_to_maintenance': days_to_maint,
            'is_overdue': is_overdue,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            # v2 fields
            'warranty_start': self.warranty_start.strftime('%Y-%m-%d') if self.warranty_start else '',
            'warranty_end': self.warranty_end.strftime('%Y-%m-%d') if self.warranty_end else '',
            'warranty_status': self.warranty_status,
            'useful_life_years': self.useful_life_years,
            'salvage_value': self.salvage_value or 0.0,
            'current_book_value': self.current_book_value,
            'total_checkout_days': self.total_checkout_days or 0,
            'custom_fields': self.custom_fields,
            'vendor_id': self.vendor_id,
            'vendor_name': self.vendor.name if self.vendor else '',
            'site_id': self.site_id,
            'site_name': self.site.name if self.site else '',
            'last_transfer_date': self.last_transfer_date.strftime('%Y-%m-%d') if self.last_transfer_date else '',
            'last_transfer_from': self.last_transfer_from or '',
            'po_id': self.po_id,
            'po_number': self.purchase_order.po_number if self.purchase_order else ''
        }


class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True)
    username = db.Column(db.String(80), nullable=False, default='System')
    action = db.Column(db.String(50), nullable=False)
    asset_code = db.Column(db.String(50), nullable=True)
    asset_name = db.Column(db.String(150), nullable=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'action': self.action,
            'asset_code': self.asset_code or '',
            'asset_name': self.asset_name or '',
            'details': self.details or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else ''
        }


class AssetAttachment(db.Model):
    """File attachments linked to an asset (invoice, manual, certificate, etc.)."""
    __tablename__ = 'asset_attachments'

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)        # stored filename
    original_name = db.Column(db.String(255), nullable=False)  # original upload name
    file_type = db.Column(db.String(50), default='other')       # manual/invoice/certificate/other
    file_size = db.Column(db.Integer, nullable=True)            # bytes
    uploaded_by = db.Column(db.String(80), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


class AssetTransfer(db.Model):
    """Record of permanent asset location/site transfers."""
    __tablename__ = 'asset_transfers'

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    from_location = db.Column(db.String(100), nullable=False)
    to_location = db.Column(db.String(100), nullable=False)
    from_site = db.Column(db.String(100), nullable=True)
    to_site = db.Column(db.String(100), nullable=True)
    reason = db.Column(db.Text, nullable=True)
    transferred_by = db.Column(db.String(80), nullable=False)
    transfer_date = db.Column(db.DateTime, default=datetime.utcnow)


class PurchaseOrder(db.Model):
    """Purchase Order model for procurement and digital approval workflow."""
    __tablename__ = 'purchase_orders'

    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default='DRAFT', index=True)  # DRAFT, SUBMITTED, APPROVED, REJECTED, ORDERED, RECEIVED, CLOSED, CANCELLED
    requested_by = db.Column(db.String(80), nullable=False)
    approved_by = db.Column(db.String(80), nullable=True)
    rejection_reason = db.Column(db.Text, nullable=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendors.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    estimated_total = db.Column(db.Float, default=0.0)

    # Attachments & Proofs
    order_proof = db.Column(db.String(255), nullable=True)
    order_notes = db.Column(db.Text, nullable=True)
    receipt_proof = db.Column(db.String(255), nullable=True)
    receipt_notes = db.Column(db.Text, nullable=True)
    is_self_approved = db.Column(db.Boolean, default=False)

    submitted_at = db.Column(db.DateTime, nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    ordered_at = db.Column(db.DateTime, nullable=True)
    received_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    vendor = db.relationship('Vendor', backref='purchase_orders', lazy=True)
    items = db.relationship('POItem', backref='purchase_order', lazy=True, cascade='all, delete-orphan')

    @property
    def total_calculated(self):
        return sum(item.total_price for item in self.items)

    @property
    def total_items_quantity(self):
        return sum(item.quantity or 0 for item in self.items)

    @property
    def total_converted_assets(self):
        return sum(item.converted_count or 0 for item in self.items)

    @property
    def is_all_converted(self):
        if not self.items:
            return False
        return all(item.converted_count >= item.quantity for item in self.items)

    def to_dict(self):
        return {
            'id': self.id,
            'po_number': self.po_number,
            'title': self.title,
            'status': self.status,
            'requested_by': self.requested_by,
            'approved_by': self.approved_by or '',
            'rejection_reason': self.rejection_reason or '',
            'vendor_id': self.vendor_id,
            'vendor_name': self.vendor.name if self.vendor else '',
            'notes': self.notes or '',
            'estimated_total': self.estimated_total or 0.0,
            'total_calculated': self.total_calculated,
            'total_items_quantity': self.total_items_quantity,
            'total_converted_assets': self.total_converted_assets,
            'is_all_converted': self.is_all_converted,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
            'submitted_at': self.submitted_at.strftime('%Y-%m-%d %H:%M') if self.submitted_at else '',
            'approved_at': self.approved_at.strftime('%Y-%m-%d %H:%M') if self.approved_at else '',
            'ordered_at': self.ordered_at.strftime('%Y-%m-%d %H:%M') if self.ordered_at else '',
            'received_at': self.received_at.strftime('%Y-%m-%d %H:%M') if self.received_at else '',
            'closed_at': self.closed_at.strftime('%Y-%m-%d %H:%M') if self.closed_at else ''
        }


class POItem(db.Model):
    """Individual line items requested in a Purchase Order."""
    __tablename__ = 'po_items'

    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    item_name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), default='Tech')
    quantity = db.Column(db.Integer, default=1)
    quantity_received = db.Column(db.Integer, default=0)
    unit_price = db.Column(db.Float, default=0.0)
    specification = db.Column(db.Text, nullable=True)
    converted_count = db.Column(db.Integer, default=0)  # how many assets converted from this item
    is_converted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def total_price(self):
        return (self.quantity or 0) * (self.unit_price or 0.0)

    @property
    def remaining_to_convert(self):
        return max(0, (self.quantity or 0) - (self.converted_count or 0))

    def to_dict(self):
        return {
            'id': self.id,
            'po_id': self.po_id,
            'item_name': self.item_name,
            'category': self.category,
            'quantity': self.quantity,
            'quantity_received': self.quantity_received,
            'unit_price': self.unit_price,
            'total_price': self.total_price,
            'specification': self.specification or '',
            'converted_count': self.converted_count or 0,
            'remaining_to_convert': self.remaining_to_convert,
            'is_converted': self.is_converted
        }


class PurchaseOrderHistory(db.Model):
    """Immutable audit trail for every Purchase Order status change."""
    __tablename__ = 'po_histories'

    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    to_status = db.Column(db.String(30), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    attachment = db.Column(db.String(255), nullable=True)
    performed_by = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    po = db.relationship('PurchaseOrder', backref=db.backref('history_entries', lazy=True, order_by='PurchaseOrderHistory.created_at.desc()'))


class MaintenanceRecord(db.Model):
    """Detailed log of each physical maintenance / servicing event performed on an asset."""
    __tablename__ = 'maintenance_records'

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    service_type = db.Column(db.String(100), default='Rutin')
    action_taken = db.Column(db.Text, nullable=False)
    cost = db.Column(db.Float, default=0.0)
    proof_file = db.Column(db.String(255), nullable=True)
    performed_by = db.Column(db.String(80), nullable=False)
    service_date = db.Column(db.Date, default=date.today)
    next_service_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    asset = db.relationship('Asset', backref=db.backref('maintenance_records', lazy=True, order_by='MaintenanceRecord.service_date.desc()'))


class AssetCirculationLog(db.Model):
    """Permanent log of all asset check-outs and check-ins (historical record)."""
    __tablename__ = 'asset_circulation_logs'

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    borrower = db.Column(db.String(100), nullable=False)
    borrow_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    return_date = db.Column(db.DateTime, nullable=True)
    duration_days = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text, nullable=True)
    checkout_by = db.Column(db.String(80), nullable=False)
    checkin_by = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    asset = db.relationship('Asset', backref=db.backref('circulation_logs', lazy=True, order_by='AssetCirculationLog.borrow_date.desc()'))


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ==========================================
# Decorators & Permissions
# ==========================================
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['Admin', 'Administrator']:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Forbidden', 'message': 'Fitur ini hanya untuk Administrator'}), 403
            flash('Akses ditolak. Fitur ini hanya dapat diakses oleh Administrator.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    """Flexible role-based access control — returns 403 JSON for API calls."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({'error': 'Unauthorized', 'message': 'Login diperlukan'}), 401
                return redirect(url_for('login'))
            if current_user.role not in roles:
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({
                        'error': 'Forbidden',
                        'message': f'Akses ditolak. Role yang dibutuhkan: {", ".join(roles)}',
                        'your_role': current_user.role
                    }), 403
                flash(f'Akses ditolak. Fitur ini hanya untuk: {", ".join(roles)}.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator


def api_key_required(f):
    """Decorator for REST API endpoints using X-API-Key header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({'error': 'Unauthorized', 'message': 'API key diperlukan. Gunakan header: X-API-Key'}), 401
        user = User.query.filter_by(api_key=api_key).first()
        if not user or not user.is_active:
            return jsonify({'error': 'Forbidden', 'message': 'API key tidak valid atau akun nonaktif'}), 403
        return f(*args, **kwargs)
    return decorated


# ==========================================
# Activity Logging & Helper Functions
# ==========================================
def validate_password(password):
    """Returns (is_valid, error_message). Min 8 chars, at least 1 letter + 1 digit."""
    if len(password) < 8:
        return False, 'Password minimal 8 karakter.'
    if not re.search(r'[a-zA-Z]', password):
        return False, 'Password harus mengandung minimal satu huruf.'
    if not re.search(r'[0-9]', password):
        return False, 'Password harus mengandung minimal satu angka.'
    return True, None


def get_overdue_returns():
    """Assets borrowed for more than 7 days without check-in."""
    threshold = datetime.utcnow() - timedelta(days=7)
    return Asset.query.filter(
        Asset.status == 'Dipinjam',
        Asset.borrow_date != None,
        Asset.borrow_date <= threshold
    ).all()


def log_activity(action, asset_code=None, asset_name=None, details=None):
    """Save an activity log record into database."""
    try:
        username = current_user.username if (current_user and current_user.is_authenticated) else 'System'
        user_id = current_user.id if (current_user and current_user.is_authenticated) else None
        log = ActivityLog(
            user_id=user_id,
            username=username,
            action=action,
            asset_code=asset_code,
            asset_name=asset_name,
            details=details,
            created_at=datetime.utcnow()
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error saving activity log: {e}")


def get_maintenance_notifications():
    """Finds all assets that have maintenance scheduled within 7 days or are overdue."""
    today = date.today()
    threshold = today + timedelta(days=7)

    due_assets = Asset.query.filter(
        Asset.needs_maintenance == True,
        Asset.next_maintenance_date != None,
        Asset.next_maintenance_date <= threshold,
        Asset.status != 'Afkir'  # v2: skip retired assets
    ).order_by(Asset.next_maintenance_date.asc()).all()

    notifications = []
    for a in due_assets:
        days_left = (a.next_maintenance_date - today).days
        is_overdue = days_left < 0
        if is_overdue:
            status_text = f"Terlewat {-days_left} hari!"
            badge_class = "danger"
        elif days_left == 0:
            status_text = "Hari ini!"
            badge_class = "danger"
        elif days_left <= 3:
            status_text = f"Sisa {days_left} hari"
            badge_class = "warning"
        else:
            status_text = f"Sisa {days_left} hari"
            badge_class = "info"

        notifications.append({
            'asset': a,
            'days_left': days_left,
            'is_overdue': is_overdue,
            'status_text': status_text,
            'badge_class': badge_class
        })
    return notifications


# Context processor so alerts are automatically available in all templates
@app.context_processor
def inject_alerts():
    if current_user.is_authenticated:
        alerts = get_maintenance_notifications()
        # v2: warranty expiring in 30 days
        today = date.today()
        threshold_w = today + timedelta(days=30)
        warranty_alerts = Asset.query.filter(
            Asset.warranty_end != None,
            Asset.warranty_end <= threshold_w
        ).order_by(Asset.warranty_end.asc()).all()
        # v2: overdue returns (>7 days)
        overdue_returns = get_overdue_returns()

        # v2: Purchase Order notifications
        pending_po_alerts = []
        user_po_alerts = []
        try:
            if current_user.role in ['Admin', 'Administrator']:
                pending_po_alerts = PurchaseOrder.query.filter_by(status='SUBMITTED')\
                    .order_by(PurchaseOrder.created_at.desc()).all()
            elif current_user.role in ['Staff']:
                user_po_alerts = PurchaseOrder.query.filter(
                    PurchaseOrder.requested_by == current_user.username,
                    PurchaseOrder.status.in_(['APPROVED', 'REJECTED', 'RECEIVED'])
                ).order_by(PurchaseOrder.updated_at.desc()).limit(5).all()
        except Exception:
            pass

        return {
            'maintenance_alerts': alerts,
            'warranty_alerts': warranty_alerts,
            'overdue_returns': overdue_returns,
            'pending_po_alerts': pending_po_alerts,
            'user_po_alerts': user_po_alerts,
            'csrf_token': lambda: ''
        }
    return {
        'maintenance_alerts': [],
        'warranty_alerts': [],
        'overdue_returns': [],
        'pending_po_alerts': [],
        'user_po_alerts': [],
        'csrf_token': lambda: ''
    }


# Image Upload Helper
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_attachment(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_ATTACHMENT_EXTENSIONS


def save_uploaded_photo(file_storage):
    """Securely save uploaded asset photo and return unique filename."""
    if not file_storage or file_storage.filename == '':
        return None
    if allowed_file(file_storage.filename):
        ext = file_storage.filename.rsplit('.', 1)[1].lower()
        clean_name = secure_filename(file_storage.filename.rsplit('.', 1)[0])[:30]
        unique_name = f"asset_{int(datetime.utcnow().timestamp())}_{clean_name}_{uuid.uuid4().hex[:6]}.{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        file_storage.save(filepath)
        return unique_name
    return None


def delete_photo_file(filename):
    """Delete uploaded photo file from static/uploads."""
    if filename:
        try:
            path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            app.logger.error(f"Error removing image file: {e}")


def save_po_attachment(file_storage):
    """Save PO proof attachment (signed PO, DP invoice, delivery order, BAST)."""
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit('.', 1)[1].lower() if '.' in file_storage.filename else ''
    if ext in ALLOWED_ATTACHMENT_EXTENSIONS:
        clean_name = secure_filename(file_storage.filename.rsplit('.', 1)[0])[:30]
        unique_name = f"po_{int(datetime.utcnow().timestamp())}_{clean_name}_{uuid.uuid4().hex[:6]}.{ext}"
        filepath = os.path.join(PO_ATTACHMENT_FOLDER, unique_name)
        file_storage.save(filepath)
        return unique_name
    return None


def save_maint_attachment(file_storage):
    """Save maintenance servicing proof attachment (receipt, repair note, photo)."""
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit('.', 1)[1].lower() if '.' in file_storage.filename else ''
    if ext in ALLOWED_ATTACHMENT_EXTENSIONS:
        clean_name = secure_filename(file_storage.filename.rsplit('.', 1)[0])[:30]
        unique_name = f"maint_{int(datetime.utcnow().timestamp())}_{clean_name}_{uuid.uuid4().hex[:6]}.{ext}"
        filepath = os.path.join(MAINT_ATTACHMENT_FOLDER, unique_name)
        file_storage.save(filepath)
        return unique_name
    return None


def save_avatar_file(file_storage):
    """Securely save user profile image and return filename."""
    if not file_storage or not file_storage.filename:
        return None
    if allowed_file(file_storage.filename):
        ext = file_storage.filename.rsplit('.', 1)[1].lower()
        clean_name = secure_filename(file_storage.filename.rsplit('.', 1)[0])[:25]
        unique_name = f"avatar_{int(datetime.utcnow().timestamp())}_{clean_name}_{uuid.uuid4().hex[:6]}.{ext}"
        filepath = os.path.join(AVATAR_FOLDER, unique_name)
        file_storage.save(filepath)
        return unique_name
    return None


def delete_avatar_file(filename):
    """Delete avatar image file if exists."""
    if filename:
        try:
            path = os.path.join(AVATAR_FOLDER, filename)
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            app.logger.error(f"Error removing avatar file: {e}")


def parse_currency(val):
    """
    Safely converts string or number to float without thousand separator inflation.
    Handles '10.200.000', '10200000.0', '10,200,000.50', 'Rp 10.200.000', etc.
    """
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val = str(val).strip().replace('Rp', '').replace('rp', '').replace(' ', '')
    if not val:
        return 0.0
    if '.' in val and ',' in val:
        if val.rfind(',') > val.rfind('.'):
            val = val.replace('.', '').replace(',', '.')
        else:
            val = val.replace(',', '')
    elif '.' in val:
        parts = val.split('.')
        if len(parts) == 2 and len(parts[1]) in [1, 2]:
            if parts[1] == '0' or parts[1] == '00':
                val = parts[0]
            else:
                pass  # decimal like 1500.50
        elif len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            val = val.replace('.', '')
        elif len(parts) == 2 and parts[1] == '0':
            val = parts[0]
        else:
            val = val.replace('.', '')
    elif ',' in val:
        parts = val.split(',')
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            val = val.replace(',', '')
        else:
            val = val.replace(',', '.')
    try:
        return float(val)
    except Exception:
        return 0.0


def log_po_history(po, action, notes=None, attachment=None):
    """Record an audit trail event in the PO history table."""
    try:
        hist = PurchaseOrderHistory(
            po_id=po.id,
            action=action,
            to_status=po.status,
            notes=notes,
            attachment=attachment,
            performed_by=current_user.username if (current_user and current_user.is_authenticated) else 'System'
        )
        db.session.add(hist)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error logging PO history: {e}")


# ==========================================
# Template Filters
# ==========================================
@app.template_filter('rupiah')
def rupiah_filter(value):
    try:
        if value is None:
            return 'Rp 0'
        num = float(value)
        formatted = f"{num:,.0f}".replace(',', '.')
        return f"Rp {formatted}"
    except (ValueError, TypeError):
        return 'Rp 0'


@app.template_filter('format_date')
def format_date_filter(val):
    if not val:
        return '-'
    if isinstance(val, (datetime, date)):
        months = [
            '', 'Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun',
            'Jul', 'Agt', 'Sep', 'Okt', 'Nov', 'Des'
        ]
        return f"{val.day} {months[val.month]} {val.year}"
    return str(val)


@app.template_filter('format_datetime')
def format_datetime_filter(val):
    if not val:
        return '-'
    if isinstance(val, datetime):
        months = [
            '', 'Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun',
            'Jul', 'Agt', 'Sep', 'Okt', 'Nov', 'Des'
        ]
        return f"{val.day} {months[val.month]} {val.year}, {val.strftime('%H:%M')}"
    return str(val)


# ==========================================
# Auto-Coding Generator
# ==========================================
def get_category_prefix(category_name):
    if not category_name:
        return 'AST'
    if category_name in CATEGORY_PREFIX_MAP:
        return CATEGORY_PREFIX_MAP[category_name]
    clean = re.sub(r'[^a-zA-Z0-9]', '', category_name)
    return clean[:5].capitalize() if clean else 'AST'


def generate_asset_code(category_name):
    prefix = get_category_prefix(category_name)
    like_pattern = f"{prefix}/%"
    existing_assets = Asset.query.filter(Asset.asset_code.like(like_pattern)).all()

    existing_numbers = []
    pattern = re.compile(rf'^{re.escape(prefix)}/(\d+)$')
    for asset in existing_assets:
        match = pattern.match(asset.asset_code)
        if match:
            try:
                existing_numbers.append(int(match.group(1)))
            except ValueError:
                pass

    next_num = max(existing_numbers) + 1 if existing_numbers else 1
    new_code = f"{prefix}/{next_num:03d}"

    while Asset.query.filter_by(asset_code=new_code).first():
        next_num += 1
        new_code = f"{prefix}/{next_num:03d}"

    return new_code


def generate_po_number():
    """Generates unique PO number formatted as PO/YYYY/MM/NNN with monthly counter reset."""
    now = datetime.now()
    prefix = f"PO/{now.year}/{now.month:02d}/"
    latest_po = PurchaseOrder.query.filter(PurchaseOrder.po_number.like(f"{prefix}%"))\
        .order_by(PurchaseOrder.id.desc()).first()
    if latest_po:
        try:
            last_seq = int(latest_po.po_number.split('/')[-1])
            next_seq = last_seq + 1
        except Exception:
            next_seq = 1
    else:
        next_seq = 1

    candidate = f"{prefix}{next_seq:03d}"
    while PurchaseOrder.query.filter_by(po_number=candidate).first():
        next_seq += 1
        candidate = f"{prefix}{next_seq:03d}"
    return candidate


# ==========================================
# Database Seeder & Schema Updater
# ==========================================
def seed_database():
    """Initializes default admin user & default site if not present."""
    admin_user = User.query.filter_by(username='Admin').first()
    if not admin_user:
        admin_user = User(
            username='Admin',
            full_name='Jessica (Admin JESCA)',
            role='Admin',
            force_password_change=False
        )
        admin_user.set_password('Admin123')
        db.session.add(admin_user)

    # Seed default Site
    default_site = Site.query.filter_by(name='Kantor Pusat').first()
    if not default_site:
        default_site = Site(
            name='Kantor Pusat',
            description='Lokasi utama operasional kantor'
        )
        db.session.add(default_site)

    db.session.commit()


def check_and_update_schema():
    """Ensure all v2 columns exist in SQLite database without corruption."""
    try:
        with db.engine.connect() as conn:
            # Check assets columns
            res = conn.execute(db.text("PRAGMA table_info(assets)"))
            cols = [row[1] for row in res.fetchall()]
            asset_additions = [
                ('image', 'VARCHAR(255)'),
                ('borrower', 'VARCHAR(100)'),
                ('borrow_date', 'DATETIME'),
                ('needs_maintenance', 'BOOLEAN DEFAULT 0'),
                ('maintenance_interval_days', 'INTEGER'),
                ('next_maintenance_date', 'DATE'),
                ('last_maintenance_date', 'DATE'),
                ('warranty_start', 'DATE'),
                ('warranty_end', 'DATE'),
                ('useful_life_years', 'INTEGER'),
                ('salvage_value', 'FLOAT DEFAULT 0.0'),
                ('total_checkout_days', 'INTEGER DEFAULT 0'),
                ('custom_fields_json', 'TEXT'),
                ('vendor_id', 'INTEGER'),
                ('site_id', 'INTEGER'),
                ('last_transfer_date', 'DATE'),
                ('last_transfer_from', 'VARCHAR(100)'),
                ('po_id', 'INTEGER'),
                ('po_item_id', 'INTEGER')
            ]
            for col_name, col_type in asset_additions:
                if col_name not in cols:
                    conn.execute(db.text(f"ALTER TABLE assets ADD COLUMN {col_name} {col_type}"))

            # Check users columns
            res_u = conn.execute(db.text("PRAGMA table_info(users)"))
            cols_u = [row[1] for row in res_u.fetchall()]
            user_additions = [
                ('profile_image', 'VARCHAR(255)'),
                ('is_active', 'BOOLEAN DEFAULT 1'),
                ('force_password_change', 'BOOLEAN DEFAULT 0'),
                ('api_key', 'VARCHAR(64)'),
                ('last_login', 'DATETIME'),
                ('failed_login_count', 'INTEGER DEFAULT 0'),
                ('locked_until', 'DATETIME')
            ]
            for col_name, col_type in user_additions:
                if col_name not in cols_u:
                    conn.execute(db.text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))

            # Check purchase_orders columns
            res_po = conn.execute(db.text("PRAGMA table_info(purchase_orders)"))
            cols_po = [row[1] for row in res_po.fetchall()]
            po_additions = [
                ('order_proof', 'VARCHAR(255)'),
                ('order_notes', 'TEXT'),
                ('receipt_proof', 'VARCHAR(255)'),
                ('receipt_notes', 'TEXT'),
                ('is_self_approved', 'BOOLEAN DEFAULT 0')
            ]
            for col_name, col_type in po_additions:
                if col_name not in cols_po:
                    conn.execute(db.text(f"ALTER TABLE purchase_orders ADD COLUMN {col_name} {col_type}"))

            conn.commit()

        # Create any newly defined tables
        db.create_all()
    except Exception as e:
        app.logger.warning(f"Schema update notice: {e}")


# ==========================================
# Middleware: Force Password Change Check
# ==========================================
@app.before_request
def check_force_password_change():
    exempt_endpoints = {
        'login', 'logout', 'change_password_page', 'static',
        'scan_asset_summary', 'health', 'api_asset_qrcode'
    }
    if current_user.is_authenticated and getattr(current_user, 'force_password_change', False):
        if request.endpoint and request.endpoint not in exempt_endpoints:
            return redirect(url_for('change_password_page'))


# ==========================================
# Routes: Health & Auth
# ==========================================
@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'version': '2.0',
        'app': 'JESCA Asset Management System',
        'timestamp': datetime.utcnow().isoformat()
    })


@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        remember = bool(request.form.get('remember'))

        user = User.query.filter_by(username=username).first()

        # Check account lockout
        if user and user.locked_until and datetime.utcnow() < user.locked_until:
            diff_mins = max(1, int((user.locked_until - datetime.utcnow()).total_seconds() / 60))
            flash(f'Akun dikunci sementara karena terlalu banyak percobaan gagal. Silakan coba lagi dalam {diff_mins} menit.', 'danger')
            return render_template('login.html')

        if user and user.check_password(password):
            if not getattr(user, 'is_active', True):
                flash('Akun Anda dinonaktifkan. Silakan hubungi Administrator.', 'danger')
                return render_template('login.html')

            # Reset lockout counters
            user.failed_login_count = 0
            user.locked_until = None
            user.last_login = datetime.utcnow()
            db.session.commit()

            login_user(user, remember=remember)
            log_activity('LOGIN', details=f"Pengguna {user.username} ({user.role}) berhasil masuk ke sistem.")

            if user.force_password_change:
                flash('Demi keamanan, Anda wajib mengganti password saat login pertama kali.', 'warning')
                return redirect(url_for('change_password_page'))

            flash(f'Selamat datang kembali, {user.full_name}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            if user:
                user.failed_login_count = (user.failed_login_count or 0) + 1
                if user.failed_login_count >= 5:
                    user.locked_until = datetime.utcnow() + timedelta(minutes=15)
                    user.failed_login_count = 0
                    db.session.commit()
                    flash('Terlalu banyak percobaan login gagal. Akun dikunci sementara selama 15 menit.', 'danger')
                    return render_template('login.html')
                db.session.commit()
            flash('Username atau password salah. Silakan coba lagi.', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    log_activity('LOGOUT', details=f"Pengguna {current_user.username} keluar dari sistem.")
    logout_user()
    flash('Anda telah berhasil keluar dari sistem JESCA.', 'info')
    return redirect(url_for('login'))


@app.route('/change-password-required', methods=['GET', 'POST'])
@login_required
def change_password_page():
    """Forced password change screen on first login."""
    if not getattr(current_user, 'force_password_change', False):
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        is_valid, err_msg = validate_password(new_password)
        if not is_valid:
            flash(err_msg, 'danger')
        elif new_password != confirm_password:
            flash('Konfirmasi password tidak cocok.', 'danger')
        else:
            current_user.set_password(new_password)
            current_user.force_password_change = False
            db.session.commit()
            log_activity('GANTI_PASSWORD', details='Password pertama kali diganti setelah login awal.')
            flash('Password berhasil diperbarui! Selamat datang di JESCA v2.', 'success')
            return redirect(url_for('dashboard'))

    return render_template('change_password_required.html')


@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """Self-service password update for logged-in user."""
    old_password = request.form.get('old_password', '').strip()
    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()

    if not current_user.check_password(old_password):
        flash('Password lama yang Anda masukkan tidak sesuai.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))

    is_valid, err_msg = validate_password(new_password)
    if not is_valid:
        flash(err_msg, 'danger')
        return redirect(request.referrer or url_for('dashboard'))

    if new_password != confirm_password:
        flash('Konfirmasi password baru tidak cocok.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))

    current_user.set_password(new_password)
    db.session.commit()
    log_activity('GANTI_PASSWORD', details=f"Pengguna {current_user.username} memperbarui password akunnya.")
    flash('Password Anda berhasil diperbarui!', 'success')
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    """Update profile full name and photo for current user."""
    full_name = request.form.get('full_name', '').strip()
    remove_avatar = request.form.get('remove_avatar') == '1'
    avatar_file = request.files.get('avatar_file')

    if full_name:
        current_user.full_name = full_name

    if remove_avatar and current_user.profile_image:
        delete_avatar_file(current_user.profile_image)
        current_user.profile_image = None

    if avatar_file and avatar_file.filename != '':
        saved_name = save_avatar_file(avatar_file)
        if saved_name:
            if current_user.profile_image:
                delete_avatar_file(current_user.profile_image)
            current_user.profile_image = saved_name
        else:
            flash('Format foto profil tidak didukung (gunakan JPG, PNG, atau WEBP).', 'warning')

    db.session.commit()
    log_activity('EDIT_PROFILE', details=f"Pengguna {current_user.username} memperbarui profil dan foto.")
    flash('Profil Anda berhasil diperbarui!', 'success')
    return redirect(request.referrer or url_for('dashboard'))


# ==========================================
# Routes: Dashboard
# ==========================================
@app.route('/dashboard')
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
        pending_pos=PurchaseOrder.query.filter_by(status='SUBMITTED').order_by(PurchaseOrder.created_at.desc()).all() if current_user.role in ['Admin', 'Administrator'] else []
    )


# ==========================================
# Routes: Assets CRUD & Operations
# ==========================================
@app.route('/assets')
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
            Asset.next_maintenance_date <= threshold
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
        today=today
    )


@app.route('/assets/create', methods=['POST'])
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
        return redirect(url_for('assets'))

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
            return redirect(url_for('assets'))
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

    db.session.add(new_asset)
    db.session.commit()

    log_activity(
        'TAMBAH_ASET',
        asset_code=new_asset.asset_code,
        asset_name=new_asset.name,
        details=f"Aset baru ditambahkan ({category}, Lokasi: {location}, Nilai: Rp {purchase_price:,.0f})."
    )

    flash(f'Aset "{new_asset.name}" berhasil ditambahkan dengan kode: {new_asset.asset_code}!', 'success')
    return redirect(url_for('assets'))


@app.route('/assets/<int:asset_id>/edit', methods=['POST'])
@login_required
@role_required('Admin', 'Staff')
def edit_asset(asset_id):
    """Edit existing asset details with full audit trail logging (old → new values)."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('assets'))

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
        return redirect(url_for('assets'))

    if asset_code != asset.asset_code:
        existing = Asset.query.filter_by(asset_code=asset_code).first()
        if existing:
            flash(f'Kode aset "{asset_code}" sudah terpakai oleh aset lain.', 'danger')
            return redirect(url_for('assets'))
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

    db.session.commit()

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

    flash(f'Perubahan aset [{asset.asset_code}] berhasil disimpan!', 'success')
    return redirect(url_for('assets'))


@app.route('/assets/<int:asset_id>/delete', methods=['POST'])
@login_required
@role_required('Admin')
def delete_asset(asset_id):
    """Delete an asset record and its image from disk (Admin only)."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('assets'))

    code = asset.asset_code
    name = asset.name
    delete_photo_file(asset.image)

    db.session.delete(asset)
    db.session.commit()

    log_activity(
        'HAPUS_ASET',
        asset_code=code,
        asset_name=name,
        details=f"Aset [{code}] {name} telah dihapus dari sistem oleh {current_user.username}."
    )

    flash(f'Aset [{code}] - {name} telah berhasil dihapus.', 'info')
    return redirect(url_for('assets'))


@app.route('/assets/<int:asset_id>/checkout', methods=['POST'])
@login_required
@role_required('Admin', 'Staff')
def checkout_asset(asset_id):
    """Check Out (Pinjam Aset) with server-side validation against Perbaikan/Rusak/Afkir."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('assets'))

    # v2: Guard against borrowing damaged / broken / retired assets
    if asset.status in ['Dalam Perbaikan', 'Afkir', 'Rusak']:
        flash(f'Aset dengan status "{asset.status}" tidak dapat dipinjam.', 'danger')
        return redirect(url_for('assets'))

    # Guard: Alert if overdue for maintenance
    if asset.needs_maintenance and asset.next_maintenance_date and asset.next_maintenance_date <= date.today() and asset.status != 'Afkir':
        flash(f'Aset [{asset.asset_code}] sedang jatuh tempo pemeliharaan ({asset.next_maintenance_date.strftime("%d/%m/%Y")}). Harap lakukan servis teknisi sebelum dipinjamkan.', 'warning')

    if asset.status == 'Dipinjam':
        flash(f'Aset sedang dipinjam oleh {asset.borrower}. Selesaikan check-in terlebih dahulu.', 'warning')
        return redirect(url_for('assets'))

    borrower = request.form.get('borrower', '').strip()
    notes = request.form.get('notes', '').strip()

    if not borrower:
        flash('Nama peminjam wajib diisi.', 'danger')
        return redirect(url_for('assets'))

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
    db.session.add(circ_log)
    db.session.commit()

    log_activity(
        'CHECK_OUT',
        asset_code=asset.asset_code,
        asset_name=asset.name,
        details=f"Aset dipinjamkan kepada: {borrower}. Catatan: {notes or '-'}"
    )

    flash(f'Aset [{asset.asset_code}] berhasil dipinjamkan kepada {borrower}.', 'success')
    return redirect(url_for('assets'))


@app.route('/assets/<int:asset_id>/checkin', methods=['POST'])
@login_required
@role_required('Admin', 'Staff')
def checkin_asset(asset_id):
    """Check In (Pengembalian Aset) with permanent circulation history logging."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('assets'))

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
    db.session.commit()

    log_activity(
        'CHECK_IN',
        asset_code=asset.asset_code,
        asset_name=asset.name,
        details=f"Aset dikembalikan oleh: {prev_borrower} ({days_borrowed} hari). Status sekarang: {new_status}. Catatan: {return_notes or '-'}"
    )

    flash(f'Aset [{asset.asset_code}] berhasil dikembalikan (Status: {new_status}).', 'success')
    return redirect(url_for('assets'))


@app.route('/api/assets/<int:asset_id>/circulation')
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
@app.route('/maintenance')
@login_required
@role_required('Admin', 'Administrator', 'Teknisi', 'Staff')
def maintenance():
    """Technician & Maintenance Operations Center."""
    today = date.today()
    threshold = today + timedelta(days=14)

    due_assets = Asset.query.filter(
        Asset.needs_maintenance == True,
        Asset.next_maintenance_date != None,
        Asset.next_maintenance_date <= threshold,
        Asset.status != 'Afkir'
    ).order_by(Asset.next_maintenance_date.asc()).all()

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


@app.route('/assets/<int:asset_id>/maintenance/start', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator', 'Teknisi', 'Staff')
def start_maintenance(asset_id):
    """Technician marks an asset as currently undergoing repair/servicing."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('maintenance'))

    old_status = asset.status
    asset.status = 'Dalam Perbaikan'
    db.session.commit()

    log_activity(
        'MULAI_SERVIS',
        asset_code=asset.asset_code,
        asset_name=asset.name,
        details=f"Pengerjaan pemeliharaan dimulai oleh Teknisi {current_user.username}. Status diubah dari '{old_status}' menjadi 'Dalam Perbaikan'."
    )

    flash(f'Aset [{asset.asset_code}] resmi ditandai "Dalam Perbaikan" oleh Teknisi {current_user.username}.', 'info')
    return redirect(url_for('maintenance'))


@app.route('/assets/<int:asset_id>/maintenance/complete', methods=['POST'])
@app.route('/assets/<int:asset_id>/complete-maintenance', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator', 'Teknisi', 'Staff')
def complete_maintenance(asset_id):
    """Complete maintenance service, record invoice/proof, reset interval."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('maintenance'))

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
    db.session.commit()

    log_activity(
        'MAINTENANCE_SELESAI',
        asset_code=asset.asset_code,
        asset_name=asset.name,
        details=f"Pemeliharaan [{service_type}] selesai dikerjakan oleh {current_user.username}. Biaya: Rp {cost:,.0f}. Jadwal berikutnya: {asset.next_maintenance_date.strftime('%d/%m/%Y')}."
    )

    flash(f'Pemeliharaan untuk [{asset.asset_code}] berhasil disimpan & jadwal servis berikutnya diperbarui ({asset.next_maintenance_date.strftime("%d/%m/%Y")})!', 'success')
    return redirect(request.referrer or url_for('maintenance'))


@app.route('/attachments/maintenance/<filename>')
@login_required
def download_maintenance_attachment(filename):
    safe_name = secure_filename(filename)
    return send_from_directory(MAINT_ATTACHMENT_FOLDER, safe_name)


@app.route('/attachments/po/<filename>')
@login_required
def download_po_attachment(filename):
    safe_name = secure_filename(filename)
    return send_from_directory(PO_ATTACHMENT_FOLDER, safe_name)


# ==========================================
# Routes: Asset Transfer
# ==========================================
@app.route('/assets/<int:asset_id>/transfer', methods=['POST'])
@login_required
@role_required('Admin', 'Staff')
def transfer_asset(asset_id):
    """Record permanent asset transfer between locations / sites."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('assets'))

    to_location = request.form.get('to_location', '').strip()
    to_site_id_raw = request.form.get('to_site_id', '').strip()
    reason = request.form.get('reason', '').strip()

    if not to_location:
        flash('Lokasi tujuan wajib diisi.', 'danger')
        return redirect(url_for('assets'))

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

    db.session.commit()

    log_activity(
        'TRANSFER_ASET',
        asset_code=asset.asset_code,
        asset_name=asset.name,
        details=f"Aset dipindahkan dari '{from_loc}' ke '{to_location}'. Alasan: {reason or '-'}"
    )

    flash(f'Aset [{asset.asset_code}] berhasil ditransfer ke {to_location}.', 'success')
    return redirect(url_for('assets'))


# ==========================================
# Routes: Bulk Operations
# ==========================================
@app.route('/assets/bulk-action', methods=['POST'])
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
        return redirect(url_for('assets'))

    if not asset_ids:
        flash('Tidak ada aset yang dipilih.', 'warning')
        return redirect(url_for('assets'))

    target_assets = Asset.query.filter(Asset.id.in_(asset_ids)).all()
    count = len(target_assets)

    if action == 'delete':
        if current_user.role != 'Admin':
            flash('Hanya Administrator yang dapat menghapus aset secara massal.', 'danger')
            return redirect(url_for('assets'))
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
            return redirect(url_for('assets'))
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
            return redirect(url_for('assets'))
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

    return redirect(url_for('assets'))


# ==========================================
# Routes: CSV Import
# ==========================================
@app.route('/assets/import-csv', methods=['GET', 'POST'])
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
        return redirect(url_for('assets'))

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

    return redirect(url_for('assets'))


# ==========================================
# Routes: PDF Export
# ==========================================
@app.route('/assets/export/pdf')
@login_required
@role_required('Admin', 'Administrator', 'Auditor')
def export_assets_pdf():
    """Generate formal PDF asset inventory report."""
    if not HAVE_REPORTLAB:
        flash('Modul reportlab belum terinstall untuk ekspor PDF.', 'warning')
        return redirect(url_for('assets'))

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


# ==========================================
# Routes: Attachments Management
# ==========================================
@app.route('/assets/<int:asset_id>/attachments/upload', methods=['POST'])
@login_required
@role_required('Admin', 'Staff')
def upload_attachment(asset_id):
    """Upload documents linked to an asset (manual, invoice, warranty certificate)."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('assets'))

    file = request.files.get('attachment_file')
    file_type = request.form.get('file_type', 'other').strip()

    if not file or file.filename == '':
        flash('File lampiran wajib dipilih.', 'danger')
        return redirect(url_for('assets'))

    if not allowed_attachment(file.filename):
        flash('Format file tidak didukung. Format diizinkan: PDF, DOCX, XLSX, JPG, PNG, TXT.', 'danger')
        return redirect(url_for('assets'))

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
    return redirect(request.referrer or url_for('assets'))


@app.route('/assets/<int:asset_id>/attachments/<int:att_id>/download')
@login_required
def download_attachment(asset_id, att_id):
    """Download an asset attachment."""
    att = db.session.get(AssetAttachment, att_id)
    if not att or att.asset_id != asset_id:
        flash('Lampiran tidak ditemukan.', 'danger')
        return redirect(url_for('assets'))
    return send_from_directory(
        ATTACHMENT_FOLDER,
        att.filename,
        as_attachment=True,
        download_name=att.original_name
    )


@app.route('/assets/<int:asset_id>/attachments/<int:att_id>/delete', methods=['POST'])
@login_required
@role_required('Admin', 'Staff')
def delete_attachment(asset_id, att_id):
    """Delete an asset attachment."""
    att = db.session.get(AssetAttachment, att_id)
    if not att or att.asset_id != asset_id:
        flash('Lampiran tidak ditemukan.', 'danger')
        return redirect(url_for('assets'))

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
    return redirect(request.referrer or url_for('assets'))


@app.route('/api/assets/<int:asset_id>/attachments', methods=['GET'])
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
            'download_url': url_for('download_attachment', asset_id=asset_id, att_id=a.id)
        } for a in attachments]
    })


# ==========================================
# Routes: Vendors & Suppliers Management
# ==========================================
@app.route('/vendors')
@login_required
def vendors():
    """List vendors & suppliers with asset counts."""
    vendor_list = Vendor.query.order_by(Vendor.name.asc()).all()
    return render_template('vendors.html', vendors=vendor_list)


@app.route('/vendors/create', methods=['POST'])
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
        return redirect(url_for('vendors'))

    new_v = Vendor(
        name=name,
        contact_person=contact_person,
        phone=phone,
        email=email,
        address=address,
        notes=notes,
        is_active=True
    )
    db.session.add(new_v)
    db.session.commit()

    log_activity('TAMBAH_VENDOR', details=f"Vendor baru ditambahkan: '{name}' oleh {current_user.username}.")
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success', 'vendor': new_v.to_dict()})

    flash(f'Vendor "{name}" berhasil ditambahkan!', 'success')
    return redirect(url_for('vendors'))


@app.route('/vendors/<int:vendor_id>/edit', methods=['POST'])
@login_required
@role_required('Admin', 'Staff')
def edit_vendor(vendor_id):
    v = db.session.get(Vendor, vendor_id)
    if not v:
        flash('Vendor tidak ditemukan.', 'danger')
        return redirect(url_for('vendors'))

    name = request.form.get('name', '').strip()
    if not name:
        flash('Nama vendor tidak boleh kosong.', 'danger')
        return redirect(url_for('vendors'))

    v.name = name
    v.contact_person = request.form.get('contact_person', '').strip()
    v.phone = request.form.get('phone', '').strip()
    v.email = request.form.get('email', '').strip()
    v.address = request.form.get('address', '').strip()
    v.notes = request.form.get('notes', '').strip()
    v.is_active = bool(request.form.get('is_active'))

    db.session.commit()
    log_activity('EDIT_VENDOR', details=f"Data vendor '{name}' diperbarui.")
    flash(f'Vendor "{name}" berhasil diperbarui!', 'success')
    return redirect(url_for('vendors'))


@app.route('/vendors/<int:vendor_id>/delete', methods=['POST'])
@login_required
@role_required('Admin')
def delete_vendor(vendor_id):
    v = db.session.get(Vendor, vendor_id)
    if not v:
        flash('Vendor tidak ditemukan.', 'danger')
        return redirect(url_for('vendors'))

    v_name = v.name
    # Unlink assets referencing this vendor
    Asset.query.filter_by(vendor_id=v.id).update({'vendor_id': None})
    db.session.delete(v)
    db.session.commit()

    log_activity('HAPUS_VENDOR', details=f"Vendor '{v_name}' dihapus oleh {current_user.username}.")
    flash(f'Vendor "{v_name}" berhasil dihapus.', 'info')
    return redirect(url_for('vendors'))


@app.route('/api/vendors', methods=['GET'])
@login_required
def api_vendors():
    v_list = Vendor.query.filter_by(is_active=True).order_by(Vendor.name.asc()).all()
    return jsonify({'status': 'success', 'data': [v.to_dict() for v in v_list]})


# ==========================================
# Routes: Sites & Locations Management
# ==========================================
@app.route('/sites')
@login_required
@role_required('Admin', 'Administrator')
def sites():
    site_list = Site.query.order_by(Site.name.asc()).all()
    return render_template('sites.html', sites=site_list)


@app.route('/sites/create', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator')
def create_site():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()

    if not name:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'error', 'message': 'Nama lokasi/site wajib diisi.'}), 400
        flash('Nama lokasi/site wajib diisi.', 'danger')
        return redirect(url_for('sites'))

    if Site.query.filter_by(name=name).first():
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'error', 'message': f'Site "{name}" sudah terdaftar.'}), 400
        flash(f'Site "{name}" sudah terdaftar.', 'warning')
        return redirect(url_for('sites'))

    s = Site(name=name, description=description, is_active=True)
    db.session.add(s)
    db.session.commit()

    log_activity('TAMBAH_SITE', details=f"Lokasi/Site '{name}' ditambahkan.")
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success', 'site': {'id': s.id, 'name': s.name, 'description': s.description}})

    flash(f'Site "{name}" berhasil ditambahkan!', 'success')
    return redirect(url_for('sites'))


@app.route('/sites/<int:site_id>/edit', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator')
def edit_site(site_id):
    s = db.session.get(Site, site_id)
    if not s:
        flash('Site tidak ditemukan.', 'danger')
        return redirect(url_for('sites'))

    name = request.form.get('name', '').strip()
    if not name:
        flash('Nama site tidak boleh kosong.', 'danger')
        return redirect(url_for('sites'))

    s.name = name
    s.description = request.form.get('description', '').strip()
    s.is_active = bool(request.form.get('is_active'))
    db.session.commit()

    log_activity('EDIT_SITE', details=f"Data site '{name}' diperbarui.")
    flash(f'Site "{name}" berhasil diperbarui!', 'success')
    return redirect(url_for('sites'))


@app.route('/sites/<int:site_id>/delete', methods=['POST'])
@login_required
@role_required('Admin')
def delete_site(site_id):
    s = db.session.get(Site, site_id)
    if not s:
        flash('Site tidak ditemukan.', 'danger')
        return redirect(url_for('sites'))

    s_name = s.name
    # Unlink assets referencing this site
    Asset.query.filter_by(site_id=s.id).update({'site_id': None})
    db.session.delete(s)
    db.session.commit()

    log_activity('HAPUS_SITE', details=f"Site '{s_name}' dihapus oleh {current_user.username}.")
    flash(f'Site "{s_name}" berhasil dihapus.', 'info')
    return redirect(url_for('sites'))


@app.route('/api/sites', methods=['GET'])
@login_required
def api_sites():
    s_list = Site.query.filter_by(is_active=True).order_by(Site.name.asc()).all()
    return jsonify({'status': 'success', 'data': [s.to_dict() for s in s_list]})


# ==========================================
# Routes: QR Code & Public Scan Summary
# ==========================================
@app.route('/scan/<path:asset_code>')
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


@app.route('/api/assets/<int:asset_id>/qrcode')
def api_asset_qrcode(asset_id):
    """Generate QR Code image pointing directly to the asset's scan summary URL."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        return jsonify({'error': 'Not found'}), 404

    scan_url = url_for('scan_asset_summary', asset_code=asset.asset_code, _external=True)

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


@app.route('/api/generate-code', methods=['GET'])
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


@app.route('/api/assets/<int:asset_id>', methods=['GET'])
@login_required
def api_get_asset(asset_id):
    asset = db.session.get(Asset, asset_id)
    if not asset:
        return jsonify({'status': 'error', 'message': 'Asset not found'}), 404
    return jsonify({'status': 'success', 'data': asset.to_dict()})


@app.route('/api/assets/warranty-alerts', methods=['GET'])
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


@app.route('/assets/export/csv')
@login_required
@role_required('Admin', 'Administrator', 'Auditor')
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
            a.purchase_date.strftime('%Y-%m-%d') if a.purchase_date else '-',
            f"{int(round(a.purchase_price or 0))}",
            f"{int(round(a.current_book_value or 0))}",
            a.status,
            a.borrower or '-',
            a.vendor.name if a.vendor else '-',
            a.site.name if a.site else '-',
            a.warranty_start.strftime('%Y-%m-%d') if a.warranty_start else '-',
            a.warranty_end.strftime('%Y-%m-%d') if a.warranty_end else '-',
            'Ya' if a.needs_maintenance else 'Tidak',
            a.maintenance_interval_days or '-',
            a.next_maintenance_date.strftime('%Y-%m-%d') if a.next_maintenance_date else '-',
            (a.description or '').replace('\r', '').replace('\n', ' ').strip() or '-'
        ])

    log_activity('EXPORT_CSV', details=f"Ekspor CSV {len(assets_all)} data inventaris aset.")
    filename = f"jesca_assets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ==========================================
# Routes: Activity Logs & Audit Report
# ==========================================
@app.route('/history')
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


@app.route('/history/clear', methods=['POST'])
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
    return redirect(url_for('history'))


@app.route('/reports/audit')
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


# ==========================================
# Routes: Backup & Restore
# ==========================================
@app.route('/admin/backups')
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
    return render_template('admin_backups.html', backups=backup_files)


@app.route('/admin/backup', methods=['POST'])
@login_required
@admin_required
def manual_backup():
    """Create manual snapshot backup of SQLite database."""
    filename = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    dst = os.path.join(BACKUP_FOLDER, filename)
    shutil.copy2(db_path, dst)

    log_activity('BACKUP', details=f"Manual backup database dibuat: {filename}")
    flash(f'Backup database berhasil dibuat: {filename}', 'success')
    return redirect(url_for('admin_backups'))


@app.route('/admin/restore/<filename>', methods=['POST'])
@login_required
@admin_required
def restore_backup(filename):
    """Restore SQLite database from backup file with safety snapshot."""
    safe_name = secure_filename(filename)
    src = os.path.join(BACKUP_FOLDER, safe_name)

    if not os.path.exists(src) or not safe_name.endswith('.db'):
        flash('File backup tidak ditemukan atau tidak valid.', 'danger')
        return redirect(url_for('admin_backups'))

    # Safety: take snapshot before overwrite
    safety_snap = f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(db_path, os.path.join(BACKUP_FOLDER, safety_snap))

    # Overwrite current db
    shutil.copy2(src, db_path)

    log_activity('RESTORE', details=f"Database dipulihkan dari file: {safe_name}")
    flash(f'Database berhasil dipulihkan dari {safe_name}. Snapshot pra-restore: {safety_snap}.', 'success')
    return redirect(url_for('admin_backups'))


def auto_backup_job():
    """Daily scheduled auto-backup (2:00 AM) keeping last 30 days retention."""
    with app.app_context():
        try:
            today_str = datetime.now().strftime('%Y%m%d')
            filename = f"auto_{today_str}.db"
            dst = os.path.join(BACKUP_FOLDER, filename)
            if not os.path.exists(dst) and os.path.exists(db_path):
                shutil.copy2(db_path, dst)

            # Prune backups older than 30 days
            cutoff = datetime.now() - timedelta(days=30)
            for f in os.listdir(BACKUP_FOLDER):
                if f.endswith('.db'):
                    fp = os.path.join(BACKUP_FOLDER, f)
                    if datetime.fromtimestamp(os.path.getctime(fp)) < cutoff:
                        os.remove(fp)
        except Exception as e:
            app.logger.error(f"Auto-backup execution failed: {e}")


# ==========================================
# Routes: REST API v1 (API Key Protected)
# ==========================================
@app.route('/api/v1/assets', methods=['GET'])
@api_key_required
def api_v1_assets():
    """REST API endpoint returning all assets as JSON."""
    all_a = Asset.query.order_by(Asset.asset_code.asc()).all()
    return jsonify({
        'status': 'success',
        'count': len(all_a),
        'data': [a.to_dict() for a in all_a]
    })


@app.route('/api/v1/assets/<asset_code>', methods=['GET'])
@api_key_required
def api_v1_asset_detail(asset_code):
    """REST API endpoint returning single asset details."""
    asset = Asset.query.filter_by(asset_code=asset_code).first()
    if not asset:
        return jsonify({'status': 'error', 'message': f'Asset with code {asset_code} not found'}), 404
    return jsonify({'status': 'success', 'data': asset.to_dict()})


# ==========================================
# Routes: Accounts & API Key Management
# ==========================================
@app.route('/accounts')
@login_required
@admin_required
def accounts():
    all_users = User.query.order_by(User.created_at.asc()).all()
    return render_template(
        'accounts.html',
        users=all_users,
        roles=ROLE_CHOICES
    )


@app.route('/users')
@login_required
@admin_required
def users_redirect():
    return redirect(url_for('accounts'))


@app.route('/accounts/create', methods=['POST'])
@login_required
@admin_required
def create_account():
    username = request.form.get('username', '').strip()
    full_name = request.form.get('full_name', '').strip()
    role = request.form.get('role', 'Staff').strip()
    password = request.form.get('password', '').strip()

    if not username or not password:
        flash('Username dan password wajib diisi.', 'danger')
        return redirect(url_for('accounts'))

    is_valid, err_msg = validate_password(password)
    if not is_valid:
        flash(err_msg, 'danger')
        return redirect(url_for('accounts'))

    if User.query.filter_by(username=username).first():
        flash(f'Username "{username}" sudah terdaftar.', 'danger')
        return redirect(url_for('accounts'))

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
    return redirect(url_for('accounts'))


@app.route('/accounts/<int:user_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_account(user_id):
    target_user = db.session.get(User, user_id)
    if not target_user:
        flash('Pengguna tidak ditemukan.', 'danger')
        return redirect(url_for('accounts'))

    full_name = request.form.get('full_name', '').strip()
    role = request.form.get('role', target_user.role).strip()
    is_active = bool(request.form.get('is_active'))

    if target_user.id == current_user.id and role != 'Admin':
        flash('Anda tidak dapat mengubah role akun Anda sendiri dari Admin.', 'danger')
        return redirect(url_for('accounts'))

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
    return redirect(url_for('accounts'))


@app.route('/accounts/<int:user_id>/change-password', methods=['POST'])
@login_required
@admin_required
def admin_change_user_password(user_id):
    target_user = db.session.get(User, user_id)
    if not target_user:
        flash('Pengguna tidak ditemukan.', 'danger')
        return redirect(url_for('accounts'))

    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()

    is_valid, err_msg = validate_password(new_password)
    if not is_valid:
        flash(err_msg, 'danger')
        return redirect(url_for('accounts'))

    if new_password != confirm_password:
        flash('Konfirmasi password tidak cocok.', 'danger')
        return redirect(url_for('accounts'))

    target_user.set_password(new_password)
    target_user.force_password_change = True  # Require change after reset
    db.session.commit()

    log_activity(
        'RESET_PASSWORD_USER',
        details=f"Password akun {target_user.username} direset oleh {current_user.username}."
    )

    flash(f'Password untuk akun "{target_user.username}" berhasil diubah!', 'success')
    return redirect(url_for('accounts'))


@app.route('/accounts/<int:user_id>/generate-api-key', methods=['POST'])
@login_required
@admin_required
def generate_api_key(user_id):
    """Generate or rotate REST API key for user."""
    target_user = db.session.get(User, user_id)
    if not target_user:
        flash('Pengguna tidak ditemukan.', 'danger')
        return redirect(url_for('accounts'))

    new_key = f"jesca_{secrets.token_hex(24)}"
    target_user.api_key = new_key
    db.session.commit()

    log_activity('GENERATE_API_KEY', details=f"API Key baru dibuat untuk {target_user.username}.")
    flash(f'API Key baru untuk {target_user.username} berhasil dibuat: {new_key}', 'success')
    return redirect(url_for('accounts'))


@app.route('/accounts/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_account(user_id):
    if user_id == current_user.id:
        flash('Anda tidak dapat menghapus akun Anda sendiri.', 'danger')
        return redirect(url_for('accounts'))

    target_user = db.session.get(User, user_id)
    if not target_user:
        flash('Pengguna tidak ditemukan.', 'danger')
        return redirect(url_for('accounts'))

    u_name = target_user.username
    db.session.delete(target_user)
    db.session.commit()

    log_activity('HAPUS_USER', details=f"Akun {u_name} dihapus oleh {current_user.username}.")
    flash(f'Akun "{u_name}" telah berhasil dihapus.', 'info')
    return redirect(url_for('accounts'))


# ==========================================
# Routes: Purchase Order (PO) Management
# ==========================================
@app.route('/purchase-orders')
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


@app.route('/purchase-orders/create', methods=['GET', 'POST'])
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
        return redirect(url_for('create_purchase_order'))

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
        return redirect(url_for('create_purchase_order'))

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

    return redirect(url_for('purchase_order_detail', po_id=po.id))


@app.route('/purchase-orders/<int:po_id>')
@login_required
@role_required('Admin', 'Administrator', 'Staff', 'Auditor')
def purchase_order_detail(po_id):
    """View detailed information, approval timeline, items, and conversion tools for a PO."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        flash('Purchase Order tidak ditemukan.', 'danger')
        return redirect(url_for('purchase_orders'))

    # Staff can only view their own PO
    if current_user.role == 'Staff' and po.requested_by != current_user.username:
        flash('Anda tidak memiliki izin melihat Purchase Order pengguna lain.', 'danger')
        return redirect(url_for('purchase_orders'))

    sites = Site.query.filter_by(is_active=True).order_by(Site.name.asc()).all()
    categories = DEFAULT_CATEGORIES

    return render_template(
        'purchase_order_detail.html',
        po=po,
        sites=sites,
        categories=categories
    )


@app.route('/purchase-orders/<int:po_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('Admin', 'Administrator', 'Staff')
def edit_purchase_order(po_id):
    """Edit a PO when in DRAFT (or Admin edit if SUBMITTED)."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        flash('Purchase Order tidak ditemukan.', 'danger')
        return redirect(url_for('purchase_orders'))

    # Permission check
    if current_user.role == 'Staff' and po.requested_by != current_user.username:
        flash('Anda tidak memiliki hak mengedit PO ini.', 'danger')
        return redirect(url_for('purchase_orders'))

    # Can only edit if DRAFT, or Admin if SUBMITTED
    can_edit = (po.status == 'DRAFT') or (current_user.role in ['Admin', 'Administrator'] and po.status in ['DRAFT', 'SUBMITTED', 'REJECTED'])
    if not can_edit:
        flash(f'Purchase Order dengan status "{po.status}" tidak dapat diedit lagi.', 'warning')
        return redirect(url_for('purchase_order_detail', po_id=po.id))

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
        return redirect(url_for('edit_purchase_order', po_id=po.id))

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
        return redirect(url_for('edit_purchase_order', po_id=po.id))

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
    return redirect(url_for('purchase_order_detail', po_id=po.id))


@app.route('/purchase-orders/<int:po_id>/submit', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator', 'Staff')
def submit_purchase_order(po_id):
    """Submit a DRAFT or REJECTED PO to Admin for approval."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        flash('PO tidak ditemukan.', 'danger')
        return redirect(url_for('purchase_orders'))

    if current_user.role == 'Staff' and po.requested_by != current_user.username:
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('purchase_orders'))

    if po.status not in ['DRAFT', 'REJECTED']:
        flash(f'PO dengan status "{po.status}" tidak dapat diajukan.', 'warning')
        return redirect(url_for('purchase_order_detail', po_id=po.id))

    if not po.items:
        flash('PO tidak memiliki item barang. Tambahkan item sebelum mengajukan.', 'danger')
        return redirect(url_for('purchase_order_detail', po_id=po.id))

    po.status = 'SUBMITTED'
    po.submitted_at = datetime.utcnow()
    po.rejection_reason = None
    db.session.commit()

    log_po_history(po, 'SUBMIT', f"Diajukan kembali untuk persetujuan Admin.")
    log_activity('SUBMIT_PO', details=f"PO [{po.po_number}] diajukan oleh {current_user.username}.")
    flash(f'Purchase Order [{po.po_number}] berhasil diajukan untuk persetujuan Admin!', 'success')
    return redirect(url_for('purchase_order_detail', po_id=po.id))


@app.route('/purchase-orders/<int:po_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_purchase_order(po_id):
    """Admin approves a submitted PO (with self-approval detection)."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        flash('PO tidak ditemukan.', 'danger')
        return redirect(url_for('purchase_orders'))

    if po.status != 'SUBMITTED':
        flash(f'Hanya PO dengan status SUBMITTED yang dapat disetujui (Status saat ini: {po.status}).', 'warning')
        return redirect(url_for('purchase_order_detail', po_id=po.id))

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
    return redirect(url_for('purchase_order_detail', po_id=po.id))


@app.route('/purchase-orders/<int:po_id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_purchase_order(po_id):
    """Admin rejects a submitted PO with a mandatory reason."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        flash('PO tidak ditemukan.', 'danger')
        return redirect(url_for('purchase_orders'))

    if po.status != 'SUBMITTED':
        flash('Hanya PO dengan status SUBMITTED yang dapat ditolak.', 'warning')
        return redirect(url_for('purchase_order_detail', po_id=po.id))

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
    return redirect(url_for('purchase_order_detail', po_id=po.id))


@app.route('/purchase-orders/<int:po_id>/order', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator', 'Staff')
def order_purchase_order(po_id):
    """Mark an approved PO as ORDERED with order proof upload."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        flash('PO tidak ditemukan.', 'danger')
        return redirect(url_for('purchase_orders'))

    if po.status != 'APPROVED':
        flash('Hanya PO dengan status APPROVED yang dapat ditandai ORDERED.', 'warning')
        return redirect(url_for('purchase_order_detail', po_id=po.id))

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
    return redirect(url_for('purchase_order_detail', po_id=po.id))


@app.route('/purchase-orders/<int:po_id>/receive', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator', 'Staff')
def receive_purchase_order(po_id):
    """Mark goods as RECEIVED with mandatory delivery receipt proof (Surat Jalan/BAST)."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        flash('PO tidak ditemukan.', 'danger')
        return redirect(url_for('purchase_orders'))

    if po.status not in ['ORDERED', 'APPROVED']:
        flash('Hanya PO yang sudah dipesan/disetujui yang dapat ditandai diterima.', 'warning')
        return redirect(url_for('purchase_order_detail', po_id=po.id))

    receipt_notes = request.form.get('receipt_notes', '').strip()
    proof_file = request.files.get('receipt_proof')

    if not proof_file or not proof_file.filename:
        if not po.receipt_proof:
            flash('Unggah berkas bukti penerimaan barang fisik (Surat Jalan / BAST / Foto Barang) wajib dilampirkan sebelum status dapat diubah menjadi RECEIVED.', 'danger')
            return redirect(url_for('purchase_order_detail', po_id=po.id))
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
    return redirect(url_for('purchase_order_detail', po_id=po.id))


@app.route('/purchase-orders/<int:po_id>/cancel', methods=['POST'])
@login_required
@role_required('Admin', 'Administrator', 'Staff')
def cancel_purchase_order(po_id):
    """Cancel a purchase order."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        flash('PO tidak ditemukan.', 'danger')
        return redirect(url_for('purchase_orders'))

    if current_user.role == 'Staff':
        if po.requested_by != current_user.username or po.status != 'DRAFT':
            flash('Staff hanya dapat membatalkan draft PO miliknya sendiri.', 'danger')
            return redirect(url_for('purchase_order_detail', po_id=po.id))
    elif po.status in ['CLOSED', 'RECEIVED']:
        flash('PO yang sudah diterima/selesai tidak dapat dibatalkan.', 'warning')
        return redirect(url_for('purchase_order_detail', po_id=po.id))

    po.status = 'CANCELLED'
    db.session.commit()

    log_po_history(po, 'CANCEL', f"Dibatalkan oleh {current_user.username}.")
    log_activity('CANCEL_PO', details=f"PO [{po.po_number}] dibatalkan oleh {current_user.username}.")
    flash(f'Purchase Order [{po.po_number}] telah dibatalkan.', 'info')
    return redirect(url_for('purchase_order_detail', po_id=po.id))


@app.route('/purchase-orders/<int:po_id>/items/<int:item_id>/convert', methods=['POST'])
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
        return redirect(url_for('purchase_orders'))

    if po.status != 'RECEIVED':
        flash('Item hanya dapat dikonversi menjadi aset setelah PO berstatus RECEIVED (Barang Tiba).', 'warning')
        return redirect(url_for('purchase_order_detail', po_id=po.id))

    # Strict physical proof guard
    if not po.receipt_proof:
        flash('Barang tidak dapat dikonversi menjadi aset resmi sebelum berkas bukti penerimaan (Surat Jalan/BAST) diunggah.', 'danger')
        return redirect(url_for('purchase_order_detail', po_id=po.id))

    if item.remaining_to_convert <= 0:
        flash('Semua unit untuk item ini sudah dikonversi menjadi aset.', 'info')
        return redirect(url_for('purchase_order_detail', po_id=po.id))

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

    db.session.commit()

    log_activity(
        'TAMBAH_ASET_PO',
        asset_code=new_asset.asset_code,
        asset_name=new_asset.name,
        details=f"Dikonversi dari PO [{po.po_number}] Item #{item.id} (Nilai: Rp {purchase_price:,.0f}) oleh {current_user.username}."
    )
    flash(msg, 'success')
    return redirect(url_for('purchase_order_detail', po_id=po.id))


@app.route('/purchase-orders/export/csv')
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


@app.route('/purchase-orders/export/pdf')
@login_required
@role_required('Admin', 'Administrator', 'Auditor')
def export_purchase_orders_pdf():
    """Generate formal PDF report of all purchase orders."""
    if not HAVE_REPORTLAB:
        flash('Modul reportlab belum terinstall untuk ekspor PDF.', 'warning')
        return redirect(url_for('purchase_orders'))

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


@app.route('/purchase-orders/<int:po_id>/print')
@login_required
@role_required('Admin', 'Administrator', 'Staff', 'Auditor')
def print_purchase_order_pdf(po_id):
    """Generate formal individual Purchase Order sheet in PDF format."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        flash('PO tidak ditemukan.', 'danger')
        return redirect(url_for('purchase_orders'))

    if not HAVE_REPORTLAB:
        flash('Modul reportlab belum terinstall.', 'warning')
        return redirect(url_for('purchase_order_detail', po_id=po.id))

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


# ==========================================
# Initialize Database Tables & Scheduler
# ==========================================
with app.app_context():
    db.create_all()
    check_and_update_schema()
    seed_database()

# Start background scheduler for auto-backup
if HAVE_SCHEDULER and (not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true'):
    try:
        scheduler = BackgroundScheduler()
        scheduler.add_job(func=auto_backup_job, trigger='cron', hour=2, minute=0)
        scheduler.start()
    except Exception as e:
        app.logger.warning(f"Could not start backup scheduler: {e}")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
