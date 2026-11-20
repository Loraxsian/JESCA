import os
import shutil
import time
from datetime import datetime, timedelta
from flask import current_app
from extensions import db
from config import BACKUP_FOLDER, db_path
from models.user import User
from models.asset import Site
from models.system import SystemSetting
from services.audit_service import log_activity


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
                ('po_item_id', 'INTEGER'),
                ('depreciation_method', "VARCHAR(30) DEFAULT 'straight_line'")
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
                ('remote_backup_path', "VARCHAR(255) DEFAULT '/'"),
                ('require_login_for_scan', 'BOOLEAN DEFAULT 0'),
                ('sudo_mode_enabled', 'BOOLEAN DEFAULT 1')
            ]
            for col_name, col_type in ss_additions:
                if col_name not in cols_ss:
                    conn.execute(db.text(f"ALTER TABLE system_settings ADD COLUMN {col_name} {col_type}"))

            # Create performance indexes if not exist
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);",
                "CREATE INDEX IF NOT EXISTS idx_assets_needs_maint ON assets(needs_maintenance);",
                "CREATE INDEX IF NOT EXISTS idx_assets_next_maint ON assets(next_maintenance_date);",
                "CREATE INDEX IF NOT EXISTS idx_assets_vendor_id ON assets(vendor_id);",
                "CREATE INDEX IF NOT EXISTS idx_assets_site_id ON assets(site_id);",
                "CREATE INDEX IF NOT EXISTS idx_assets_created_at ON assets(created_at);",
                "CREATE INDEX IF NOT EXISTS idx_po_status ON purchase_orders(status);",
                "CREATE INDEX IF NOT EXISTS idx_po_requested_by ON purchase_orders(requested_by);",
                "CREATE INDEX IF NOT EXISTS idx_po_created_at ON purchase_orders(created_at);",
                "CREATE INDEX IF NOT EXISTS idx_maint_asset_id ON maintenance_records(asset_id);",
                "CREATE INDEX IF NOT EXISTS idx_maint_service_date ON maintenance_records(service_date);",
                "CREATE INDEX IF NOT EXISTS idx_circ_asset_id ON asset_circulation_logs(asset_id);",
                "CREATE INDEX IF NOT EXISTS idx_activity_created_at ON activity_logs(created_at);",
                "CREATE INDEX IF NOT EXISTS idx_activity_action ON activity_logs(action);",
                "CREATE INDEX IF NOT EXISTS idx_feedback_status ON system_feedbacks(status);",
                "CREATE INDEX IF NOT EXISTS idx_feedback_category ON system_feedbacks(category);",
                "CREATE INDEX IF NOT EXISTS idx_opname_code ON stock_opname_records(asset_code);",
                "CREATE INDEX IF NOT EXISTS idx_opname_synced ON stock_opname_records(synced_at);"
            ]
            for idx_sql in indexes:
                try:
                    conn.execute(db.text(idx_sql))
                except Exception:
                    pass

            conn.commit()

        # Create any newly defined tables
        db.create_all()
    except Exception as e:
        current_app.logger.warning(f"Schema update notice: {e}")


def backup_sqlite_db(src_path, dst_path):
    """
    Perform a consistent and atomic SQLite backup using SQLite's native backup API.
    Truncates WAL before and during backup to ensure all transactions are captured.
    """
    import sqlite3
    if not os.path.exists(src_path):
        raise FileNotFoundError(f"Source database not found: {src_path}")

    # Flush WAL into main database file
    try:
        chk_conn = sqlite3.connect(src_path, timeout=30)
        chk_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        chk_conn.close()
    except Exception as e:
        try:
            current_app.logger.warning(f"WAL checkpoint before backup warning: {e}")
        except Exception:
            pass

    # Use native SQLite backup API
    src_conn = sqlite3.connect(src_path, timeout=30)
    dst_conn = sqlite3.connect(dst_path, timeout=30)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()


def auto_backup_job(app=None):
    """Daily auto backup, keep last 30 days. Uses a POSIX file lock so only 1 Gunicorn worker executes."""
    def _run():
        lock_file = None
        try:
            try:
                import fcntl
                lock_file = open('/tmp/jesca_auto_backup.lock', 'w')
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                # Another Gunicorn worker already holds the lock for this scheduled run
                return
            except ImportError:
                # Non-POSIX fallback (e.g. Windows dev)
                pass

            filename = f"auto_{datetime.now().strftime('%Y%m%d')}.db"
            dst = os.path.join(BACKUP_FOLDER, filename)
            if not os.path.exists(dst) and os.path.exists(db_path):
                backup_sqlite_db(db_path, dst)
            for f in os.listdir(BACKUP_FOLDER):
                fp = os.path.join(BACKUP_FOLDER, f)
                if f.endswith('.db') and (datetime.now() - datetime.fromtimestamp(os.path.getctime(fp))).days > 30:
                    os.remove(fp)
        except Exception as e:
            try:
                current_app.logger.error(f'Auto backup failed: {e}')
            except Exception:
                pass
        finally:
            if lock_file is not None:
                try:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
                try:
                    lock_file.close()
                except Exception:
                    pass

    if app is not None:
        with app.app_context():
            _run()
    else:
        _run()
