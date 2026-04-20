from __future__ import annotations
import enum
import logging
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
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


# --- Ingestion backbone enums ---
class IngestionSourceType(str, enum.Enum):
    CSV = "CSV"
    DB_SYNC = "DB sync"
    MANUAL = "manual"


class IngestionEntity(str, enum.Enum):
    DEMAND = "demand"
    RECEIPTS = "receipts"
    INVENTORY = "inventory"
    SKU_MAP = "sku_map"
    PRODUCT_MASTER = "product_master"
    FORECAST_OUTPUT = "forecast_output"
    SALES_OUT = "sales_out"
    STOCK_ON_HAND = "stock_on_hand"


class IngestionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    DUPLICATE_NOOP = "duplicate_noop"


class IngestionMode(str, enum.Enum):
    WEEKLY = "weekly"
    HISTORICAL = "historical"


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(256), nullable=True)
    description = Column(Text, nullable=True)
    uom = Column(String(32), nullable=False, server_default="units")
    active = Column(Boolean, nullable=False, server_default=text("1"))
    aah_code = Column(Text, nullable=True)
    brand = Column(Text, nullable=True)
    product_family = Column(Text, nullable=True)
    selling_unit_text = Column(Text, nullable=True)
    single_unit_content = Column(Numeric(18, 4), nullable=True)
    content_uom = Column(String(16), nullable=True)
    is_recipe = Column(Boolean, nullable=False, server_default=text("0"))


class Warehouse(Base):
    __tablename__ = "warehouses"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(256), nullable=True)
    timezone = Column(String(64), nullable=False, server_default="Europe/London")
    active = Column(Boolean, nullable=False, server_default=text("1"))


class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(256), nullable=True)
    active = Column(Boolean, nullable=False, server_default=text("1"))


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
    source_type = Column(String(32), nullable=False, server_default="legacy")
    source_run_id = Column(Uuid(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="SET NULL"), nullable=True)
    __table_args__ = (UniqueConstraint("week_start", "sku", "warehouse_code", "source_type", name="uq_inv_week_sku_wh_source"),)


class Receipt(Base):
    """Upsert key: (week_start, sku, warehouse_code, source_type). Unique index in migration 002."""
    __tablename__ = "receipts"
    id = Column(Integer, primary_key=True, index=True)
    week_start = Column(Date, nullable=False, index=True)
    sku = Column(String(64), nullable=False, index=True)
    warehouse_code = Column(String(32), nullable=False, index=True)
    qty = Column(Numeric(18, 4), nullable=False)
    source_type = Column(String(64), nullable=True)  # e.g. PO, TRANSFER, etc.


class DemandActual(Base):
    """Upsert key: (week_start, sku, warehouse_code, demand_type). Unique in migration 002."""
    __tablename__ = "demand_actuals"
    __table_args__ = (
        UniqueConstraint(
            "week_start", "sku", "warehouse_code", "demand_type",
            name="uq_demand_actuals_week_sku_wh_type",
        ),
    )
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
    demand_source = Column(String(32), nullable=False, server_default="actuals")
    freeze_weeks = Column(Integer, nullable=False, server_default="4")
    plan_start_week_start = Column(Date, nullable=False)  # W-TUE anchor for freeze window
    created_by = Column(String(256), nullable=True)
    notes = Column(Text, nullable=True)
    baseline_train_end_week_start = Column(Date, nullable=True)
    selected_train_end_week_start = Column(Date, nullable=True)
    warehouses_scope = Column(JSON, nullable=True)  # e.g. ["AAH"], ["BLP"], ["AAH","BLP"]; NULL = legacy all
    progress_meta = Column(JSON, nullable=True)  # warehouses_planned, warehouses_skipped, row counts, etc.


class PlanRunDemandInputWeekly(Base):
    """Materialized demand used by a plan run; single truth per run."""
    __tablename__ = "plan_run_demand_inputs_weekly"
    __table_args__ = (
        UniqueConstraint(
            "plan_run_id", "week_start", "sku", "warehouse_code",
            name="uq_plan_run_demand_inputs_run_week_sku_wh",
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    plan_run_id = Column(Integer, ForeignKey("plan_runs.id", ondelete="CASCADE"), nullable=False)
    week_start = Column(Date, nullable=False, index=True)
    sku = Column(String(64), nullable=False, index=True)
    warehouse_code = Column(String(32), nullable=False, index=True)
    demand_qty = Column(Numeric(18, 4), nullable=False)
    source = Column(String(32), nullable=False)
    source_ref = Column(JSON, nullable=True)
    demand_breakdown_json = Column(JSON, nullable=True)  # per demand_type + included/excluded, or OVERRIDE/FORECAST_TOTAL
    demand_includes_samples = Column(Boolean, nullable=False, server_default=text("1"))
    is_frozen = Column(Boolean, nullable=False, server_default=text("0"))


class DemandOverrideWeekly(Base):
    __tablename__ = "demand_overrides_weekly"
    __table_args__ = (
        UniqueConstraint(
            "plan_run_id", "week_start", "sku", "warehouse_code",
            name="uq_demand_overrides_run_week_sku_wh",
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    plan_run_id = Column(Integer, ForeignKey("plan_runs.id", ondelete="CASCADE"), nullable=False)
    week_start = Column(Date, nullable=False, index=True)
    sku = Column(String(64), nullable=False, index=True)
    warehouse_code = Column(String(32), nullable=False, index=True)
    override_qty = Column(Numeric(18, 4), nullable=False)
    reason_code = Column(String(64), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(String(256), nullable=True)


class PlannedOrderOverrideWeekly(Base):
    __tablename__ = "planned_order_overrides_weekly"
    __table_args__ = (
        UniqueConstraint(
            "plan_run_id", "week_start", "sku", "warehouse_code",
            name="uq_planned_order_overrides_run_week_sku_wh",
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    plan_run_id = Column(Integer, ForeignKey("plan_runs.id", ondelete="CASCADE"), nullable=False)
    week_start = Column(Date, nullable=False, index=True)
    sku = Column(String(64), nullable=False, index=True)
    warehouse_code = Column(String(32), nullable=False, index=True)
    override_order_qty = Column(Numeric(18, 4), nullable=False)
    reason_code = Column(String(64), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(String(256), nullable=True)


class PlanRunFreezeEvent(Base):
    __tablename__ = "plan_run_freeze_events"
    id = Column(Integer, primary_key=True, index=True)
    plan_run_id = Column(Integer, ForeignKey("plan_runs.id", ondelete="CASCADE"), nullable=False)
    frozen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    frozen_by = Column(String(256), nullable=True)
    freeze_weeks = Column(Integer, nullable=False)
    scope = Column(String(32), nullable=False)
    notes = Column(Text, nullable=True)


class PlanRunEvent(Base):
    __tablename__ = "plan_run_events"
    id = Column(Integer, primary_key=True, index=True)
    plan_run_id = Column(Integer, ForeignKey("plan_runs.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(String(256), nullable=True)
    details_json = Column(JSON, nullable=True)


class ProjectedInventory(Base):
    """Stored per week: start_qty, receipts_qty, demand_qty, end_qty (projected_qty), weeks_cover (weeks_of_cover), stockout."""
    __tablename__ = "projected_inventory"
    id = Column(Integer, primary_key=True, index=True)
    plan_run_id = Column(Integer, ForeignKey("plan_runs.id"), nullable=False)
    week_start = Column(Date, nullable=False, index=True)
    sku = Column(String(64), nullable=False, index=True)
    warehouse_code = Column(String(32), nullable=False, index=True)
    start_qty = Column(Numeric(18, 4), nullable=False, default=0)
    receipts_qty = Column(Numeric(18, 4), nullable=False, default=0)
    demand_qty = Column(Numeric(18, 4), nullable=False, default=0)
    projected_qty = Column(Numeric(18, 4), nullable=False)  # end_qty = start_qty + receipts_qty - demand_qty
    weeks_of_cover = Column(Numeric(10, 2), nullable=True)  # weeks_cover
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
    is_frozen = Column(Boolean, nullable=False, server_default=text("0"))
    plan_run = relationship("PlanRun", back_populates="planned_orders")


PlanRun.projected_inventory = relationship("ProjectedInventory", back_populates="plan_run")
PlanRun.planned_orders = relationship("PlannedOrder", back_populates="plan_run")


# --- Backbone schema (admin-first weekly supply planning) ---

class SafetyStockModeEnum(str, enum.Enum):
    FIXED_UNITS = "fixed_units"
    FIXED_WEEKS = "fixed_weeks"


class StockSourceEnum(str, enum.Enum):
    IMPORT = "import"
    MANUAL = "manual"


class InboundSourceEnum(str, enum.Enum):
    IMPORT = "import"
    MANUAL = "manual"


class DemandSourceEnum(str, enum.Enum):
    IMPORT = "import"
    MANUAL = "manual"
    FORECAST = "forecast"


class BreachStatusEnum(str, enum.Enum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class CalendarWeek(Base):
    __tablename__ = "calendar_weeks"
    id = Column(Integer, primary_key=True, index=True)
    iso_year = Column(Integer, nullable=False, index=True)
    iso_week = Column(Integer, nullable=False, index=True)
    week_start_date = Column(Date, nullable=False)
    week_end_date = Column(Date, nullable=False)
    __table_args__ = (UniqueConstraint("iso_year", "iso_week", name="uq_calendar_weeks_iso"),)


class SupplierProduct(Base):
    __tablename__ = "supplier_products"
    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    lead_time_weeks = Column(Integer, nullable=False, server_default="0")
    moq_units = Column(Integer, nullable=True)
    pack_size_units = Column(Integer, nullable=True)
    active = Column(Boolean, nullable=False, server_default=text("1"))
    supplier = relationship("Supplier", back_populates="supplier_products")
    product = relationship("Product", back_populates="supplier_products")
    __table_args__ = (UniqueConstraint("supplier_id", "product_id", name="uq_supplier_products_supplier_product"),)


class ProductMasterAttributes(Base):
    """Logistics/cost attributes per SKU (non-planning). One row per sku."""
    __tablename__ = "product_master_attributes"
    __table_args__ = (UniqueConstraint("sku", name="uq_product_master_attributes_sku"),)
    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(64), ForeignKey("products.sku", ondelete="CASCADE"), nullable=False, index=True)
    shelf_life_text = Column(Text, nullable=True)
    hs_code = Column(String(64), nullable=True)
    pallet_weight_kg = Column(Numeric(12, 4), nullable=True)
    pallet_dimensions_text = Column(Text, nullable=True)
    ti_hi = Column(String(32), nullable=True)
    price_unit = Column(Numeric(18, 4), nullable=True)
    cogs_unit = Column(Numeric(18, 4), nullable=True)
    cogs_selling_unit = Column(Numeric(18, 4), nullable=True)
    currency = Column(String(8), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ProductMasterStage(Base):
    """Staging rows for product_master ingestion (payload = raw CSV row)."""
    __tablename__ = "product_master_stage"
    id = Column(Integer, primary_key=True, index=True)
    ingestion_run_id = Column(Uuid(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False)
    row_number = Column(Integer, nullable=False)
    payload = Column(JSON, nullable=False)


class WarehouseProduct(Base):
    __tablename__ = "warehouse_products"
    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    safety_stock_mode = Column(
        SQLEnum(SafetyStockModeEnum, name="safety_stock_mode_enum", create_constraint=False),
        nullable=False,
        server_default="fixed_units",
    )
    safety_stock_units = Column(Integer, nullable=True)
    safety_stock_weeks = Column(Numeric(10, 2), nullable=True)
    haulage_buffer_weeks = Column(Integer, nullable=False, server_default="0")
    stocking_buffer_weeks = Column(Integer, nullable=False, server_default="0")
    reorder_review_weeks = Column(Integer, nullable=False, server_default="1")
    active = Column(Boolean, nullable=False, server_default=text("1"))
    warehouse = relationship("Warehouse", back_populates="warehouse_products")
    product = relationship("Product", back_populates="warehouse_products")
    __table_args__ = (UniqueConstraint("warehouse_id", "product_id", name="uq_warehouse_products_wh_product"),)


class StockPositionWeekly(Base):
    __tablename__ = "stock_positions_weekly"
    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    calendar_week_id = Column(Integer, ForeignKey("calendar_weeks.id"), nullable=False)
    on_hand_units = Column(Integer, nullable=False, server_default="0")
    source = Column(
        SQLEnum(StockSourceEnum, name="stock_source_enum", create_constraint=False),
        nullable=False,
        server_default="import",
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    warehouse = relationship("Warehouse")
    product = relationship("Product")
    calendar_week = relationship("CalendarWeek")
    __table_args__ = (
        UniqueConstraint("warehouse_id", "product_id", "calendar_week_id", name="uq_stock_positions_wh_product_week"),
    )


class InboundOrderWeekly(Base):
    __tablename__ = "inbound_orders_weekly"
    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    calendar_week_id = Column(Integer, ForeignKey("calendar_weeks.id"), nullable=False)
    inbound_units = Column(Integer, nullable=False, server_default="0")
    source = Column(
        SQLEnum(InboundSourceEnum, name="inbound_source_enum", create_constraint=False),
        nullable=False,
        server_default="import",
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    warehouse = relationship("Warehouse")
    product = relationship("Product")
    supplier = relationship("Supplier")
    calendar_week = relationship("CalendarWeek")


class DemandWeekly(Base):
    __tablename__ = "demand_weekly"
    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    calendar_week_id = Column(Integer, ForeignKey("calendar_weeks.id"), nullable=False)
    demand_units = Column(Integer, nullable=False, server_default="0")
    source = Column(
        SQLEnum(DemandSourceEnum, name="demand_source_enum", create_constraint=False),
        nullable=False,
        server_default="import",
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    warehouse = relationship("Warehouse")
    product = relationship("Product")
    calendar_week = relationship("CalendarWeek")
    __table_args__ = (UniqueConstraint("warehouse_id", "product_id", "calendar_week_id", name="uq_demand_weekly_wh_product_week"),)


class ProjectionWeekly(Base):
    __tablename__ = "projections_weekly"
    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    calendar_week_id = Column(Integer, ForeignKey("calendar_weeks.id"), nullable=False)
    opening_units = Column(Integer, nullable=False)
    inbound_units = Column(Integer, nullable=False)
    demand_units = Column(Integer, nullable=False)
    closing_units = Column(Integer, nullable=False)
    weeks_of_supply = Column(Numeric(12, 4), nullable=True)
    safety_stock_target_units = Column(Integer, nullable=False)
    breach_status = Column(
        SQLEnum(BreachStatusEnum, name="breach_status_enum", create_constraint=False),
        nullable=False,
    )
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    run_id = Column(String(36), nullable=False, index=True)
    warehouse = relationship("Warehouse")
    product = relationship("Product")
    calendar_week = relationship("CalendarWeek")
    __table_args__ = (
        UniqueConstraint("run_id", "warehouse_id", "product_id", "calendar_week_id", name="uq_projections_run_wh_product_week"),
    )


# --- Ingestion + canonical weekly + baseline forecast backbone ---


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [m.value for m in enum_cls]  # type: ignore[arg-type]


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type = Column(
        SQLEnum(IngestionSourceType, values_callable=_enum_values),
        nullable=False,
    )
    entity = Column(
        SQLEnum(IngestionEntity, values_callable=_enum_values),
        nullable=False,
    )
    file_name = Column(String(512), nullable=True)
    file_sha256 = Column(String(64), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(
        SQLEnum(IngestionStatus, values_callable=_enum_values),
        nullable=False,
        server_default="pending",
    )
    row_count = Column(Integer, default=0)
    inserted_count = Column(Integer, default=0)
    updated_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    error_summary = Column(Text, nullable=True)
    created_by = Column(String(256), nullable=True)
    # Weekly vs historical ingestion mode
    mode = Column(
        SQLEnum(IngestionMode, values_callable=_enum_values, native_enum=False, length=32),
        nullable=True,
        server_default="weekly",
    )
    date_min = Column(Date, nullable=True)
    date_max = Column(Date, nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    requires_confirm = Column(Boolean, nullable=False, server_default=text("0"))
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_by = Column(String(256), nullable=True)
    progress_meta = Column(JSON, nullable=True)
    rejections = relationship("IngestionRejection", back_populates="ingestion_run", cascade="all, delete-orphan")
    demand_stage_rows = relationship("DemandStageWeekly", back_populates="ingestion_run", cascade="all, delete-orphan")
    forecast_output_stage_rows = relationship(
        "ForecastRunOutputStage", back_populates="ingestion_run", cascade="all, delete-orphan"
    )
    sales_out_stage_rows = relationship(
        "SalesOutStage", back_populates="ingestion_run", cascade="all, delete-orphan"
    )
    stock_on_hand_stage_rows = relationship(
        "StockOnHandStage", back_populates="ingestion_run", cascade="all, delete-orphan"
    )


class IngestionRejection(Base):
    __tablename__ = "ingestion_rejections"
    id = Column(Integer, primary_key=True, index=True)
    ingestion_run_id = Column(Uuid(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False)
    row_number = Column(Integer, nullable=False)
    raw_payload = Column(JSON, nullable=True)
    reason = Column(Text, nullable=False)
    ingestion_run = relationship("IngestionRun", back_populates="rejections")


class SkuCodeMap(Base):
    __tablename__ = "sku_code_map"
    id = Column(Integer, primary_key=True, index=True)
    old_sku = Column(String(64), nullable=False, index=True)
    new_sku = Column(String(64), nullable=False, index=True)
    effective_from_week_start = Column(Date, nullable=True)
    effective_to_week_start = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    __table_args__ = (
        UniqueConstraint("old_sku", "new_sku", "effective_from_week_start", name="uq_sku_code_map_old_new_from"),
    )


class DemandStageWeekly(Base):
    __tablename__ = "demand_stage_weekly"
    id = Column(Integer, primary_key=True, index=True)
    ingestion_run_id = Column(Uuid(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False)
    week_start = Column(Date, nullable=False, index=True)
    sku_raw = Column(String(64), nullable=False)
    sku = Column(String(64), nullable=False)
    warehouse_code = Column(String(32), nullable=False)
    demand_type = Column(SQLEnum(DemandType), nullable=False)
    qty = Column(Numeric(18, 4), nullable=False)
    source = Column(String(64), nullable=True)
    ingestion_run = relationship("IngestionRun", back_populates="demand_stage_rows")


class DemandFactsWeekly(Base):
    """Canonical weekly demand fact table; single truth for forecasting."""
    __tablename__ = "demand_facts_weekly"
    __table_args__ = (
        UniqueConstraint(
            "week_start", "sku", "warehouse_code", "demand_type",
            name="uq_demand_facts_weekly_week_sku_wh_type",
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    week_start = Column(Date, nullable=False, index=True)
    sku = Column(String(64), nullable=False, index=True)
    warehouse_code = Column(String(32), nullable=False, index=True)
    demand_type = Column(SQLEnum(DemandType), nullable=False)
    qty = Column(Numeric(18, 4), nullable=False)
    source_run_id = Column(Uuid(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="SET NULL"), nullable=True)
    is_imputed = Column(Boolean, nullable=False, server_default=text("0"))
    is_outlier = Column(Boolean, nullable=False, server_default=text("0"))
    outlier_method = Column(String(64), nullable=True)


class BaselineForecastWeekly(Base):
    __tablename__ = "baseline_forecasts_weekly"
    __table_args__ = (
        UniqueConstraint(
            "sku", "warehouse_code", "week_start", "model_name", "model_version", "train_end_week_start",
            name="uq_baseline_forecasts_sku_wh_week_model_train",
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(64), nullable=False, index=True)
    warehouse_code = Column(String(32), nullable=False, index=True)
    week_start = Column(Date, nullable=False, index=True)  # target week (W-TUE)
    horizon_week_index = Column(Integer, nullable=True)  # derived, optional
    forecast_qty = Column(Numeric(18, 4), nullable=False)
    model_name = Column(String(64), nullable=False)
    model_version = Column(String(64), nullable=False)
    trained_at = Column(DateTime(timezone=True), nullable=False)
    train_window_start = Column(Date, nullable=False)
    train_window_end = Column(Date, nullable=False)
    train_end_week_start = Column(Date, nullable=False, index=True)  # inference_date / run date
    metrics_json = Column(JSON, nullable=True)


class SalesOutStage(Base):
    """Staging rows for Sales Out ingestion (CSV/XLSX)."""
    __tablename__ = "sales_out_stage"
    id = Column(Integer, primary_key=True, index=True)
    ingestion_run_id = Column(Uuid(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False)
    aah_product_code = Column(Text, nullable=False)
    account_code = Column(Text, nullable=True)
    customer_name = Column(Text, nullable=True)
    postcode = Column(Text, nullable=True)
    customer_sector = Column(Text, nullable=True)
    pip_code = Column(Text, nullable=True)
    product_name = Column(Text, nullable=True)
    item_size = Column(Text, nullable=True)
    invoiced_qty = Column(Numeric(18, 4), nullable=True)
    servings_qty = Column(Numeric(18, 4), nullable=True)
    net_sales_value = Column(Numeric(18, 4), nullable=True)
    processed_date = Column(Date, nullable=False)
    processed_year = Column(Integer, nullable=True)
    print_branch = Column(Text, nullable=True)
    branch = Column(Text, nullable=True)
    raw_json = Column(JSON, nullable=True)
    ingestion_run = relationship("IngestionRun", back_populates="sales_out_stage_rows")


class WarehouseBranchMapping(Base):
    """Maps SOH Branch Name to warehouse_code (e.g. GLASGOW -> GLA)."""
    __tablename__ = "warehouse_branch_mapping"
    id = Column(Integer, primary_key=True, index=True)
    branch_name = Column(String(128), nullable=False, unique=True, index=True)
    warehouse_code = Column(String(32), nullable=False, index=True)


class WarehouseProductCode(Base):
    """Persistent mapping: (warehouse_code, external_code) -> canonical products.sku. Used first in SOH resolution."""
    __tablename__ = "warehouse_product_codes"
    __table_args__ = (UniqueConstraint("warehouse_code", "external_code", name="uq_warehouse_product_codes_wh_ext"),)
    id = Column(Integer, primary_key=True, index=True)
    warehouse_code = Column(String(32), nullable=False, index=True)
    external_code = Column(String(128), nullable=False, index=True)
    sku = Column(String(64), ForeignKey("products.sku", ondelete="CASCADE"), nullable=False, index=True)
    external_name = Column(Text, nullable=True)
    hs_code = Column(String(64), nullable=True)
    active = Column(Boolean, nullable=False, server_default=text("1"))
    match_method = Column(String(32), nullable=True)
    match_confidence = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class StockOnHandStage(Base):
    """Staging rows for SOH ingestion (CSV/XLSX)."""
    __tablename__ = "stock_on_hand_stage"
    id = Column(Integer, primary_key=True, index=True)
    ingestion_run_id = Column(Uuid(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False)
    stock_at_raw = Column(Text, nullable=True)
    branch_name_raw = Column(Text, nullable=True)
    aah_code_raw = Column(Text, nullable=True)
    stock_raw = Column(Text, nullable=True)
    on_order_raw = Column(Text, nullable=True)
    description_raw = Column(Text, nullable=True)
    reject_reason = Column(Text, nullable=True)
    row_hash = Column(String(64), nullable=True)
    ingestion_run = relationship("IngestionRun", back_populates="stock_on_hand_stage_rows")


class InventorySnapshotDaily(Base):
    """Daily inventory snapshots (e.g. from SOH); rolled up to weekly for planning."""
    __tablename__ = "inventory_snapshots_daily"
    __table_args__ = (
        UniqueConstraint("warehouse_code", "sku", "as_of_date", "source_type", name="uq_inv_daily_wh_sku_date_source"),
    )
    id = Column(Integer, primary_key=True, index=True)
    warehouse_code = Column(String(32), nullable=False, index=True)
    sku = Column(String(64), nullable=False, index=True)
    as_of_date = Column(Date, nullable=False, index=True)
    on_hand_units = Column(Numeric(18, 4), nullable=False, server_default="0")
    on_order_units = Column(Numeric(18, 4), nullable=False, server_default="0")
    source_type = Column(String(32), nullable=False)
    source_run_id = Column(Uuid(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ForecastRunOutputStage(Base):
    """Staging rows for forecast output ingestion (Excel/CSV)."""
    __tablename__ = "forecast_run_output_stage"
    id = Column(Integer, primary_key=True, index=True)
    ingestion_run_id = Column(Uuid(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False)
    aah_product_code = Column(Text, nullable=False)
    product_name = Column(Text, nullable=True)
    inference_date = Column(Date, nullable=False)
    forecast_week = Column(Date, nullable=False)
    actual = Column(Numeric(18, 4), nullable=True)
    interpolated_values = Column(Numeric(18, 4), nullable=True)
    forecast = Column(Numeric(18, 4), nullable=True)
    model = Column(Text, nullable=False)
    model_details = Column(Text, nullable=True)
    mae = Column(Numeric(18, 4), nullable=True)
    mape = Column(Numeric(18, 4), nullable=True)
    is_best_model = Column(Boolean, nullable=True)
    outlier = Column(Integer, nullable=True)
    predicted_best_model_bool = Column(Boolean, nullable=True)
    raw_json = Column(JSON, nullable=True)
    ingestion_run = relationship("IngestionRun", back_populates="forecast_output_stage_rows")


class PublishedBaselineForecastWeekly(Base):
    """Single selected baseline series per (sku, warehouse, week, train_end_week_start); used when demand_source=baseline."""
    __tablename__ = "published_baseline_forecasts_weekly"
    __table_args__ = (
        UniqueConstraint(
            "sku", "warehouse_code", "week_start", "train_end_week_start",
            name="uq_published_baseline_sku_wh_week_train",
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(64), nullable=False, index=True)
    warehouse_code = Column(String(32), nullable=False, index=True)
    week_start = Column(Date, nullable=False, index=True)
    forecast_qty = Column(Numeric(18, 4), nullable=False)
    train_end_week_start = Column(Date, nullable=False, index=True)
    selected_model_name = Column(String(64), nullable=False)
    selected_model_version = Column(String(256), nullable=False)


class ForecastRunMetrics(Base):
    """WAPE/Bias per (model, train_end_week_start, sku, warehouse) for baseline runs."""
    __tablename__ = "forecast_run_metrics"
    __table_args__ = (
        UniqueConstraint(
            "model_name", "model_version", "train_end_week_start", "sku", "warehouse_code",
            name="uq_forecast_run_metrics_model_train_sku_wh",
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String(64), nullable=False)
    model_version = Column(String(64), nullable=False)
    train_end_week_start = Column(Date, nullable=False)
    sku = Column(String(64), nullable=False, index=True)
    warehouse_code = Column(String(32), nullable=False, index=True)
    eval_weeks = Column(Integer, nullable=True)
    wape = Column(Numeric(12, 6), nullable=True)
    bias = Column(Numeric(18, 4), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# --- RBAC ---
class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), unique=True, nullable=False, index=True)
    users = relationship("User", secondary="user_roles", back_populates="roles")


class User(Base):
    __tablename__ = "users"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entra_oid = Column(String(256), unique=True, nullable=True, index=True)
    email = Column(String(256), nullable=False, index=True)
    display_name = Column(String(256), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=text("1"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    roles = relationship("Role", secondary="user_roles", back_populates="users")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)


class AppSettings(Base):
    """Key-value app config (e.g. sample_sales_soh_warehouses)."""
    __tablename__ = "app_settings"
    key = Column(String(128), primary_key=True)
    value = Column(JSON, nullable=False)


# Back-populate relationships on Product, Warehouse, Supplier
Product.supplier_products = relationship("SupplierProduct", back_populates="product")
Product.warehouse_products = relationship("WarehouseProduct", back_populates="product")
Supplier.supplier_products = relationship("SupplierProduct", back_populates="supplier")
Warehouse.warehouse_products = relationship("WarehouseProduct", back_populates="warehouse")

# Forecasting subsystem models — kept in a separate module to isolate scope.
# Importing here ensures they are registered with Base.metadata for Alembic.
from app.forecast_models import (  # noqa: E402, F401
    ForecastSourceConfig,
    ForecastModelConfig,
    ForecastRuntimeConfig,
    ForecastSkuHistoryRule,
    ForecastProductProfile,
    ForecastSalesWeekly,
    ForecastStockWeekly,
    ForecastRun,
    ForecastRunModel,
    ForecastResultWeekly,
    ForecastTrainingSeriesWeekly,
    ForecastRunDiagnostic,
)
