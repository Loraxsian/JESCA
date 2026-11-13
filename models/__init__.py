from sqlalchemy import event
from sqlalchemy.engine import Engine

from models.system import SystemSetting, ActivityLog, SystemFeedback
from models.user import User, load_user
from models.asset import (
    Site, Vendor, Asset, AssetAttachment, AssetTransfer,
    MaintenanceRecord, AssetCirculationLog, StockOpnameRecord
)
from models.purchase_order import PurchaseOrder, POItem, PurchaseOrderHistory


@event.listens_for(Engine, 'connect')
def set_sqlite_pragma(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA synchronous=NORMAL')
        cursor.execute('PRAGMA busy_timeout=30000')
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()
    except Exception:
        pass


__all__ = [
    'SystemSetting', 'ActivityLog', 'SystemFeedback',
    'User', 'load_user',
    'Site', 'Vendor', 'Asset', 'AssetAttachment', 'AssetTransfer',
    'MaintenanceRecord', 'AssetCirculationLog', 'StockOpnameRecord',
    'PurchaseOrder', 'POItem', 'PurchaseOrderHistory',
    'set_sqlite_pragma',
]
