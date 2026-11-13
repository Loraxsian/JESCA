import os
import re
import uuid
import base64
import hashlib
import ipaddress
import secrets
from datetime import datetime, timezone, timedelta
from flask import request, current_app
from werkzeug.utils import secure_filename

from config import (
    ALLOWED_EXTENSIONS, ALLOWED_ATTACHMENT_EXTENSIONS,
    UPLOAD_FOLDER, PO_ATTACHMENT_FOLDER, MAINT_ATTACHMENT_FOLDER, AVATAR_FOLDER,
    CATEGORY_PREFIX_MAP
)
from extensions import db
from models.asset import Asset
from models.purchase_order import PurchaseOrder
from models.system import SystemSetting

WIB = timezone(timedelta(hours=7))


def _app_secret():
    from flask import current_app
    return current_app.config.get('SECRET_KEY', 'jesca-super-secret-key-change-in-production-2024')


def validate_password(password):
    """Returns (is_valid, error_message). Min 8 chars, at least 1 letter + 1 digit."""
    if len(password) < 8:
        return False, 'Password minimal 8 karakter.'
    if not re.search(r'[a-zA-Z]', password):
        return False, 'Password harus mengandung minimal satu huruf.'
    if not re.search(r'[0-9]', password):
        return False, 'Password harus mengandung minimal satu angka.'
    return True, None


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
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
        file_storage.save(filepath)
        return unique_name
    return None


def delete_photo_file(filename):
    """Delete uploaded photo file from static/uploads."""
    if filename:
        try:
            path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            current_app.logger.error(f"Error removing image file: {e}")


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
            current_app.logger.error(f"Error removing avatar file: {e}")


def encrypt_smtp_password(plain_pwd: str) -> str:
    """Obfuscate SMTP password using XOR cipher with app SECRET_KEY."""
    if not plain_pwd:
        return ""
    key = hashlib.sha256(_app_secret().encode()).digest()
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
        key = hashlib.sha256(_app_secret().encode()).digest()
        decrypted = bytes([b ^ key[i % len(key)] for i, b in enumerate(xored)])
        return decrypted.decode('utf-8')
    except Exception as e:
        current_app.logger.error(f"Decryption error: {e}")
        return ""


def get_wib_now():
    """Return current datetime in WIB (UTC+7)."""
    return datetime.now(WIB)


def format_wib_datetime(dt=None):
    """Format datetime into Indonesian WIB format: '04 November 2026, 11:42:13 WIB'."""
    if dt is None:
        dt = get_wib_now()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc).astimezone(WIB)
    else:
        dt = dt.astimezone(WIB)
    months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    return f"{dt.day:02d} {months[dt.month - 1]} {dt.year}, {dt.strftime('%H:%M:%S')} WIB"


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

