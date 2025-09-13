from datetime import datetime
from decimal import Decimal

from flask_login import UserMixin
from sqlalchemy import Numeric, UniqueConstraint, Index
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(64), nullable=False)
    entity = db.Column(db.String(64), nullable=False)
    entity_id = db.Column(db.Integer, nullable=True)
    before = db.Column(db.JSON, nullable=True)
    after = db.Column(db.JSON, nullable=True)
    at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(32), default="viewer")  # admin, ops, buyer, viewer
    is_active = db.Column(db.Boolean, default=True)

    def set_password(self, pwd: str) -> None:
        self.password_hash = generate_password_hash(pwd)

    def check_password(self, pwd: str) -> bool:
        return check_password_hash(self.password_hash, pwd)


class Warehouse(db.Model):
    __tablename__ = "warehouses"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(32), unique=True, nullable=False)


class Location(db.Model):
    __tablename__ = "locations"
    id = db.Column(db.Integer, primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=False)
    code = db.Column(db.String(64), nullable=False)  # e.g., A-01-03
    type = db.Column(db.String(32), default="pick")  # pick, bulk, quarantine

    warehouse = db.relationship("Warehouse", backref=db.backref("locations", lazy=True))
    __table_args__ = (UniqueConstraint("warehouse_id", "code", name="uq_wh_loc_code"),)


class Item(db.Model):
    __tablename__ = "items"
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(100), unique=True, index=True, nullable=False)  # item_number
    name = db.Column(db.String(200), nullable=False)
    price = db.Column(Numeric(12, 4), nullable=False, default=Decimal("0.0000"))

    # kept for backward-compat (no longer edited in UI)
    min_level = db.Column(db.Integer, nullable=False, default=0)
    max_level = db.Column(db.Integer, nullable=False, default=0)
    safety_stock = db.Column(db.Integer, nullable=False, default=0)

    reorder_point = db.Column(db.Integer, nullable=False, default=0)
    on_transit = db.Column(db.Integer, nullable=False, default=0)  # incoming qty (does not affect Available)

    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    last_changed = db.Column(db.DateTime, nullable=True)

    def available_qty(self) -> int:
        on_hand = sum((b.on_hand or 0) for b in self.balances)
        allocated = sum((b.allocated or 0) for b in self.balances)
        return on_hand - allocated

    def on_hand_total(self) -> int:
        return sum((b.on_hand or 0) for b in self.balances)


class InventoryBalance(db.Model):
    __tablename__ = "inventory_balances"
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), nullable=False, index=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False, index=True)
    on_hand = db.Column(db.Integer, nullable=False, default=0)
    allocated = db.Column(db.Integer, nullable=False, default=0)

    item = db.relationship(
        "Item",
        backref=db.backref("balances", lazy="joined", cascade="all, delete-orphan"),
    )
    location = db.relationship("Location", backref=db.backref("balances", lazy=True))

    __table_args__ = (
        UniqueConstraint("item_id", "location_id", name="uq_item_location"),
        Index("ix_item_loc", "item_id", "location_id"),
    )
