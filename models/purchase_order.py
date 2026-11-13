from datetime import datetime
from extensions import db


class PurchaseOrder(db.Model):
    """Purchase Order model for procurement and digital approval workflow."""
    __tablename__ = 'purchase_orders'

    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default='DRAFT', index=True)  # DRAFT, SUBMITTED, APPROVED, REJECTED, ORDERED, RECEIVED, CLOSED, CANCELLED
    requested_by = db.Column(db.String(80), nullable=False)
    approved_by = db.Column(db.String(80), nullable=True)
    rejection_reason = db.Column(db.Text, nullable=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendors.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    estimated_total = db.Column(db.Float, default=0.0)

    # Attachments & Proofs
    order_proof = db.Column(db.String(255), nullable=True)
    order_notes = db.Column(db.Text, nullable=True)
    receipt_proof = db.Column(db.String(255), nullable=True)
    receipt_notes = db.Column(db.Text, nullable=True)
    is_self_approved = db.Column(db.Boolean, default=False)

    submitted_at = db.Column(db.DateTime, nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    ordered_at = db.Column(db.DateTime, nullable=True)
    received_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    vendor = db.relationship('Vendor', backref='purchase_orders', lazy=True)
    items = db.relationship('POItem', backref='purchase_order', lazy=True, cascade='all, delete-orphan')

    @property
    def total_calculated(self):
        return sum(item.total_price for item in self.items)

    @property
    def total_items_quantity(self):
        return sum(item.quantity or 0 for item in self.items)

    @property
    def total_converted_assets(self):
        return sum(item.converted_count or 0 for item in self.items)

    @property
    def is_all_converted(self):
        if not self.items:
            return False
        return all(item.converted_count >= item.quantity for item in self.items)

    def to_dict(self):
        return {
            'id': self.id,
            'po_number': self.po_number,
            'title': self.title,
            'status': self.status,
            'requested_by': self.requested_by,
            'approved_by': self.approved_by or '',
            'rejection_reason': self.rejection_reason or '',
            'vendor_id': self.vendor_id,
            'vendor_name': self.vendor.name if self.vendor else '',
            'notes': self.notes or '',
            'estimated_total': self.estimated_total or 0.0,
            'total_calculated': self.total_calculated,
            'total_items_quantity': self.total_items_quantity,
            'total_converted_assets': self.total_converted_assets,
            'is_all_converted': self.is_all_converted,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
            'submitted_at': self.submitted_at.strftime('%Y-%m-%d %H:%M') if self.submitted_at else '',
            'approved_at': self.approved_at.strftime('%Y-%m-%d %H:%M') if self.approved_at else '',
            'ordered_at': self.ordered_at.strftime('%Y-%m-%d %H:%M') if self.ordered_at else '',
            'received_at': self.received_at.strftime('%Y-%m-%d %H:%M') if self.received_at else '',
            'closed_at': self.closed_at.strftime('%Y-%m-%d %H:%M') if self.closed_at else ''
        }


class POItem(db.Model):
    """Individual line items requested in a Purchase Order."""
    __tablename__ = 'po_items'

    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    item_name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), default='Tech')
    quantity = db.Column(db.Integer, default=1)
    quantity_received = db.Column(db.Integer, default=0)
    unit_price = db.Column(db.Float, default=0.0)
    specification = db.Column(db.Text, nullable=True)
    converted_count = db.Column(db.Integer, default=0)  # how many assets converted from this item
    is_converted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def total_price(self):
        return (self.quantity or 0) * (self.unit_price or 0.0)

    @property
    def remaining_to_convert(self):
        return max(0, (self.quantity or 0) - (self.converted_count or 0))

    def to_dict(self):
        return {
            'id': self.id,
            'po_id': self.po_id,
            'item_name': self.item_name,
            'category': self.category,
            'quantity': self.quantity,
            'quantity_received': self.quantity_received,
            'unit_price': self.unit_price,
            'total_price': self.total_price,
            'specification': self.specification or '',
            'converted_count': self.converted_count or 0,
            'remaining_to_convert': self.remaining_to_convert,
            'is_converted': self.is_converted
        }


class PurchaseOrderHistory(db.Model):
    """Immutable audit trail for every Purchase Order status change."""
    __tablename__ = 'po_histories'

    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    to_status = db.Column(db.String(30), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    attachment = db.Column(db.String(255), nullable=True)
    performed_by = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    po = db.relationship('PurchaseOrder', backref=db.backref('history_entries', lazy=True, order_by='PurchaseOrderHistory.created_at.desc()', cascade='all, delete-orphan'))


