from datetime import datetime, date, timedelta
from flask import current_app
from flask_login import current_user
from extensions import db
from models.asset import Asset
from models.system import ActivityLog
from models.purchase_order import PurchaseOrderHistory


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
        current_app.logger.error(f"Error saving activity log: {e}")


def get_maintenance_notifications():
    """Finds all assets that have maintenance scheduled within 7 days or are overdue."""
    today = date.today()
    threshold = today + timedelta(days=7)

    due_assets = Asset.query.filter(
        Asset.needs_maintenance == True,
        Asset.next_maintenance_date != None,
        Asset.next_maintenance_date <= threshold,
        Asset.status.notin_(['Dalam Perbaikan', 'Afkir'])
    ).order_by(Asset.next_maintenance_date.asc()).all()

    notifications = []
    for a in due_assets:
        # If the asset was serviced today and next maintenance is in the future, it is clear for this cycle
        if a.last_maintenance_date and a.last_maintenance_date >= today and a.next_maintenance_date > today:
            continue

        days_left = (a.next_maintenance_date - today).days

        # Dynamic notice window: For shorter intervals (e.g. <= 7 days), don't alert prematurely
        max_notice_days = min(7, max(1, (a.maintenance_interval_days or 90) // 2))
        if days_left > max_notice_days:
            continue

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


def log_po_history(po, action, notes=None, attachment=None):
    """Record an audit trail event in the PO history table."""
    try:
        hist = PurchaseOrderHistory(
            po_id=po.id,
            action=action,
            to_status=po.status,
            notes=notes,
            attachment=attachment,
            performed_by=current_user.username if (current_user and current_user.is_authenticated) else 'System'
        )
        db.session.add(hist)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error logging PO history: {e}")

