import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app
from models.system import SystemSetting
from utils.helpers import format_wib_datetime, decrypt_smtp_password


def build_system_email_html(header_title: str, badge_text: str, badge_type: str, intro_html: str, rows: list, note_text: str = None) -> str:
    """
    Standardized corporate transactional email template for JESCA.
    badge_type: 'success' (green), 'danger' (red), 'primary' (blue), 'warning' (amber)
    rows: list of (label, value_html)
    """
    badge_styles = {
        'success': {'accent': '#16a34a', 'bg': '#dcfce7', 'fg': '#15803d', 'border': '#bbf7d0'},
        'danger': {'accent': '#dc2626', 'bg': '#fee2e2', 'fg': '#b91c1c', 'border': '#fecaca'},
        'primary': {'accent': '#2563eb', 'bg': '#dbeafe', 'fg': '#1d4ed8', 'border': '#bfdbfe'},
        'warning': {'accent': '#d97706', 'bg': '#fef3c7', 'fg': '#b45309', 'border': '#fde68a'},
    }
    style = badge_styles.get(badge_type, badge_styles['primary'])

    table_rows_html = []
    for i, (label, val) in enumerate(rows):
        bg = "#f8fafc" if i % 2 == 0 else "#ffffff"
        table_rows_html.append(f"""
            <tr style="background-color: {bg}; border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 11px 16px; color: #64748b; font-size: 13px; font-weight: 600; width: 34%; vertical-align: middle;">{label}</td>
                <td style="padding: 11px 16px; color: #0f172a; font-size: 13px; vertical-align: middle;">{val}</td>
            </tr>
        """)
    table_content = "".join(table_rows_html)

    note_html = ""
    if note_text:
        note_html = f"""
        <div style="margin-top: 18px; padding: 12px 16px; background-color: #f8fafc; border-left: 4px solid {style['accent']}; border-radius: 4px; font-size: 12.5px; color: #475569; line-height: 1.5;">
            {note_text}
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin: 0; padding: 24px 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
    <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06);">
        <!-- Top Accent Bar -->
        <div style="height: 4px; background-color: {style['accent']};"></div>

        <!-- Header -->
        <div style="background-color: #0f172a; padding: 20px 24px;">
            <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">
                <tr>
                    <td style="vertical-align: middle;">
                        <div style="font-size: 18px; font-weight: 800; letter-spacing: 0.5px; color: #ffffff; margin-bottom: 2px;">JESCA</div>
                        <div style="font-size: 11px; color: #94a3b8; font-weight: 500;">Jessica Assets Management System</div>
                    </td>
                    <td style="text-align: right; vertical-align: middle;">
                        <span style="display: inline-block; padding: 4px 10px; background-color: {style['bg']}; color: {style['fg']}; border: 1px solid {style['border']}; border-radius: 20px; font-size: 11px; font-weight: 700; letter-spacing: 0.3px; text-transform: uppercase;">
                            {badge_text}
                        </span>
                    </td>
                </tr>
            </table>
        </div>

        <!-- Body Content -->
        <div style="padding: 24px;">
            <h2 style="margin: 0 0 12px 0; font-size: 16px; font-weight: 700; color: #0f172a;">{header_title}</h2>
            <div style="font-size: 13.5px; color: #334155; line-height: 1.6; margin-bottom: 16px;">
                {intro_html}
            </div>

            <!-- Parameter Table -->
            <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
                <tbody>
                    {table_content}
                </tbody>
            </table>

            {note_html}
        </div>

        <!-- Corporate Footer -->
        <div style="padding: 16px 24px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; text-align: center;">
            <p style="margin: 0 0 6px 0; font-size: 11px; color: #64748b; line-height: 1.5;">
                Pesan ini dihasilkan secara otomatis oleh sistem notifikasi JESCA. Mohon untuk tidak membalas email ini secara langsung.
            </p>
            <div style="font-size: 11px; color: #94a3b8; font-weight: 500;">
                &copy; 2026 JESCA &bull; Jessica Assets Management System
            </div>
        </div>
    </div>
</body>
</html>"""


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
                    current_app.logger.warning("Email dispatch skipped: server or username not configured.")
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
                        current_app.logger.error(f"SMTP Auth failed: {auth_err}")
                        return

                server.sendmail(sender_addr, targets, msg.as_string())
                server.quit()
                current_app.logger.info(f"Email successfully sent to {targets}: {subj}")
            except Exception as e:
                current_app.logger.error(f"Failed to dispatch email: {e}")

    # Launch asynchronously
    t = threading.Thread(
        target=_worker,
        args=(current_app._get_current_object().app_context(), subject, html_body, recipient_list),
        daemon=True
    )
    t.start()

