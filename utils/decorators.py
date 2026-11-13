from functools import wraps
from datetime import datetime
from flask import request, redirect, url_for, flash, jsonify, session
from flask_login import current_user
from models.user import User
from models.system import SystemSetting


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['Admin', 'Administrator']:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Forbidden', 'message': 'Fitur ini hanya untuk Administrator'}), 403
            flash('Akses ditolak. Fitur ini hanya dapat diakses oleh Administrator.', 'danger')
            return redirect(url_for('main.dashboard'))
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
                return redirect(url_for('auth.login'))
            if current_user.role not in roles:
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({
                        'error': 'Forbidden',
                        'message': f'Akses ditolak. Role yang dibutuhkan: {", ".join(roles)}',
                        'your_role': current_user.role
                    }), 403
                flash(f'Akses ditolak. Fitur ini hanya untuk: {", ".join(roles)}.', 'danger')
                return redirect(url_for('main.dashboard'))
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
    Step-Up Authentication (Mode Akses Khusus / Sudo).
    Always enforces sudo for destructive actions; allows toggling Settings access via SystemSetting.sudo_mode_enabled.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if request.endpoint == 'admin.system_settings':
            try:
                setting = SystemSetting.get_settings()
                if not getattr(setting, 'sudo_mode_enabled', True):
                    return f(*args, **kwargs)
            except Exception:
                pass
        if not is_sudo_active():
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({
                    'error': 'sudo_required',
                    'message': 'Konfirmasi sandi administrator diperlukan (Mode Akses Khusus / Sudo).'
                }), 403
            return redirect(url_for('auth.confirm_sudo', next=request.url))
        return f(*args, **kwargs)
    return decorated
