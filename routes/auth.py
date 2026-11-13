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
from services.tunnel_service import start_quick_tunnel, stop_quick_tunnel, get_quick_tunnel_status

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

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
                return redirect(url_for('auth.change_password_page'))

            flash(f'Selamat datang kembali, {user.full_name}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))
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


@auth_bp.route('/logout')
@login_required
def logout():
    log_activity('LOGOUT', details=f"Pengguna {current_user.username} keluar dari sistem.")
    logout_user()
    flash('Anda telah berhasil keluar dari sistem JESCA.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password-required', methods=['GET', 'POST'])
@login_required
def change_password_page():
    """Forced password change screen on first login."""
    if not getattr(current_user, 'force_password_change', False):
        return redirect(url_for('main.dashboard'))

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
            return redirect(url_for('main.dashboard'))

    return render_template('change_password_required.html')


@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """Self-service password update for logged-in user."""
    old_password = request.form.get('old_password', '').strip()
    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()

    if not current_user.check_password(old_password):
        flash('Password lama yang Anda masukkan tidak sesuai.', 'danger')
        return redirect(request.referrer or url_for('main.dashboard'))

    is_valid, err_msg = validate_password(new_password)
    if not is_valid:
        flash(err_msg, 'danger')
        return redirect(request.referrer or url_for('main.dashboard'))

    if new_password != confirm_password:
        flash('Konfirmasi password baru tidak cocok.', 'danger')
        return redirect(request.referrer or url_for('main.dashboard'))

    current_user.set_password(new_password)
    db.session.commit()
    log_activity('GANTI_PASSWORD', details=f"Pengguna {current_user.username} memperbarui password akunnya.")
    flash('Password Anda berhasil diperbarui!', 'success')
    return redirect(request.referrer or url_for('main.dashboard'))


@auth_bp.route('/profile/update', methods=['POST'])
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
    return redirect(request.referrer or url_for('main.dashboard'))


@auth_bp.route('/confirm-sudo', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def confirm_sudo():
    """Sudo mode step-up verification before accessing /settings."""
    next_url = request.args.get('next') or request.form.get('next') or url_for('admin.system_settings')
    if is_sudo_active():
        return redirect(next_url)

    if request.method == 'POST':
        password = request.form.get('password', '')
        if current_user.check_password(password):
            session['sudo_mode_until'] = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
            log_activity('SUDO_ACCESS', details=f"Mode Akses Khusus (Sudo) diverifikasi oleh {current_user.username} (valid 15 menit).")
            flash('Autentikasi Mode Akses Khusus (Sudo) berhasil! Anda memiliki akses aman selama 15 menit.', 'success')
            return redirect(next_url)
        else:
            log_activity('SUDO_FAILED', details=f"Percobaan sandi Sudo Mode gagal oleh {current_user.username}.")
            flash('Kata sandi administrator salah. Silakan coba kembali.', 'danger')

    return render_template('confirm_sudo.html', next_url=next_url)


@auth_bp.route('/settings/lock-sudo', methods=['POST'])
@login_required
@role_required('Admin')
def lock_sudo():
    """Manually lock sudo mode session immediately."""
    session.pop('sudo_mode_until', None)
    log_activity('SUDO_LOCKED', details=f"Mode Akses Khusus (Sudo) dikunci secara manual oleh {current_user.username}.")
    flash('Sesi Mode Akses Khusus (Sudo) telah dikunci demi keamanan. Sandi akan diminta kembali saat membuka Pengaturan.', 'info')
    return redirect(url_for('main.dashboard'))


