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
ATTACHMENT_FOLDER = os.path.join(BASE_DIR, 'static', 'attachments')
BACKUP_FOLDER = os.path.join(BASE_DIR, 'backups')
QRCODE_FOLDER = os.path.join(BASE_DIR, 'static', 'qrcodes')

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(ATTACHMENT_FOLDER, exist_ok=True)
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

    # Relationships to models
    vendor = db.relationship('Vendor', backref='assets', lazy=True)
    site = db.relationship('Site', backref='assets', lazy=True)

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
        years_elapsed = (date.today() - self.purchase_date).days / 365.25
        annual_dep = ((self.purchase_price or 0) - (self.salvage_value or 0)) / self.useful_life_years
        book_value = (self.purchase_price or 0) - (annual_dep * years_elapsed)
        return round(max(book_value, self.salvage_value or 0), 2)

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
            'last_transfer_from': self.last_transfer_from or ''
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
        return {
            'maintenance_alerts': alerts,
            'warranty_alerts': warranty_alerts,
            'overdue_returns': overdue_returns
        }
    return {'maintenance_alerts': [], 'warranty_alerts': [], 'overdue_returns': []}


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
                ('last_transfer_from', 'VARCHAR(100)')
            ]
            for col_name, col_type in asset_additions:
                if col_name not in cols:
                    conn.execute(db.text(f"ALTER TABLE assets ADD COLUMN {col_name} {col_type}"))

            # Check users columns
            res_u = conn.execute(db.text("PRAGMA table_info(users)"))
            cols_u = [row[1] for row in res_u.fetchall()]
            user_additions = [
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

            conn.commit()
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

    # Recent items
    recent_assets = Asset.query.order_by(Asset.created_at.desc(), Asset.id.desc()).limit(5).all()
    recent_logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(6).all()
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
        statuses=STATUS_CHOICES
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

    if asset.status == 'Dipinjam':
        flash(f'Aset sedang dipinjam oleh {asset.borrower}. Selesaikan check-in terlebih dahulu.', 'warning')
        return redirect(url_for('assets'))

    borrower = request.form.get('borrower', '').strip()
    notes = request.form.get('notes', '').strip()

    if not borrower:
        flash('Nama peminjam wajib diisi.', 'danger')
        return redirect(url_for('assets'))

    asset.status = 'Dipinjam'
    asset.borrower = borrower
    asset.borrow_date = datetime.utcnow()
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
    """Check In (Pengembalian Aset) with utilization tracking."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('assets'))

    prev_borrower = asset.borrower or 'Peminjam'
    new_status = request.form.get('status', 'Aktif').strip()
    return_notes = request.form.get('notes', '').strip()

    # Track utilization days
    if asset.borrow_date:
        days_borrowed = max(1, (datetime.utcnow() - asset.borrow_date).days)
        asset.total_checkout_days = (asset.total_checkout_days or 0) + days_borrowed

    asset.status = new_status
    asset.borrower = None
    asset.borrow_date = None
    db.session.commit()

    log_activity(
        'CHECK_IN',
        asset_code=asset.asset_code,
        asset_name=asset.name,
        details=f"Aset dikembalikan oleh: {prev_borrower}. Status sekarang: {new_status}. Catatan: {return_notes or '-'}"
    )

    flash(f'Aset [{asset.asset_code}] berhasil dikembalikan (Status: {new_status}).', 'success')
    return redirect(url_for('assets'))


@app.route('/assets/<int:asset_id>/complete-maintenance', methods=['POST'])
@login_required
@role_required('Admin', 'Staff', 'Teknisi')
def complete_maintenance(asset_id):
    """Mark current maintenance as completed and schedule next date."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('assets'))

    notes = request.form.get('notes', '').strip()
    today = date.today()
    interval = asset.maintenance_interval_days or 90

    asset.last_maintenance_date = today
    asset.next_maintenance_date = today + timedelta(days=interval)
    if asset.status == 'Dalam Perbaikan':
        asset.status = 'Aktif'

    db.session.commit()

    next_date_str = asset.next_maintenance_date.strftime('%d/%m/%Y')
    log_activity(
        'MAINTENANCE_SELESAI',
        asset_code=asset.asset_code,
        asset_name=asset.name,
        details=f"Pemeliharaan selesai dicatat oleh {current_user.username}. Jadwal berikutnya: {next_date_str}. Catatan: {notes or '-'}"
    )

    flash(f'Maintenance untuk [{asset.asset_code}] selesai dicatat! Jadwal berikutnya: {next_date_str}.', 'success')
    return redirect(request.referrer or url_for('assets'))


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

    title_text = "LAPORAN INVENTARIS ASET PERUSAHAAN"
    sub_text = f"Jessica Assets Management System (JESCA v2.0) | Tanggal Cetak: {datetime.now().strftime('%d %B %Y %H:%M')} | Dicetak oleh: {current_user.full_name}"

    elements.append(Paragraph(f"<b><font size=14 color='#1e293b'>{title_text}</font></b>", styles['Normal']))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(f"<font size=8 color='#64748b'>{sub_text}</font>", styles['Normal']))
    elements.append(Spacer(1, 14))

    table_data = [
        ['No', 'Kode Aset', 'Nama Aset', 'Kategori', 'Lokasi', 'Status', 'Nilai Perolehan', 'Nilai Buku', 'Maintenance']
    ]

    for idx, a in enumerate(assets_list, 1):
        maint_str = a.next_maintenance_date.strftime('%d/%m/%Y') if a.next_maintenance_date else '-'
        table_data.append([
            str(idx),
            a.asset_code,
            a.name[:30],
            a.category,
            a.location[:18],
            a.status,
            f"Rp {a.purchase_price:,.0f}".replace(',', '.'),
            f"Rp {a.current_book_value:,.0f}".replace(',', '.'),
            maint_str
        ])

    pdf_table = Table(table_data, repeatRows=1)
    pdf_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), rl_colors.HexColor('#4361ee')),
        ('TEXTCOLOR', (0, 0), (-1, 0), rl_colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 7.5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor('#f8fafc')]),
        ('GRID', (0, 0), (-1, -1), 0.5, rl_colors.HexColor('#cbd5e1')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (1, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (6, 1), (7, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
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
@role_required('Admin', 'Staff')
def sites():
    site_list = Site.query.order_by(Site.name.asc()).all()
    return render_template('sites.html', sites=site_list)


@app.route('/sites/create', methods=['POST'])
@login_required
@role_required('Admin', 'Staff')
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
@role_required('Admin', 'Staff')
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
def export_assets_csv():
    assets_all = Asset.query.order_by(Asset.asset_code.asc()).all()

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')

    writer.writerow([
        'ID', 'Kode Aset', 'Nama Aset', 'Kategori', 'Lokasi',
        'Tanggal Perolehan', 'Nilai Perolehan (IDR)', 'Nilai Buku (IDR)', 'Status',
        'Peminjam', 'Vendor', 'Site', 'Garansi Mulai', 'Garansi Selesai',
        'Perlu Maintenance', 'Interval (Hari)', 'Jadwal Maintenance', 'Deskripsi'
    ])

    for a in assets_all:
        writer.writerow([
            a.id,
            a.asset_code,
            a.name,
            a.category,
            a.location,
            a.purchase_date.strftime('%Y-%m-%d') if a.purchase_date else '',
            f"{a.purchase_price:.2f}",
            f"{a.current_book_value:.2f}",
            a.status,
            a.borrower or '-',
            a.vendor.name if a.vendor else '-',
            a.site.name if a.site else '-',
            a.warranty_start.strftime('%Y-%m-%d') if a.warranty_start else '-',
            a.warranty_end.strftime('%Y-%m-%d') if a.warranty_end else '-',
            'Ya' if a.needs_maintenance else 'Tidak',
            a.maintenance_interval_days or '-',
            a.next_maintenance_date.strftime('%Y-%m-%d') if a.next_maintenance_date else '-',
            (a.description or '').replace('\n', ' ')
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
@role_required('Admin', 'Auditor', 'Staff')
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
