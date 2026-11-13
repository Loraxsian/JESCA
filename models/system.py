from datetime import datetime
from extensions import db


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
    # v3.0: Security & UX flexibility
    require_login_for_scan = db.Column(db.Boolean, default=False)
    sudo_mode_enabled = db.Column(db.Boolean, default=True)
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


class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True)
    username = db.Column(db.String(80), nullable=False, default='System')
    action = db.Column(db.String(50), nullable=False, index=True)
    asset_code = db.Column(db.String(50), nullable=True)
    asset_name = db.Column(db.String(150), nullable=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

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


class SystemFeedback(db.Model):
    """Stores bug reports, feature suggestions, login issues, and inquiries submitted from login modal or internal users."""
    __tablename__ = 'system_feedbacks'

    id = db.Column(db.Integer, primary_key=True)
    sender_name = db.Column(db.String(100), nullable=True)
    contact = db.Column(db.String(120), nullable=True)
    category = db.Column(db.String(50), default='Saran Fitur Baru', index=True)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Pending', index=True)  # 'Pending', 'In Progress', 'Resolved'
    resolved_by = db.Column(db.String(80), nullable=True)
    resolution_notes = db.Column(db.Text, nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'sender_name': self.sender_name or 'Anonim',
            'contact': self.contact or '-',
            'category': self.category,
            'message': self.message,
            'status': self.status,
            'resolved_by': self.resolved_by or '-',
            'created_at': self.created_at.strftime('%d/%m/%Y %H:%M') if self.created_at else '-'
        }
