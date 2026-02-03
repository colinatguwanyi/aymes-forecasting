from __future__ import annotations
import enum
import logging

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base

logger = logging.getLogger(__name__)


class PlanningMode(str, enum.Enum):
    WOS_TARGET = "WOS_TARGET"
    ROP = "ROP"


class SafetyStockMethod(str, enum.Enum):
    WEEKS = "WEEKS"
    SERVICE_LEVEL = "SERVICE_LEVEL"


class DemandType(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    SAMPLES = "SAMPLES"
    ADJUSTMENT = "ADJUSTMENT"


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(256), nullable=True)
    description = Column(Text, nullable=True)


class Warehouse(Base):
    __tablename__ = "warehouses"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(256), nullable=True)


class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(256), nullable=True)


class Lane(Base):
    __tablename__ = "lanes"
    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    code = Column(String(64), nullable=True)
    supplier = relationship("Supplier", back_populates="lanes")
    warehouse = relationship("Warehouse", back_populates="lanes")


Supplier.lanes = relationship("Lane", back_populates="supplier")
Warehouse.lanes = relationship("Lane", back_populates="warehouse")


class PlanningPolicy(Base):
    __tablename__ = "planning_policies"
    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(64), nullable=False, index=True)
    warehouse_code = Column(String(32), nullable=False, index=True)
    mode = Column(SQLEnum(PlanningMode), default=PlanningMode.WOS_TARGET)
    target_weeks = Column(Numeric(10, 2), default=4)
    safety_stock_method = Column(SQLEnum(SafetyStockMethod), default=SafetyStockMethod.WEEKS)
    safety_stock_weeks = Column(Numeric(10, 2), default=1)
    service_level = Column(Numeric(5, 4), default=0.95)  # e.g. 0.95 = 95%
    forecast_window_weeks = Column(Integer, default=8)
    lead_time_production_weeks = Column(Numeric(10, 2), default=2)
    lead_time_slot_wait_weeks = Column(Numeric(10, 2), default=0)
    lead_time_haulage_weeks = Column(Numeric(10, 2), default=1)
    lead_time_putaway_weeks = Column(Numeric(10, 2), default=0)
    lead_time_padding_weeks = Column(Numeric(10, 2), default=0)
    include_samples = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("sku", "warehouse_code", name="uq_planning_policy_sku_wh"),)


class InventorySnapshotWeekly(Base):
    __tablename__ = "inventory_snapshots_weekly"
    id = Column(Integer, primary_key=True, index=True)
    week_start = Column(Date, nullable=False, index=True)
    sku = Column(String(64), nullable=False, index=True)
    warehouse_code = Column(String(32), nullable=False, index=True)
    on_hand_qty = Column(Numeric(18, 4), default=0)
    __table_args__ = (UniqueConstraint("week_start", "sku", "warehouse_code", name="uq_inv_week_sku_wh"),)


class Receipt(Base):
    __tablename__ = "receipts"
    id = Column(Integer, primary_key=True, index=True)
    week_start = Column(Date, nullable=False, index=True)
    sku = Column(String(64), nullable=False, index=True)
    warehouse_code = Column(String(32), nullable=False, index=True)
    qty = Column(Numeric(18, 4), nullable=False)
    source_type = Column(String(64), nullable=True)  # e.g. PO, TRANSFER, etc.


class DemandActual(Base):
    __tablename__ = "demand_actuals"
    id = Column(Integer, primary_key=True, index=True)
    week_start = Column(Date, nullable=False, index=True)
    sku = Column(String(64), nullable=False, index=True)
    warehouse_code = Column(String(32), nullable=False, index=True)
    demand_type = Column(SQLEnum(DemandType), nullable=False)
    qty = Column(Numeric(18, 4), nullable=False)


class PlanRun(Base):
    __tablename__ = "plan_runs"
    id = Column(Integer, primary_key=True, index=True)
    scenario_name = Column(String(128), nullable=False, index=True)
    run_at = Column(Date, nullable=False)
    created_at = Column(Date, nullable=False)


class ProjectedInventory(Base):
    __tablename__ = "projected_inventory"
    id = Column(Integer, primary_key=True, index=True)
    plan_run_id = Column(Integer, ForeignKey("plan_runs.id"), nullable=False)
    week_start = Column(Date, nullable=False, index=True)
    sku = Column(String(64), nullable=False, index=True)
    warehouse_code = Column(String(32), nullable=False, index=True)
    start_qty = Column(Numeric(18, 4), nullable=False, default=0)
    receipts_qty = Column(Numeric(18, 4), nullable=False, default=0)
    demand_qty = Column(Numeric(18, 4), nullable=False, default=0)
    projected_qty = Column(Numeric(18, 4), nullable=False)  # end_qty = start + receipts - demand
    weeks_of_cover = Column(Numeric(10, 2), nullable=True)
    stockout = Column(Boolean, default=False)
    plan_run = relationship("PlanRun", back_populates="projected_inventory")


class PlannedOrder(Base):
    __tablename__ = "planned_orders"
    id = Column(Integer, primary_key=True, index=True)
    plan_run_id = Column(Integer, ForeignKey("plan_runs.id"), nullable=False)
    week_start = Column(Date, nullable=False, index=True)
    sku = Column(String(64), nullable=False, index=True)
    warehouse_code = Column(String(32), nullable=False, index=True)
    order_qty = Column(Numeric(18, 4), nullable=False)
    plan_run = relationship("PlanRun", back_populates="planned_orders")


PlanRun.projected_inventory = relationship("ProjectedInventory", back_populates="plan_run")
PlanRun.planned_orders = relationship("PlannedOrder", back_populates="plan_run")
