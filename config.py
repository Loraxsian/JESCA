import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
AVATAR_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'avatars')
ATTACHMENT_FOLDER = os.path.join(BASE_DIR, 'static', 'attachments')
PO_ATTACHMENT_FOLDER = os.path.join(BASE_DIR, 'static', 'attachments', 'po')
MAINT_ATTACHMENT_FOLDER = os.path.join(BASE_DIR, 'static', 'attachments', 'maintenance')
BACKUP_FOLDER = os.path.join(BASE_DIR, 'backups')
QRCODE_FOLDER = os.path.join(BASE_DIR, 'static', 'qrcodes')

APP_VERSION = '3.0.0'
GITHUB_REPO = 'Loraxsian/JESCA'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
ALLOWED_ATTACHMENT_EXTENSIONS = {'pdf', 'docx', 'doc', 'jpg', 'jpeg', 'png', 'xlsx', 'xls', 'txt'}

CATEGORY_CUSTOM_FIELDS = {
    'Tech': ['serial_number', 'ip_address', 'mac_address', 'os_version'],
    'Vehicle': ['plate_number', 'chassis_number', 'bpkb_number', 'color'],
    'Tools': ['serial_number', 'power_watt'],
    'Furniture': ['material', 'color'],
    'Office': ['serial_number', 'model_number'],
}

CATEGORY_PREFIX_MAP = {
    'Tech': 'Tech',
    'Tools': 'Tools',
    'Furniture': 'Furn',
    'Vehicle': 'Vehicle',
    'Office': 'Office',
    'Elektronik': 'Elek',
    'Mesin': 'Mesin',
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

db_path = os.path.join(DATA_DIR, 'jesca.db')


def ensure_directories():
    for folder in (
        DATA_DIR, UPLOAD_FOLDER, AVATAR_FOLDER, ATTACHMENT_FOLDER,
        PO_ATTACHMENT_FOLDER, MAINT_ATTACHMENT_FOLDER, BACKUP_FOLDER, QRCODE_FOLDER
    ):
        os.makedirs(folder, exist_ok=True)


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'jesca-super-secret-key-change-in-production-2024')
    env_db_url = os.environ.get('DATABASE_URL')
    if env_db_url and env_db_url.startswith('sqlite:///data/'):
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path}'
    elif env_db_url:
        SQLALCHEMY_DATABASE_URI = env_db_url
    else:
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path}'

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    if SQLALCHEMY_DATABASE_URI.startswith('sqlite'):
        SQLALCHEMY_ENGINE_OPTIONS = {'connect_args': {'timeout': 30}}

    UPLOAD_FOLDER = UPLOAD_FOLDER
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_REFRESH_EACH_REQUEST = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
