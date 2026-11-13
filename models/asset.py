import json
from datetime import datetime, date
from extensions import db


class Site(db.Model):
    """Physical location / branch that holds assets."""
    __tablename__ = 'sites'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description or '',
            'is_active': self.is_active,
            'asset_count': Asset.query.filter_by(site_id=self.id).count() if 'Asset' in globals() else 0
        }


class Vendor(db.Model):
    """Supplier / vendor for asset procurement."""
    __tablename__ = 'vendors'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    contact_person = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'contact_person': self.contact_person or '',
            'phone': self.phone or '',
            'email': self.email or '',
            'address': self.address or '',
            'notes': self.notes or '',
            'is_active': self.is_active,
            'asset_count': Asset.query.filter_by(vendor_id=self.id).count() if 'Asset' in globals() else 0
        }


class Asset(db.Model):
    __tablename__ = 'assets'

    id = db.Column(db.Integer, primary_key=True)
    asset_code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=False, index=True)
    purchase_date = db.Column(db.Date, nullable=False, default=date.today)
    purchase_price = db.Column(db.Float, default=0.0)
    location = db.Column(db.String(100), default='Kantor Pusat')
    status = db.Column(db.String(50), default='Aktif', index=True)  # Aktif, Dipinjam, Dalam Perbaikan, Rusak, Afkir
    description = db.Column(db.Text, nullable=True)
    image = db.Column(db.String(255), nullable=True)  # filename in static/uploads
    borrower = db.Column(db.String(100), nullable=True)  # Current borrower name
    borrow_date = db.Column(db.DateTime, nullable=True)  # Date when borrowed

    # Maintenance Scheduling
    needs_maintenance = db.Column(db.Boolean, default=False, index=True)
    maintenance_interval_days = db.Column(db.Integer, nullable=True)  # e.g., 30, 90, 180, 365
    next_maintenance_date = db.Column(db.Date, nullable=True, index=True)
    last_maintenance_date = db.Column(db.Date, nullable=True)

    # v2: Warranty
    warranty_start = db.Column(db.Date, nullable=True)
    warranty_end = db.Column(db.Date, nullable=True)

    # v2: Depreciation (straight-line)
    useful_life_years = db.Column(db.Integer, nullable=True)
    salvage_value = db.Column(db.Float, default=0.0)

    # v2: Utilization tracking
    total_checkout_days = db.Column(db.Integer, default=0)

    # v2: Custom fields (JSON string)
    custom_fields_json = db.Column(db.Text, nullable=True)

    # v2: Relations
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendors.id'), nullable=True, index=True)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=True, index=True)
    po_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=True)
    po_item_id = db.Column(db.Integer, db.ForeignKey('po_items.id'), nullable=True)

    # Relationships to models
    vendor = db.relationship('Vendor', backref='assets', lazy=True)
    site = db.relationship('Site', backref='assets', lazy=True)
    purchase_order = db.relationship('PurchaseOrder', backref='assets', foreign_keys=[po_id], lazy=True)
    po_item = db.relationship('POItem', backref='assets', foreign_keys=[po_item_id], lazy=True)

    # v2: Transfer tracking
    last_transfer_date = db.Column(db.Date, nullable=True)
    last_transfer_from = db.Column(db.String(100), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    attachments = db.relationship('AssetAttachment', backref='asset', lazy=True, cascade='all, delete-orphan')
    transfers = db.relationship('AssetTransfer', backref='asset', lazy=True, cascade='all, delete-orphan')

    @property
    def custom_fields(self):
        """Return parsed custom fields dict."""
        if self.custom_fields_json:
            try:
                return json.loads(self.custom_fields_json)
            except Exception:
                return {}
        return {}

    @property
    def current_book_value(self):
        """Straight-line depreciation: (cost - salvage) / useful_life_years."""
        if not self.useful_life_years or self.useful_life_years <= 0:
            return self.purchase_price or 0.0
        if not self.purchase_date:
            return self.purchase_price or 0.0
        
        # Jika tanggal perolehan hari ini atau di masa depan, belum ada penyusutan
        if self.purchase_date >= date.today():
            return self.purchase_price or 0.0

        years_elapsed = (date.today() - self.purchase_date).days / 365.25
        salvage = self.salvage_value or 0.0
        cost = self.purchase_price or 0.0
        annual_dep = (cost - salvage) / self.useful_life_years
        book_value = cost - (annual_dep * years_elapsed)
        
        # Nilai buku tidak boleh lebih besar dari harga beli dan tidak boleh lebih kecil dari nilai residu
        return round(min(cost, max(book_value, salvage)), 2)

    @property
    def warranty_status(self):
        """Returns warranty status dict or None."""
        if not self.warranty_end:
            return None
        today = date.today()
        days_left = (self.warranty_end - today).days
        if days_left < 0:
            return {'status': 'expired', 'days': days_left, 'label': f'Expired {-days_left} hari lalu', 'color': 'danger'}
        elif days_left <= 30:
            return {'status': 'expiring', 'days': days_left, 'label': f'Berakhir {days_left} hari lagi', 'color': 'warning'}
        else:
            return {'status': 'active', 'days': days_left, 'label': f'Aktif ({days_left} hari)', 'color': 'success'}

    def to_dict(self):
        today = date.today()
        days_to_maint = None
        is_overdue = False
        if self.needs_maintenance and self.next_maintenance_date:
            days_to_maint = (self.next_maintenance_date - today).days
            is_overdue = days_to_maint < 0

        return {
            'id': self.id,
            'asset_code': self.asset_code,
            'name': self.name,
            'category': self.category,
            'purchase_date': self.purchase_date.strftime('%Y-%m-%d') if self.purchase_date else '',
            'purchase_price': self.purchase_price,
            'location': self.location,
            'status': self.status,
            'description': self.description or '',
            'image': self.image or '',
            'image_url': f"/static/uploads/{self.image}" if self.image else None,
            'borrower': self.borrower or '',
            'borrow_date': self.borrow_date.strftime('%Y-%m-%d %H:%M') if self.borrow_date else '',
            'needs_maintenance': bool(self.needs_maintenance),
            'maintenance_interval_days': self.maintenance_interval_days,
            'next_maintenance_date': self.next_maintenance_date.strftime('%Y-%m-%d') if self.next_maintenance_date else '',
            'last_maintenance_date': self.last_maintenance_date.strftime('%Y-%m-%d') if self.last_maintenance_date else '',
            'days_to_maintenance': days_to_maint,
            'is_overdue': is_overdue,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            # v2 fields
            'warranty_start': self.warranty_start.strftime('%Y-%m-%d') if self.warranty_start else '',
            'warranty_end': self.warranty_end.strftime('%Y-%m-%d') if self.warranty_end else '',
            'warranty_status': self.warranty_status,
            'useful_life_years': self.useful_life_years,
            'salvage_value': self.salvage_value or 0.0,
            'current_book_value': self.current_book_value,
            'total_checkout_days': self.total_checkout_days or 0,
            'custom_fields': self.custom_fields,
            'vendor_id': self.vendor_id,
            'vendor_name': self.vendor.name if self.vendor else '',
            'site_id': self.site_id,
            'site_name': self.site.name if self.site else '',
            'last_transfer_date': self.last_transfer_date.strftime('%Y-%m-%d') if self.last_transfer_date else '',
            'last_transfer_from': self.last_transfer_from or '',
            'po_id': self.po_id,
            'po_number': self.purchase_order.po_number if self.purchase_order else ''
        }


class AssetAttachment(db.Model):
    """File attachments linked to an asset (invoice, manual, certificate, etc.)."""
    __tablename__ = 'asset_attachments'

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)        # stored filename
    original_name = db.Column(db.String(255), nullable=False)  # original upload name
    file_type = db.Column(db.String(50), default='other')       # manual/invoice/certificate/other
    file_size = db.Column(db.Integer, nullable=True)            # bytes
    uploaded_by = db.Column(db.String(80), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


class AssetTransfer(db.Model):
    """Record of permanent asset location/site transfers."""
    __tablename__ = 'asset_transfers'

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    from_location = db.Column(db.String(100), nullable=False)
    to_location = db.Column(db.String(100), nullable=False)
    from_site = db.Column(db.String(100), nullable=True)
    to_site = db.Column(db.String(100), nullable=True)
    reason = db.Column(db.Text, nullable=True)
    transferred_by = db.Column(db.String(80), nullable=False)
    transfer_date = db.Column(db.DateTime, default=datetime.utcnow)


class MaintenanceRecord(db.Model):
    """Detailed log of each physical maintenance / servicing event performed on an asset."""
    __tablename__ = 'maintenance_records'

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False, index=True)
    service_type = db.Column(db.String(100), default='Rutin')
    action_taken = db.Column(db.Text, nullable=False)
    cost = db.Column(db.Float, default=0.0)
    proof_file = db.Column(db.String(255), nullable=True)
    performed_by = db.Column(db.String(80), nullable=False)
    service_date = db.Column(db.Date, default=date.today, index=True)
    next_service_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    asset = db.relationship('Asset', backref=db.backref('maintenance_records', lazy=True, order_by='MaintenanceRecord.service_date.desc()', cascade='all, delete-orphan'))


class AssetCirculationLog(db.Model):
    """Permanent log of all asset check-outs and check-ins (historical record)."""
    __tablename__ = 'asset_circulation_logs'

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False, index=True)
    borrower = db.Column(db.String(100), nullable=False)
    borrow_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    return_date = db.Column(db.DateTime, nullable=True)
    duration_days = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text, nullable=True)
    checkout_by = db.Column(db.String(80), nullable=False)
    checkin_by = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    asset = db.relationship('Asset', backref=db.backref('circulation_logs', lazy=True, order_by='AssetCirculationLog.borrow_date.desc()', cascade='all, delete-orphan'))


class StockOpnameRecord(db.Model):
    """Log of physical asset verification (stock opname) performed online or synced from offline cache."""
    __tablename__ = 'stock_opname_records'

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=True, index=True)
    asset_code = db.Column(db.String(50), nullable=False, index=True)
    asset_name = db.Column(db.String(150), nullable=True)
    physical_condition = db.Column(db.String(50), default='Sesuai & Baik')  # 'Sesuai & Baik', 'Rusak Ringan', 'Lokasi Berpindah', 'Hilang/Tidak Ditemukan'
    location_checked = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    verified_by = db.Column(db.String(80), nullable=False)
    is_offline_sync = db.Column(db.Boolean, default=False)
    scanned_at = db.Column(db.DateTime, default=datetime.utcnow)
    synced_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    asset = db.relationship('Asset', backref=db.backref('opname_records', lazy=True, order_by='StockOpnameRecord.scanned_at.desc()'))

    def to_dict(self):
        return {
            'id': self.id,
            'asset_code': self.asset_code,
            'asset_name': self.asset_name or '',
            'physical_condition': self.physical_condition,
            'location_checked': self.location_checked or '',
            'notes': self.notes or '',
            'verified_by': self.verified_by,
            'is_offline_sync': self.is_offline_sync,
            'scanned_at': self.scanned_at.strftime('%d/%m/%Y %H:%M') if self.scanned_at else '-',
            'synced_at': self.synced_at.strftime('%d/%m/%Y %H:%M') if self.synced_at else '-'
        }


