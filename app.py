import os
import re
import csv
import io
import uuid
from functools import wraps
from datetime import datetime, date, timedelta
from urllib.parse import quote

from flask import (
    Flask, render_template, request, redirect, url_for, flash, jsonify, Response, send_from_directory
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

# ==========================================
# Application Configuration
# ==========================================
app = Flask(__name__)

# Base directories
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Max 16MB upload

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

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
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), default='Administrator')
    role = db.Column(db.String(30), default='Admin')  # Admin, Staff, Auditor, Teknisi
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else ''
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
            flash('Akses ditolak. Fitur ini hanya dapat diakses oleh Administrator.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# ==========================================
# Activity Logging Helper
# ==========================================
def log_activity(action, asset_code=None, asset_name=None, details=None):
    """Save an activity log record into database."""
    try:
        username = current_user.username if current_user.is_authenticated else 'System'
        user_id = current_user.id if current_user.is_authenticated else None
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


# ==========================================
# Maintenance Notification Helper
# ==========================================
def get_maintenance_notifications():
    """
    Finds all assets that have maintenance scheduled within 7 days or are overdue.
    """
    today = date.today()
    threshold = today + timedelta(days=7)
    
    due_assets = Asset.query.filter(
        Asset.needs_maintenance == True,
        Asset.next_maintenance_date != None,
        Asset.next_maintenance_date <= threshold
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


# Context processor so maintenance alerts are automatically available in all templates
@app.context_processor
def inject_maintenance_alerts():
    if current_user.is_authenticated:
        alerts = get_maintenance_notifications()
        return {'maintenance_alerts': alerts}
    return {'maintenance_alerts': []}


# ==========================================
# Image Upload Helper
# ==========================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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
# Helper Functions: Auto-Coding
# ==========================================
def get_category_prefix(category_name):
    """Resolve category code prefix (e.g., Tech -> Tech, Tools -> Tools, Furniture -> Furn)"""
    if not category_name:
        return 'AST'
    if category_name in CATEGORY_PREFIX_MAP:
        return CATEGORY_PREFIX_MAP[category_name]
    clean = re.sub(r'[^a-zA-Z0-9]', '', category_name)
    return clean[:5].capitalize() if clean else 'AST'


def generate_asset_code(category_name):
    """Auto-coding generator: finds existing codes like '<Prefix>/001' and increments."""
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
# Database Seeder & Schema Check
# ==========================================
def seed_database():
    """Initializes default admin user if not already present."""
    admin_user = User.query.filter_by(username='Admin').first()
    if not admin_user:
        admin_user = User(
            username='Admin',
            full_name='Jessica (Admin JESCA)',
            role='Admin'
        )
        admin_user.set_password('Admin123')
        db.session.add(admin_user)
        db.session.commit()


def check_and_update_schema():
    """Ensure newly added columns exist in sqlite table without error."""
    try:
        with db.engine.connect() as conn:
            # Check assets columns
            res = conn.execute(db.text("PRAGMA table_info(assets)"))
            cols = [row[1] for row in res.fetchall()]
            if 'image' not in cols:
                conn.execute(db.text("ALTER TABLE assets ADD COLUMN image VARCHAR(255)"))
            if 'borrower' not in cols:
                conn.execute(db.text("ALTER TABLE assets ADD COLUMN borrower VARCHAR(100)"))
            if 'borrow_date' not in cols:
                conn.execute(db.text("ALTER TABLE assets ADD COLUMN borrow_date DATETIME"))
            if 'needs_maintenance' not in cols:
                conn.execute(db.text("ALTER TABLE assets ADD COLUMN needs_maintenance BOOLEAN DEFAULT 0"))
            if 'maintenance_interval_days' not in cols:
                conn.execute(db.text("ALTER TABLE assets ADD COLUMN maintenance_interval_days INTEGER"))
            if 'next_maintenance_date' not in cols:
                conn.execute(db.text("ALTER TABLE assets ADD COLUMN next_maintenance_date DATE"))
            if 'last_maintenance_date' not in cols:
                conn.execute(db.text("ALTER TABLE assets ADD COLUMN last_maintenance_date DATE"))

            # Check users columns
            res_u = conn.execute(db.text("PRAGMA table_info(users)"))
            cols_u = [row[1] for row in res_u.fetchall()]
            if 'is_active' not in cols_u:
                conn.execute(db.text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1"))

            conn.commit()
    except Exception as e:
        app.logger.warning(f"Schema update notice: {e}")


# ==========================================
# Routes & Views: Auth & Self-Service
# ==========================================

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
        if user and user.check_password(password):
            if not getattr(user, 'is_active', True):
                flash('Akun Anda dinonaktifkan. Silakan hubungi Administrator.', 'danger')
                return render_template('login.html')

            login_user(user, remember=remember)
            log_activity('LOGIN', details=f"Pengguna {user.username} ({user.role}) berhasil masuk ke sistem.")
            flash(f'Selamat datang kembali, {user.full_name}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Username atau password salah. Silakan coba lagi.', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    log_activity('LOGOUT', details=f"Pengguna {current_user.username} keluar dari sistem.")
    logout_user()
    flash('Anda telah berhasil keluar dari sistem JESCA.', 'info')
    return redirect(url_for('login'))


@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """Self-service password update for currently logged-in user."""
    old_password = request.form.get('old_password', '').strip()
    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()

    if not current_user.check_password(old_password):
        flash('Password lama yang Anda masukkan tidak sesuai.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))

    if len(new_password) < 6:
        flash('Password baru minimal terdiri dari 6 karakter.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))

    if new_password != confirm_password:
        flash('Konfirmasi password baru tidak cocok.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))

    current_user.set_password(new_password)
    db.session.commit()
    log_activity('GANTI_PASSWORD', details=f"Pengguna {current_user.username} memperbarui password akunnya sendiri.")
    flash('Password Anda berhasil diperbarui!', 'success')
    return redirect(request.referrer or url_for('dashboard'))


# ==========================================
# Routes: Dashboard
# ==========================================

@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard view with statistics, maintenance alerts, charts, and recent activity."""
    total_assets = Asset.query.count()
    total_value = db.session.query(db.func.sum(Asset.purchase_price)).scalar() or 0.0

    # Status counts
    active_count = Asset.query.filter_by(status='Aktif').count()
    borrowed_count = Asset.query.filter_by(status='Dipinjam').count()
    maintenance_count = Asset.query.filter_by(status='Dalam Perbaikan').count()
    broken_count = Asset.query.filter_by(status='Rusak').count()
    retired_count = Asset.query.filter_by(status='Afkir').count()

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

    # Status breakdown for Chart.js
    status_labels = STATUS_CHOICES
    status_counts = [
        Asset.query.filter_by(status=st).count() for st in status_labels
    ]

    # Recent 5 Assets
    recent_assets = Asset.query.order_by(Asset.created_at.desc(), Asset.id.desc()).limit(5).all()

    # Recent 6 Activity Logs
    recent_logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(6).all()

    # Active percentage
    active_percentage = round((active_count / total_assets * 100), 1) if total_assets > 0 else 0

    # Maintenance alerts in dashboard
    maintenance_alerts = get_maintenance_notifications()

    return render_template(
        'dashboard.html',
        total_assets=total_assets,
        total_value=total_value,
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
        categories=DEFAULT_CATEGORIES,
        statuses=STATUS_CHOICES
    )


# ==========================================
# Routes: Assets CRUD & Operations
# ==========================================

@app.route('/assets')
@login_required
def assets():
    """Asset management page with searching, category, status, and maintenance filters."""
    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()
    status_filter = request.args.get('status', '').strip()
    maintenance_filter = request.args.get('maintenance', '').strip()

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

    if maintenance_filter == 'due':
        today = date.today()
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

    today = date.today()

    return render_template(
        'assets.html',
        assets=asset_list,
        search_query=search_query,
        category_filter=category_filter,
        status_filter=status_filter,
        maintenance_filter=maintenance_filter,
        filtered_value=filtered_value,
        categories=DEFAULT_CATEGORIES,
        statuses=STATUS_CHOICES,
        today=today
    )


@app.route('/assets/create', methods=['POST'])
@login_required
def create_asset():
    """Create a new asset with photo upload, maintenance settings, auto-coding, and logging."""
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

    if not name:
        flash('Nama aset wajib diisi.', 'danger')
        return redirect(url_for('assets'))

    # Parse date
    try:
        purchase_date = datetime.strptime(purchase_date_str, '%Y-%m-%d').date() if purchase_date_str else date.today()
    except ValueError:
        purchase_date = date.today()

    # Parse price
    try:
        clean_price = purchase_price_str.replace('.', '').replace(',', '.').replace('Rp', '').strip()
        purchase_price = float(clean_price) if clean_price else 0.0
    except ValueError:
        purchase_price = 0.0

    # Auto-coding logic
    if custom_code:
        if Asset.query.filter_by(asset_code=custom_code).first():
            flash(f'Kode aset "{custom_code}" sudah digunakan. Silakan gunakan kode lain atau auto-generate.', 'danger')
            return redirect(url_for('assets'))
        asset_code = custom_code
    else:
        asset_code = generate_asset_code(category)

    # Handle Maintenance scheduling
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

    # Handle Photo Upload
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
        last_maintenance_date=None
    )

    db.session.add(new_asset)
    db.session.commit()

    # Log Activity
    maint_note = f"Maintenance: Tiap {maintenance_interval_days} hari (Jadwal: {next_maintenance_date})" if needs_maintenance else "Maintenance: -"
    log_activity(
        'TAMBAH_ASET',
        asset_code=new_asset.asset_code,
        asset_name=new_asset.name,
        details=f"Aset baru ditambahkan ({category}, Lokasi: {location}, Nilai: Rp {purchase_price:,.0f}). {maint_note}."
    )

    flash(f'Aset "{new_asset.name}" berhasil ditambahkan dengan kode: {new_asset.asset_code}!', 'success')
    return redirect(url_for('assets'))


@app.route('/assets/<int:asset_id>/edit', methods=['POST'])
@login_required
def edit_asset(asset_id):
    """Edit existing asset details, maintenance schedule, and optionally replace photo."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('assets'))

    name = request.form.get('name', '').strip()
    category = request.form.get('category', asset.category).strip()
    purchase_date_str = request.form.get('purchase_date', '').strip()
    purchase_price_str = request.form.get('purchase_price', '').strip()
    location = request.form.get('location', '').strip()
    status = request.form.get('status', asset.status).strip()
    description = request.form.get('description', '').strip()
    asset_code = request.form.get('asset_code', asset.asset_code).strip()

    # Maintenance inputs
    needs_maintenance_raw = request.form.get('needs_maintenance', '0').strip()
    needs_maintenance = (needs_maintenance_raw == '1')
    interval_str = request.form.get('maintenance_interval_days', '').strip()
    next_maint_date_str = request.form.get('next_maintenance_date', '').strip()

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

    # Update Maintenance fields
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

    # Check if new photo was uploaded
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

    log_activity(
        'EDIT_ASET',
        asset_code=asset.asset_code,
        asset_name=asset.name,
        details=f"Data aset diperbarui: Status: {status}, Maintenance: {'Ya' if needs_maintenance else 'Tidak'}."
    )

    flash(f'Perubahan aset [{asset.asset_code}] berhasil disimpan!', 'success')
    return redirect(url_for('assets'))


@app.route('/assets/<int:asset_id>/delete', methods=['POST'])
@login_required
def delete_asset(asset_id):
    """Delete an asset record and its image from disk."""
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
def checkout_asset(asset_id):
    """Check Out (Pinjam Aset): Mark asset as 'Dipinjam' with borrower name."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
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
def checkin_asset(asset_id):
    """Check In (Pengembalian Aset): Mark asset as 'Aktif' and clear borrower."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('assets'))

    prev_borrower = asset.borrower or 'Peminjam'
    new_status = request.form.get('status', 'Aktif').strip()
    return_notes = request.form.get('notes', '').strip()

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
def complete_maintenance(asset_id):
    """Mark current maintenance as completed, advance next date by interval, and log."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        flash('Aset tidak ditemukan.', 'danger')
        return redirect(url_for('assets'))

    notes = request.form.get('notes', '').strip()
    today = date.today()
    interval = asset.maintenance_interval_days or 90

    asset.last_maintenance_date = today
    asset.next_maintenance_date = today + timedelta(days=interval)
    db.session.commit()

    next_date_str = asset.next_maintenance_date.strftime('%d/%m/%Y')
    log_activity(
        'MAINTENANCE_SELESAI',
        asset_code=asset.asset_code,
        asset_name=asset.name,
        details=f"Pemeliharaan selesai dicatat oleh {current_user.username}. Jadwal berikutnya: {next_date_str} (Interval: {interval} hari). Catatan: {notes or '-'}"
    )

    flash(f'Maintenance untuk [{asset.asset_code}] selesai dicatat! Jadwal berikutnya: {next_date_str}.', 'success')
    return redirect(request.referrer or url_for('assets'))


# ==========================================
# Routes: QR Code & Scan Summary
# ==========================================

@app.route('/scan/<path:asset_code>')
def scan_asset_summary(asset_code):
    """
    Public Asset Summary Page rendered when someone scans the Asset QR Tag.
    Accessible on mobile/scanner without requiring login!
    """
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
        today=today
    )


@app.route('/api/assets/<int:asset_id>/qrcode')
def api_asset_qrcode(asset_id):
    """Generate QR Code image pointing directly to the asset's scan summary URL."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        return jsonify({'error': 'Not found'}), 404

    # The QR Code contains the URL to the scan summary page
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
        # Fallback to QuickChart QR API
        api_url = f"https://quickchart.io/qr?text={quote(scan_url)}&size=250&margin=2"
        return redirect(api_url)


@app.route('/api/generate-code', methods=['GET'])
@login_required
def api_generate_code():
    """AJAX endpoint for real-time asset auto-coding preview based on selected category."""
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
    """AJAX endpoint returning asset details as JSON for edit/detail/check-out modals."""
    asset = db.session.get(Asset, asset_id)
    if not asset:
        return jsonify({'status': 'error', 'message': 'Asset not found'}), 404
    return jsonify({'status': 'success', 'data': asset.to_dict()})


@app.route('/assets/export/csv')
@login_required
def export_assets_csv():
    """Export current assets list to CSV format with UTF-8 BOM."""
    assets = Asset.query.order_by(Asset.asset_code.asc()).all()

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')

    writer.writerow([
        'ID',
        'Kode Aset',
        'Nama Aset',
        'Kategori',
        'Lokasi',
        'Tanggal Perolehan',
        'Nilai Perolehan (IDR)',
        'Status',
        'Peminjam',
        'Perlu Maintenance',
        'Interval (Hari)',
        'Jadwal Maintenance',
        'Foto File',
        'Deskripsi / Catatan'
    ])

    for a in assets:
        writer.writerow([
            a.id,
            a.asset_code,
            a.name,
            a.category,
            a.location,
            a.purchase_date.strftime('%Y-%m-%d') if a.purchase_date else '',
            f"{a.purchase_price:.2f}",
            a.status,
            a.borrower or '-',
            'Ya' if a.needs_maintenance else 'Tidak',
            a.maintenance_interval_days or '-',
            a.next_maintenance_date.strftime('%Y-%m-%d') if a.next_maintenance_date else '-',
            a.image or '-',
            (a.description or '').replace('\n', ' ')
        ])

    log_activity('EXPORT_CSV', details=f"Ekspor laporan {len(assets)} data aset ke format CSV.")

    filename = f"jesca_assets_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ==========================================
# Routes: Activity Log & History
# ==========================================

@app.route('/history')
@login_required
def history():
    """Activity Log / History page with search & filter."""
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
        'TAMBAH_ASET', 'EDIT_ASET', 'HAPUS_ASET',
        'CHECK_OUT', 'CHECK_IN', 'MAINTENANCE_SELESAI',
        'LOGIN', 'GANTI_PASSWORD', 'TAMBAH_USER', 'EDIT_USER', 'RESET_PASSWORD_USER', 'HAPUS_USER'
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
    """Clear activity logs (Admin only)."""
    ActivityLog.query.delete()
    db.session.commit()
    log_activity('CLEAR_LOGS', details="Riwayat log aktivitas telah dibersihkan oleh Administrator.")
    flash('Seluruh riwayat aktivitas telah dibersihkan.', 'info')
    return redirect(url_for('history'))


# ==========================================
# Routes: Accounts Management (Admin Only)
# ==========================================

@app.route('/accounts')
@login_required
@admin_required
def accounts():
    """Accounts management view for Administrators."""
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
    """Backward compatibility redirect to /accounts."""
    return redirect(url_for('accounts'))


@app.route('/accounts/create', methods=['POST'])
@login_required
@admin_required
def create_account():
    """Create a new user account with role."""
    username = request.form.get('username', '').strip()
    full_name = request.form.get('full_name', '').strip()
    role = request.form.get('role', 'Staff').strip()
    password = request.form.get('password', '').strip()

    if not username or not password:
        flash('Username dan password wajib diisi.', 'danger')
        return redirect(url_for('accounts'))

    if len(password) < 6:
        flash('Password minimal harus 6 karakter.', 'danger')
        return redirect(url_for('accounts'))

    if User.query.filter_by(username=username).first():
        flash(f'Username "{username}" sudah terdaftar. Silakan gunakan username lain.', 'danger')
        return redirect(url_for('accounts'))

    new_user = User(
        username=username,
        full_name=full_name or username,
        role=role,
        is_active=True
    )
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()

    log_activity(
        'TAMBAH_USER',
        details=f"Akun baru dibuat oleh Admin: {username} ({full_name}) dengan role {role}."
    )

    flash(f'Akun baru "{username}" dengan role {role} berhasil dibuat!', 'success')
    return redirect(url_for('accounts'))


@app.route('/accounts/<int:user_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_account(user_id):
    """Edit user details (Full Name, Role, Active Status)."""
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
    """Admin directly changes/resets password for any account."""
    target_user = db.session.get(User, user_id)
    if not target_user:
        flash('Pengguna tidak ditemukan.', 'danger')
        return redirect(url_for('accounts'))

    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()

    if not new_password or len(new_password) < 6:
        flash('Password baru minimal harus 6 karakter.', 'danger')
        return redirect(url_for('accounts'))

    if new_password != confirm_password:
        flash('Konfirmasi password tidak cocok.', 'danger')
        return redirect(url_for('accounts'))

    target_user.set_password(new_password)
    db.session.commit()

    log_activity(
        'RESET_PASSWORD_USER',
        details=f"Password akun {target_user.username} diubah/direset oleh Administrator ({current_user.username})."
    )

    flash(f'Password untuk akun "{target_user.username}" berhasil diubah!', 'success')
    return redirect(url_for('accounts'))


@app.route('/accounts/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_account(user_id):
    """Delete a user account (cannot delete self)."""
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

    log_activity(
        'HAPUS_USER',
        details=f"Akun {u_name} dihapus dari sistem oleh {current_user.username}."
    )

    flash(f'Akun "{u_name}" telah berhasil dihapus.', 'info')
    return redirect(url_for('accounts'))


# ==========================================
# Initialize Database Tables & Seed
# ==========================================
with app.app_context():
    db.create_all()
    check_and_update_schema()
    seed_database()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
