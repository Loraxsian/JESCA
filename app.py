import os
import re
import csv
import io
import json
import uuid
import shutil
import secrets
import smtplib
import threading
import base64
import hashlib
import ipaddress
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
from datetime import datetime, date, timedelta
from urllib.parse import quote

from flask import (
    Flask, render_template, request, redirect, url_for, flash, jsonify, Response, send_from_directory, session
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine
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
# Application Version
# ==========================================
APP_VERSION = '2.5.0'
GITHUB_REPO = 'Loraxsian/JESCA'  # Used for release check via GitHub API

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
# SQLite Concurrency & Timeout Optimization (WAL mode + 30s busy timeout)
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {'timeout': 30}
    }

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # Max 5MB upload
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config['SESSION_REFRESH_EACH_REQUEST'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

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

# SQLite Concurrency & Integrity Optimizer: WAL mode, 30s timeout & foreign keys
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")  # 30 seconds
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        pass

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
class SystemSetting(db.Model):
    """Dynamic persistent system configurations (SMTP & Global Settings)."""
    __tablename__ = 'system_settings'

    id = db.Column(db.Integer, primary_key=True)
    mail_enabled = db.Column(db.Boolean, default=False)
    mail_server = db.Column(db.String(150), default='smtp.gmail.com')
    mail_port = db.Column(db.Integer, default=587)
    mail_use_tls = db.Column(db.Boolean, default=True)
    mail_use_ssl = db.Column(db.Boolean, default=False)
    mail_username = db.Column(db.String(150), nullable=True)
    mail_password = db.Column(db.String(255), nullable=True)
    mail_sender_name = db.Column(db.String(100), default='JESCA Notification')
    mail_target_admins = db.Column(db.Text, nullable=True)  # Comma separated
    # v2.3: Network & Custom Domain Protections
    app_base_url = db.Column(db.String(255), default='http://localhost:5000')
    enforce_https = db.Column(db.Boolean, default=False)
    ip_whitelist_enabled = db.Column(db.Boolean, default=False)
    allowed_ip_ranges = db.Column(db.Text, nullable=True)  # Comma separated IPs or CIDR
    # v2.4.4: Remote Backup Destination (FTP/SFTP)
    remote_backup_enabled = db.Column(db.Boolean, default=False)
    remote_backup_protocol = db.Column(db.String(10), default='ftp')  # ftp / sftp
    remote_backup_host = db.Column(db.String(150), nullable=True)
    remote_backup_port = db.Column(db.Integer, default=21)
    remote_backup_user = db.Column(db.String(100), nullable=True)
    remote_backup_pass = db.Column(db.String(255), nullable=True)
    remote_backup_path = db.Column(db.String(255), default='/')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def get_settings(cls):
        """Fetch singleton setting row (id=1) or create default."""
        setting = cls.query.get(1)
        if not setting:
            setting = cls(
                id=1,
                mail_enabled=False,
                mail_server='smtp.gmail.com',
                mail_port=587,
                mail_use_tls=True,
                mail_use_ssl=False,
                mail_sender_name='JESCA Notification',
                app_base_url='http://localhost:5000',
                enforce_https=False,
                ip_whitelist_enabled=False
            )
            db.session.add(setting)
            db.session.commit()
        return setting


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


def is_sudo_active():
    """Check if current session has an active, unexpired sudo verification (valid 15 minutes)."""
    sudo_until = session.get('sudo_mode_until')
    if not sudo_until:
        return False
    try:
        expiry = datetime.fromisoformat(sudo_until)
        return datetime.utcnow() < expiry
    except Exception:
        return False


def sudo_required(f):
    """
    Step-Up Authentication (Sudo Mode) Decorator.
    Requires password re-verification within the last 15 minutes
    before accessing sensitive administrative actions.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if not is_sudo_active():
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({
                    'error': 'sudo_required',
                    'message': 'Konfirmasi sandi administrator diperlukan (Sudo Mode).'
                }), 403
            return redirect(url_for('confirm_sudo', next=request.url))
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
            'is_sudo_active': is_sudo_active(),
            'csrf_token': lambda: ''
        }
    return {
        'maintenance_alerts': [],
        'warranty_alerts': [],
        'overdue_returns': [],
        'pending_po_alerts': [],
        'user_po_alerts': [],
        'is_sudo_active': False,
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


# ==========================================
# Helpers: Password Cipher & Email Dispatcher
# ==========================================
def encrypt_smtp_password(plain_pwd: str) -> str:
    """Obfuscate SMTP password using XOR cipher with app SECRET_KEY."""
    if not plain_pwd:
        return ""
    key = hashlib.sha256(app.config['SECRET_KEY'].encode()).digest()
    pwd_bytes = plain_pwd.encode('utf-8')
    xored = bytes([b ^ key[i % len(key)] for i, b in enumerate(pwd_bytes)])
    return "enc:" + base64.b64encode(xored).decode('utf-8')


def decrypt_smtp_password(stored_pwd: str) -> str:
    """De-obfuscate stored SMTP password."""
    if not stored_pwd:
        return ""
    if not stored_pwd.startswith("enc:"):
        return stored_pwd  # backward compatibility for plain text
    try:
        raw_b64 = stored_pwd[4:]
        xored = base64.b64decode(raw_b64)
        key = hashlib.sha256(app.config['SECRET_KEY'].encode()).digest()
        decrypted = bytes([b ^ key[i % len(key)] for i, b in enumerate(xored)])
        return decrypted.decode('utf-8')
    except Exception as e:
        app.logger.error(f"Decryption error: {e}")
        return ""


def send_system_email(subject: str, html_body: str, recipient_list=None):
    """
    Sends email via background thread to avoid blocking web request.
    Reads current settings from database on each send.
    """
    def _worker(app_context, subj, html, recips):
        with app_context:
            try:
                setting = SystemSetting.query.get(1)
                if not setting or not setting.mail_enabled:
                    return

                if not setting.mail_server or not setting.mail_username:
                    app.logger.warning("Email dispatch skipped: server or username not configured.")
                    return

                # Build recipient list
                targets = []
                if recips:
                    if isinstance(recips, list):
                        targets.extend(recips)
                    else:
                        targets.append(recips)
                elif setting.mail_target_admins:
                    targets.extend([e.strip() for e in setting.mail_target_admins.split(',') if e.strip()])

                if not targets:
                    return

                sender_addr = setting.mail_username
                sender_name = setting.mail_sender_name or "JESCA Notification"
                decrypted_pwd = decrypt_smtp_password(setting.mail_password)

                msg = MIMEMultipart('alternative')
                msg['Subject'] = subj
                msg['From'] = f"{sender_name} <{sender_addr}>"
                msg['To'] = ", ".join(targets)

                part = MIMEText(html, 'html', 'utf-8')
                msg.attach(part)

                # Connect via SSL or TLS
                if setting.mail_use_ssl:
                    server = smtplib.SMTP_SSL(setting.mail_server, setting.mail_port or 465, timeout=15)
                else:
                    server = smtplib.SMTP(setting.mail_server, setting.mail_port or 587, timeout=15)
                    if setting.mail_use_tls:
                        server.starttls()

                if decrypted_pwd:
                    try:
                        server.login(setting.mail_username, decrypted_pwd)
                    except Exception as auth_err:
                        app.logger.error(f"SMTP Auth failed: {auth_err}")
                        return

                server.sendmail(sender_addr, targets, msg.as_string())
                server.quit()
                app.logger.info(f"Email successfully sent to {targets}: {subj}")
            except Exception as e:
                app.logger.error(f"Failed to dispatch email: {e}")

    # Launch asynchronously
    t = threading.Thread(
        target=_worker,
        args=(app.app_context(), subject, html_body, recipient_list),
        daemon=True
    )
    t.start()


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
            force_password_change=True
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

    # Seed default SystemSetting
    if not SystemSetting.query.get(1):
        db.session.add(SystemSetting(
            id=1,
            mail_enabled=False,
            mail_server='smtp.gmail.com',
            mail_port=587,
            mail_use_tls=True,
            mail_use_ssl=False,
            mail_sender_name='JESCA Notification'
        ))

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

            # Check system_settings columns
            res_ss = conn.execute(db.text("PRAGMA table_info(system_settings)"))
            cols_ss = [row[1] for row in res_ss.fetchall()]
            ss_additions = [
                ('app_base_url', "VARCHAR(255) DEFAULT 'http://localhost:5000'"),
                ('enforce_https', 'BOOLEAN DEFAULT 0'),
                ('ip_whitelist_enabled', 'BOOLEAN DEFAULT 0'),
                ('allowed_ip_ranges', 'TEXT'),
                ('remote_backup_enabled', 'BOOLEAN DEFAULT 0'),
                ('remote_backup_protocol', "VARCHAR(10) DEFAULT 'ftp'"),
                ('remote_backup_host', 'VARCHAR(150)'),
                ('remote_backup_port', 'INTEGER DEFAULT 21'),
                ('remote_backup_user', 'VARCHAR(100)'),
                ('remote_backup_pass', 'VARCHAR(255)'),
                ('remote_backup_path', "VARCHAR(255) DEFAULT '/'")
            ]
            for col_name, col_type in ss_additions:
                if col_name not in cols_ss:
                    conn.execute(db.text(f"ALTER TABLE system_settings ADD COLUMN {col_name} {col_type}"))

            conn.commit()

        # Create any newly defined tables
        db.create_all()
    except Exception as e:
        app.logger.warning(f"Schema update notice: {e}")


# ==========================================
# Helpers: Network & IP Protection
# ==========================================
def get_client_ip():
    """Extract real client IP taking proxies/load balancers into account."""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    if request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP').strip()
    return request.remote_addr or '127.0.0.1'


def is_ip_allowed(client_ip_str: str, allowed_rules_str: str) -> bool:
    """Check if client IP matches allowed list (single IPs or CIDR subnets)."""
    if not allowed_rules_str:
        return True
    try:
        client_ip = ipaddress.ip_address(client_ip_str)
    except ValueError:
        return False

    for rule in allowed_rules_str.split(','):
        rule = rule.strip()
        if not rule:
            continue
        try:
            if '/' in rule:
                network = ipaddress.ip_network(rule, strict=False)
                if client_ip in network:
                    return True
            else:
                target_ip = ipaddress.ip_address(rule)
                if client_ip == target_ip:
                    return True
        except ValueError:
            continue
    return False


# ==========================================
# Middleware: Security, IP Whitelist & HTTPS
# ==========================================
@app.before_request
def enforce_network_and_security():
    # 1. Enforce HTTPS if configured
    try:
        setting = SystemSetting.query.get(1)
    except Exception:
        setting = None

    if setting and setting.enforce_https:
        if request.headers.get('X-Forwarded-Proto', request.scheme) == 'http':
            https_url = request.url.replace('http://', 'https://', 1)
            return redirect(https_url, code=301)

    # 2. IP Whitelisting / VPN Restriction Check
    if setting and setting.ip_whitelist_enabled and setting.allowed_ip_ranges:
        exempt_endpoints = {'static', 'health', 'scan_asset_summary', 'robots'}
        if request.endpoint and request.endpoint not in exempt_endpoints:
            client_ip = get_client_ip()
            # Always permit localhost/loopback
            if client_ip not in ['127.0.0.1', '::1']:
                if not is_ip_allowed(client_ip, setting.allowed_ip_ranges):
                    return render_template('403_network.html', client_ip=client_ip), 403


# ==========================================
# Middleware: Security Headers
# ==========================================
@app.after_request
def add_security_headers(response):
    """Enforce defense-in-depth HTTP security headers."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response


# ==========================================
# Middleware: Force Password Change Check
# ==========================================
@app.before_request
def check_force_password_change():
    exempt_endpoints = {
        'login', 'logout', 'change_password_page', 'static',
        'scan_asset_summary', 'health', 'api_asset_qrcode',
        'confirm_sudo', 'lock_sudo', 'robots'
    }
    if current_user.is_authenticated and getattr(current_user, 'force_password_change', False):
        if request.endpoint and request.endpoint not in exempt_endpoints:
            return redirect(url_for('change_password_page'))


# ==========================================
# Routes: Health, Robots & Auth
# ==========================================
@app.route('/robots.txt')
def robots():
    """Prevent web crawlers from indexing internal inventory data."""
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'version': APP_VERSION,
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
        is_default_admin_password=bool(current_user.role == 'Admin' and current_user.check_password('Admin123')),
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

    # Trigger Async Notification if status changed to 'Rusak' or 'Afkir'
    if old_status != status and status in ['Rusak', 'Afkir']:
        html_alert = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; padding: 20px; border: 1px solid #fee2e2; border-radius: 8px;">
            <div style="background: #ef4444; color: white; padding: 12px 16px; border-radius: 6px 6px 0 0;">
                <h3 style="margin: 0; font-size: 16px;">⚠️ PERINGATAN KONDISI ASET BERMASALAH</h3>
            </div>
            <div style="padding: 16px; background: #fff;">
                <p>Status aset telah diubah menjadi <strong>{status}</strong> oleh <strong>{current_user.full_name}</strong>.</p>
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <tr><td style="padding: 6px 0; color: #64748b;">Kode Aset:</td><td><strong>{asset.asset_code}</strong></td></tr>
                    <tr><td style="padding: 6px 0; color: #64748b;">Nama Aset:</td><td>{asset.name}</td></tr>
                    <tr><td style="padding: 6px 0; color: #64748b;">Kategori:</td><td>{asset.category}</td></tr>
                    <tr><td style="padding: 6px 0; color: #64748b;">Lokasi:</td><td>{asset.location}</td></tr>
                    <tr><td style="padding: 6px 0; color: #64748b;">Waktu:</td><td>{datetime.now().strftime('%d %B %Y %H:%M')}</td></tr>
                </table>
                <p style="margin-top: 15px; font-size: 12px; color: #64748b;">Silakan tindak lanjuti pemeriksaan atau pembuatan jadwal servis melalui menu Pemeliharaan Aset.</p>
            </div>
        </div>
        """
        send_system_email(f"[PERINGATAN ASET] {asset.asset_code} - Status Diubah Menjadi {status}", html_alert)

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

    setting = SystemSetting.query.get(1)
    if setting and setting.app_base_url:
        scan_url = f"{setting.app_base_url.rstrip('/')}{url_for('scan_asset_summary', asset_code=asset.asset_code)}"
    else:
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


def upload_to_remote_backup(local_file_path, setting=None):
    """Uploads backup snapshot file to remote FTP/SFTP server in background."""
    if setting is None:
        setting = SystemSetting.get_settings()
    if not setting or not setting.remote_backup_enabled or not setting.remote_backup_host:
        return False, "Remote backup tidak aktif."

    protocol = (setting.remote_backup_protocol or 'ftp').lower()
    host = setting.remote_backup_host.strip()
    port = int(setting.remote_backup_port or (22 if protocol == 'sftp' else 21))
    user = (setting.remote_backup_user or '').strip()
    passwd = setting.remote_backup_pass or ''
    remote_path = (setting.remote_backup_path or '/').strip()
    filename = os.path.basename(local_file_path)

    try:
        if protocol == 'ftp':
            import ftplib
            ftp = ftplib.FTP()
            ftp.connect(host, port, timeout=20)
            ftp.login(user, passwd)
            if remote_path and remote_path != '/':
                for part in remote_path.strip('/').split('/'):
                    if not part:
                        continue
                    try:
                        ftp.cwd(part)
                    except Exception:
                        try:
                            ftp.mkd(part)
                            ftp.cwd(part)
                        except Exception:
                            pass
            with open(local_file_path, 'rb') as f:
                ftp.storbinary(f"STOR {filename}", f)
            ftp.quit()
            log_activity('REMOTE_BACKUP', details=f"Salinan backup '{filename}' berhasil diunggah ke FTP {host}:{port}{remote_path}")
            return True, f"Berhasil diunggah ke FTP {host}:{port}"

        elif protocol == 'sftp':
            try:
                import paramiko
            except ImportError:
                return False, "Library paramiko belum terpasang untuk SFTP."
            transport = paramiko.Transport((host, port))
            transport.connect(username=user, password=passwd)
            sftp = paramiko.SFTPClient.from_transport(transport)
            if remote_path and remote_path != '/':
                try:
                    sftp.chdir(remote_path)
                except Exception:
                    sftp.mkdir(remote_path)
                    sftp.chdir(remote_path)
            sftp.put(local_file_path, filename)
            sftp.close()
            transport.close()
            log_activity('REMOTE_BACKUP', details=f"Salinan backup '{filename}' berhasil diunggah ke SFTP {host}:{port}{remote_path}")
            return True, f"Berhasil diunggah ke SFTP {host}:{port}"
        else:
            return False, f"Protokol {protocol} tidak didukung."
    except Exception as e:
        app.logger.error(f"Remote backup upload failed: {e}")
        log_activity('REMOTE_BACKUP_FAIL', details=f"Gagal mengunggah backup '{filename}' ke {host}: {str(e)}")
        return False, str(e)


@app.route('/admin/backup', methods=['POST'])
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
    return redirect(url_for('admin_backups'))


@app.route('/admin/backup-remote/config', methods=['POST'])
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
    return redirect(url_for('admin_backups'))


@app.route('/admin/backup-remote/test', methods=['POST'])
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


@app.route('/admin/import-db', methods=['POST'])
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
        return redirect(url_for('admin_backups'))

    if not uploaded.filename.lower().endswith('.db'):
        flash('File harus berformat .db (SQLite database).', 'danger')
        return redirect(url_for('admin_backups'))

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
            return redirect(url_for('admin_backups'))

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
        app.logger.exception(f"import_db_merge error: {e}")
        flash(f'Import gagal: {str(e)}', 'danger')

    finally:
        # Clean up temp file
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    return redirect(url_for('admin_backups'))


@app.route('/admin/import-report/csv')
@login_required
@admin_required
def import_report_csv():
    """Download reconciliation report from last import as CSV."""
    import csv as _csv
    report = session.get('import_report')
    if not report:
        flash('Tidak ada laporan impor yang tersedia.', 'warning')
        return redirect(url_for('admin_backups'))

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


@app.route('/admin/optimize-db', methods=['POST'])
@login_required
@admin_required
@sudo_required
def optimize_database():
    """Optimize SQLite database via VACUUM, PRAGMA optimize, and Integrity Check."""
    import sqlite3 as _sqlite3

    if not os.path.exists(db_path):
        flash('Berkas basis data tidak ditemukan.', 'danger')
        return redirect(url_for('admin_backups'))

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
            return redirect(url_for('admin_backups'))

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
        app.logger.exception(f"optimize_database error: {e}")
        flash(f'Gagal melakukan optimasi basis data: {str(e)}', 'danger')

    return redirect(url_for('admin_backups'))


def auto_backup_job():
    """Daily scheduled auto-backup (2:00 AM) keeping last 30 days retention and optional remote upload."""
    with app.app_context():
        try:
            today_str = datetime.now().strftime('%Y%m%d')
            filename = f"auto_{today_str}.db"
            dst = os.path.join(BACKUP_FOLDER, filename)
            if not os.path.exists(dst) and os.path.exists(db_path):
                shutil.copy2(db_path, dst)
                # Upload to remote FTP/SFTP destination if configured
                upload_to_remote_backup(dst)

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
# Routes: System Settings, Sudo Mode & SMTP Diagnostic
# ==========================================
@app.route('/confirm-sudo', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def confirm_sudo():
    """Sudo mode step-up verification before accessing /settings."""
    next_url = request.args.get('next') or request.form.get('next') or url_for('system_settings')
    if is_sudo_active():
        return redirect(next_url)

    if request.method == 'POST':
        password = request.form.get('password', '')
        if current_user.check_password(password):
            session['sudo_mode_until'] = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
            log_activity('SUDO_ACCESS', details=f"Sudo Mode diverifikasi oleh {current_user.username} (valid 15 menit).")
            flash('Autentikasi Sudo Mode berhasil! Anda memiliki akses aman selama 15 menit.', 'success')
            return redirect(next_url)
        else:
            log_activity('SUDO_FAILED', details=f"Percobaan sandi Sudo Mode gagal oleh {current_user.username}.")
            flash('Kata sandi administrator salah. Silakan coba kembali.', 'danger')

    return render_template('confirm_sudo.html', next_url=next_url)


@app.route('/settings/lock-sudo', methods=['POST'])
@login_required
@role_required('Admin')
def lock_sudo():
    """Manually lock sudo mode session immediately."""
    session.pop('sudo_mode_until', None)
    log_activity('SUDO_LOCKED', details=f"Sudo Mode dikunci secara manual oleh {current_user.username}.")
    flash('Sesi Sudo Mode telah dikunci demi keamanan. Sandi akan diminta kembali saat membuka Pengaturan.', 'info')
    return redirect(url_for('dashboard'))


@app.route('/settings', methods=['GET', 'POST'])
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
        if app_base_url:
            setting.app_base_url = app_base_url.rstrip('/')
        setting.enforce_https = (request.form.get('enforce_https') == '1')
        setting.ip_whitelist_enabled = (request.form.get('ip_whitelist_enabled') == '1')
        setting.allowed_ip_ranges = request.form.get('allowed_ip_ranges', '').strip()

        if mail_password_input:
            setting.mail_password = encrypt_smtp_password(mail_password_input)

        db.session.commit()
        log_activity('EDIT_SETTINGS', details=f"Pengaturan sistem diperbarui oleh {current_user.username}. SMTP: {'Aktif' if mail_enabled else 'Nonaktif'}, Whitelist: {'Aktif' if setting.ip_whitelist_enabled else 'Nonaktif'}.")
        flash('Pengaturan sistem, jaringan, dan SMTP berhasil disimpan!', 'success')
        return redirect(url_for('system_settings'))

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


@app.route('/settings/test-smtp', methods=['POST'])
@login_required
@role_required('Admin')
@sudo_required
def test_smtp_connection():
    """Send test email to test recipient to verify SMTP credentials and handshake."""
    test_target = request.form.get('test_email', '').strip()
    if not test_target:
        flash('Masukkan alamat email tujuan uji coba.', 'warning')
        return redirect(url_for('system_settings'))

    setting = SystemSetting.get_settings()
    if not setting.mail_server or not setting.mail_username:
        flash('Server SMTP dan Username pengirim belum dikonfigurasi.', 'danger')
        return redirect(url_for('system_settings'))

    decrypted_pwd = decrypt_smtp_password(setting.mail_password)

    try:
        sender_addr = setting.mail_username
        sender_name = setting.mail_sender_name or "JESCA Notification"

        msg = MIMEMultipart('alternative')
        msg['Subject'] = "[UJI KONEKSI] Tes Pengiriman Email JESCA"
        msg['From'] = f"{sender_name} <{sender_addr}>"
        msg['To'] = test_target

        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 10px;">
            <div style="background: #1e293b; color: white; padding: 15px 20px; border-radius: 8px 8px 0 0;">
                <h2 style="margin: 0; font-size: 18px;">JESCA &bull; Tes Notifikasi Sistem</h2>
                <small style="color: #94a3b8;">Jessica Assets Management System</small>
            </div>
            <div style="padding: 20px; background: #ffffff;">
                <p>Halo <strong>{current_user.full_name}</strong>,</p>
                <p>Jika Anda menerima email ini, berarti <strong>konfigurasi Dynamic SMTP JESCA Anda telah berhasil terhubung</strong> dengan baik ke server email!</p>
                <div style="background: #f8fafc; border-left: 4px solid #16a34a; padding: 12px; margin: 15px 0;">
                    <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #334155;">
                        <li><strong>Host:</strong> {setting.mail_server}:{setting.mail_port}</li>
                        <li><strong>Enkripsi:</strong> {'SSL' if setting.mail_use_ssl else 'TLS'}</li>
                        <li><strong>Pengirim:</strong> {setting.mail_username}</li>
                        <li><strong>Waktu Tes:</strong> {datetime.now().strftime('%d %B %Y %H:%M:%S')}</li>
                    </ul>
                </div>
                <p style="font-size: 12px; color: #64748b;">Notifikasi otomatis untuk perubahan status aset dan pengajuan Purchase Order siap digunakan.</p>
            </div>
            <div style="text-align: center; font-size: 11px; color: #94a3b8; padding: 10px; border-top: 1px solid #e2e8f0;">
                &copy; 2026 JESCA &bull; Jessica Assets Management System
            </div>
        </div>
        """
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
        app.logger.error(f"SMTP Test Connection Error: {e}")
        flash(f'Koneksi SMTP gagal: {str(e)}', 'danger')

    return redirect(url_for('system_settings'))


# ==========================================
# Routes: System Update Checker & Safe Updater
# ==========================================
@app.route('/api/system/check-update')
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
            return tuple(int(x) for x in parts[:3]) if parts else (0, 0, 0)
        except Exception:
            return (0, 0, 0)

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
        app.logger.error(f"Check update error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'update_available': False
        }), 500


@app.route('/system/update', methods=['POST'])
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
        log_lines.append('🔄 Memulai proses update otomatis JESCA...')
        update_success = False

        # Attempt 1: Git Pull (jika folder .git ada dan binary git terpasang)
        if has_git:
            log_lines.append('📦 [1/3] Menarik perubahan terbaru dari repositori Git...')
            rc = run_cmd(['git', 'pull', 'origin', 'main'])
            if rc == 0:
                update_success = True
                log_lines.append('✅ Git pull berhasil.')
            else:
                log_lines.append('⚠️ Git pull mengalami kendala. Beralih ke mode Auto-Download langsung dari GitHub...')

        # Attempt 2: Fallback ke Direct Archive Download (jika bukan git clone / download ZIP)
        if not update_success:
            log_lines.append('📦 [1/3] Mengunduh arsip rilis terbaru langsung dari GitHub (Mode Tanpa Git)...')
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

                    log_lines.append('📥 Arsip rilis berhasil diunduh. Mengekstrak pembaruan sistem secara aman...')
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
                    log_lines.append('✅ Seluruh berkas pembaruan berhasil diekstrak (database dan berkas unggahan tetap aman).')
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
        log_lines.append('📦 [2/3] Memeriksa & memperbarui dependensi Python...')
        req_file = os.path.join(base, 'requirements.txt')
        if os.path.exists(req_file):
            rc = run_cmd(['pip', 'install', '-r', req_file, '--quiet', '--no-cache-dir'])
            if rc != 0:
                log_lines.append('[WARNING] pip install ada catatan peringatan, melanjutkan proses reload...')
            else:
                log_lines.append('✅ Dependensi Python terverifikasi mutakhir.')

        # Step 3: Graceful restart
        log_lines.append('♻️ [3/3] Mengirim sinyal graceful reload ke Gunicorn...')
        restarted = False

        # Try gunicorn HUP signal via PID file
        gunicorn_pid_file = '/tmp/gunicorn.pid'
        if os.path.exists(gunicorn_pid_file):
            try:
                with open(gunicorn_pid_file) as f:
                    pid = int(f.read().strip())
                os.kill(pid, 1)  # SIGHUP = 1
                log_lines.append(f'✅ SIGHUP terkirim ke Gunicorn PID {pid}.')
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
                    log_lines.append(f'✅ SIGHUP terkirim ke Gunicorn master PID {master_pid}.')
                    restarted = True
            except Exception as e:
                log_lines.append(f'[WARNING] Tidak bisa menemukan proses Gunicorn: {e}')

        # Fallback: touch reload trigger
        if not restarted:
            trigger = os.path.join(base, '.reload_trigger')
            try:
                with open(trigger, 'w') as f:
                    f.write(datetime.utcnow().isoformat())
                log_lines.append(f'ℹ️ File trigger restart dibuat: {trigger}.')
            except Exception:
                pass

        log_activity('SYSTEM_UPDATE', details=f'Update otomatis JESCA berhasil dijalankan oleh {current_user.username}.')
        log_lines.append('✅ Update selesai dengan sukses! Sistem siap digunakan.')
        return jsonify({'status': 'ok', 'message': 'Pembaruan sistem berhasil.', 'log': '\n'.join(log_lines)})

    except subprocess.TimeoutExpired:
        return jsonify({'status': 'error', 'message': 'Update timeout setelah 120 detik.', 'log': '\n'.join(log_lines)}), 500
    except Exception as e:
        app.logger.error(f'System self-update error: {e}')
        return jsonify({'status': 'error', 'message': str(e), 'log': '\n'.join(log_lines)}), 500

    except subprocess.TimeoutExpired:
        return jsonify({'status': 'error', 'message': 'Update timeout setelah 120 detik.', 'log': '\n'.join(log_lines)}), 500
    except Exception as e:
        app.logger.error(f'System self-update error: {e}')
        return jsonify({'status': 'error', 'message': str(e), 'log': '\n'.join(log_lines)}), 500


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

    # Async email notification for PO submission
    html_po = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; padding: 20px; border: 1px solid #bae6fd; border-radius: 8px;">
        <div style="background: #0284c7; color: white; padding: 12px 16px; border-radius: 6px 6px 0 0;">
            <h3 style="margin: 0; font-size: 16px;">📋 PENGAJUAN PURCHASE ORDER BARU</h3>
        </div>
        <div style="padding: 16px; background: #fff;">
            <p>Purchase Order baru memerlukan persetujuan Administrator:</p>
            <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                <tr><td style="padding: 6px 0; color: #64748b;">Nomor PO:</td><td><strong>{po.po_number}</strong></td></tr>
                <tr><td style="padding: 6px 0; color: #64748b;">Judul:</td><td>{po.title}</td></tr>
                <tr><td style="padding: 6px 0; color: #64748b;">Pemohon:</td><td>{po.requested_by}</td></tr>
                <tr><td style="padding: 6px 0; color: #64748b;">Estimasi Nilai:</td><td><strong>Rp {po.estimated_total:,.0f}</strong></td></tr>
                <tr><td style="padding: 6px 0; color: #64748b;">Jumlah Item:</td><td>{po.total_items_quantity} unit</td></tr>
            </table>
            <p style="margin-top: 15px; font-size: 12px; color: #64748b;">Silakan masuk ke sistem JESCA untuk menyetujui atau menolak pengajuan ini.</p>
        </div>
    </div>
    """
    send_system_email(f"[PERLU PERSETUJUAN] PO {po.po_number} - {po.title}", html_po)

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
