import os
import traceback
from datetime import date, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user

from config import APP_VERSION, Config, ensure_directories
from extensions import db, login_manager, HAVE_SCHEDULER, BackgroundScheduler
from i18n import get_current_lang, translate as i18n_translate
from models import Asset, PurchaseOrder, SystemFeedback, SystemSetting, set_sqlite_pragma  # noqa: F401
from routes import register_blueprints
from services.audit_service import get_maintenance_notifications, get_overdue_returns, log_activity
from services.backup_service import auto_backup_job, check_and_update_schema, seed_database
from utils.decorators import is_sudo_active
from utils.filters import register_filters
from utils.helpers import get_client_ip, is_ip_allowed


def create_app(config_class=Config):
    ensure_directories()

    application = Flask(__name__)
    application.config.from_object(config_class)

    db.init_app(application)
    login_manager.init_app(application)

    register_filters(application)
    register_blueprints(application)

    @application.context_processor
    def inject_alerts():
        today_now = date.today()
        if current_user.is_authenticated:
            alerts = get_maintenance_notifications()
            threshold_w = today_now + timedelta(days=30)
            warranty_alerts = Asset.query.filter(
                Asset.warranty_end != None,
                Asset.warranty_end <= threshold_w
            ).order_by(Asset.warranty_end.asc()).all()
            overdue_returns = get_overdue_returns()

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

            feedback_alerts = []
            try:
                if current_user.role in ['Admin', 'Administrator']:
                    feedback_alerts = SystemFeedback.query.filter_by(status='Pending')\
                        .order_by(SystemFeedback.created_at.desc()).all()
                elif current_user.role == 'Teknisi':
                    feedback_alerts = SystemFeedback.query.filter(
                        SystemFeedback.status == 'Pending',
                        SystemFeedback.category.in_([
                            'Laporan Bug / Eror', 'Kendala Login / Akun',
                            'Laporan Kendala Aset', 'Pertanyaan Inventaris'
                        ])
                    ).order_by(SystemFeedback.created_at.desc()).all()
            except Exception:
                pass

            return {
                'today': today_now,
                'date_today': today_now,
                'maintenance_alerts': alerts,
                'warranty_alerts': warranty_alerts,
                'overdue_returns': overdue_returns,
                'pending_po_alerts': pending_po_alerts,
                'user_po_alerts': user_po_alerts,
                'feedback_alerts': feedback_alerts,
                'is_sudo_active': is_sudo_active(),
                'csrf_token': lambda: '',
                't': i18n_translate,
                'current_lang': get_current_lang()
            }

        return {
            'today': today_now,
            'date_today': today_now,
            'maintenance_alerts': [],
            'warranty_alerts': [],
            'overdue_returns': [],
            'pending_po_alerts': [],
            'user_po_alerts': [],
            't': i18n_translate,
            'current_lang': get_current_lang(),
            'feedback_alerts': [],
            'is_sudo_active': False,
            'csrf_token': lambda: ''
        }

    @application.before_request
    def enforce_network_and_security():
        try:
            setting = SystemSetting.query.get(1)
        except Exception:
            setting = None

        if setting and setting.enforce_https:
            host_name = request.host.split(':')[0].lower()
            client_ip = get_client_ip()
            is_loopback = (host_name in ('localhost', '127.0.0.1', '::1') or client_ip in ('127.0.0.1', '::1'))
            is_recovery_endpoint = (request.endpoint in ('admin.system_settings', 'auth.confirm_sudo', 'auth.lock_sudo'))
            if not is_loopback and not is_recovery_endpoint:
                if request.headers.get('X-Forwarded-Proto', request.scheme) == 'http':
                    https_url = request.url.replace('http://', 'https://', 1)
                    return redirect(https_url, code=301)

        if setting and setting.ip_whitelist_enabled and setting.allowed_ip_ranges:
            exempt_endpoints = {'static', 'main.health', 'main.scan_asset_summary', 'main.robots'}
            if request.endpoint and request.endpoint not in exempt_endpoints:
                client_ip = get_client_ip()
                if client_ip not in ['127.0.0.1', '::1']:
                    if not is_ip_allowed(client_ip, setting.allowed_ip_ranges):
                        return render_template('403_network.html', client_ip=client_ip), 403

    @application.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response

    @application.before_request
    def check_force_password_change():
        exempt_endpoints = {
            'auth.login', 'auth.logout', 'auth.change_password_page', 'static',
            'main.scan_asset_summary', 'main.health', 'api.api_asset_qrcode',
            'auth.confirm_sudo', 'auth.lock_sudo', 'main.robots'
        }
        if current_user.is_authenticated and getattr(current_user, 'force_password_change', False):
            if request.endpoint and request.endpoint not in exempt_endpoints:
                return redirect(url_for('auth.change_password_page'))

    @application.errorhandler(404)
    def handle_404_error(e):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({
                'status': 'error',
                'code': 404,
                'message': 'Halaman atau endpoint yang Anda tuju tidak ditemukan.'
            }), 404
        return render_template('404.html', path=request.path), 404

    @application.errorhandler(500)
    def handle_500_error(e):
        db.session.rollback()
        original_err = getattr(e, 'original_exception', e)
        tb_str = traceback.format_exc()
        application.logger.error(f"[SYSTEM_ERROR 500] URL: {request.path} [{request.method}] - Error: {original_err}\n{tb_str}")

        try:
            user_name = current_user.username if current_user and current_user.is_authenticated else 'Guest/System'
            err_msg = str(original_err)[:250]
            log_activity(
                'SYSTEM_ERROR',
                details=f"500 Error pada {request.path} ({request.method}) oleh {user_name}: {err_msg}"
            )
        except Exception:
            db.session.rollback()

        if request.is_json or request.path.startswith('/api/'):
            return jsonify({
                'status': 'error',
                'code': 500,
                'message': 'Terjadi kendala pada server. Sistem telah memulihkan transaksi (rollback) dan mencatat insiden ini.'
            }), 500

        return render_template('500.html', error=original_err, path=request.path), 500

    @application.errorhandler(413)
    def handle_413_error(e):
        flash('Ukuran berkas melebihi batas maksimum 5MB. Silakan gunakan berkas yang lebih kecil.', 'danger')
        return redirect(request.referrer or url_for('main.dashboard'))

    with application.app_context():
        try:
            if application.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
                with db.engine.connect() as conn:
                    conn.execute(db.text("PRAGMA journal_mode=WAL;"))
                    conn.execute(db.text("PRAGMA synchronous=NORMAL;"))
                    conn.execute(db.text("PRAGMA busy_timeout=30000;"))
                    conn.execute(db.text("PRAGMA foreign_keys=ON;"))
        except Exception as e:
            application.logger.warning(f"Could not apply startup SQLite PRAGMAs: {e}")
        db.create_all()
        check_and_update_schema()
        seed_database()

    if HAVE_SCHEDULER and (not application.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true'):
        try:
            scheduler = BackgroundScheduler()
            scheduler.add_job(func=lambda: auto_backup_job(application), trigger='cron', hour=2, minute=0)
            scheduler.start()
        except Exception as e:
            application.logger.warning(f"Could not start backup scheduler: {e}")

    return application


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
