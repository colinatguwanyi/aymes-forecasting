from __future__ import annotations
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models import DemandType, PlanningMode, SafetyStockMethod

logger = logging.getLogger(__name__)


class ProductBase(BaseModel):
    sku: str
    name: Optional[str] = None
    description: Optional[str] = None
    uom: str = "units"
    active: bool = True


class ProductCreate(ProductBase):
    pass


class Product(ProductBase):
    id: int

    class Config:
        from_attributes = True


class WarehouseBase(BaseModel):
    code: str
    name: Optional[str] = None
    timezone: str = "Europe/London"
    active: bool = True


class WarehouseCreate(WarehouseBase):
    pass


class Warehouse(WarehouseBase):
    id: int

    class Config:
        from_attributes = True


class SupplierBase(BaseModel):
    code: str
    name: Optional[str] = None
    active: bool = True


class SupplierCreate(SupplierBase):
    pass


class Supplier(SupplierBase):
    id: int

    class Config:
        from_attributes = True


# Backbone: warehouse_products, supplier_products
class WarehouseProductBase(BaseModel):
    safety_stock_mode: str = "fixed_units"  # "fixed_units" | "fixed_weeks"
    safety_stock_units: Optional[int] = None
    safety_stock_weeks: Optional[Decimal] = None
    haulage_buffer_weeks: int = 0
    stocking_buffer_weeks: int = 0
    reorder_review_weeks: int = 1
    active: bool = True


class WarehouseProductCreate(WarehouseProductBase):
    warehouse_id: int
    product_id: int


class WarehouseProduct(WarehouseProductBase):
    id: int
    warehouse_id: int
    product_id: int

    class Config:
        from_attributes = True


class WarehouseProductUpdate(BaseModel):
    safety_stock_mode: Optional[str] = None
    safety_stock_units: Optional[int] = None
    safety_stock_weeks: Optional[Decimal] = None
    haulage_buffer_weeks: Optional[int] = None
    stocking_buffer_weeks: Optional[int] = None
    reorder_review_weeks: Optional[int] = None
    active: Optional[bool] = None


class SupplierProductBase(BaseModel):
    lead_time_weeks: int = 0
    moq_units: Optional[int] = None
    pack_size_units: Optional[int] = None
    active: bool = True


class SupplierProductCreate(SupplierProductBase):
    supplier_id: int
    product_id: int


class SupplierProduct(SupplierProductBase):
    id: int
    supplier_id: int
    product_id: int

    class Config:
        from_attributes = True


class SupplierProductUpdate(BaseModel):
    lead_time_weeks: Optional[int] = None
    moq_units: Optional[int] = None
    pack_size_units: Optional[int] = None
    active: Optional[bool] = None


class LaneBase(BaseModel):
    supplier_id: int
    warehouse_id: int
    code: Optional[str] = None


class LaneCreate(LaneBase):
    pass


class Lane(LaneBase):
    id: int

    class Config:
        from_attributes = True


class PlanningPolicyBase(BaseModel):
    sku: str
    warehouse_code: str
    mode: PlanningMode = PlanningMode.WOS_TARGET
    target_weeks: Decimal = Decimal("4")
    safety_stock_method: SafetyStockMethod = SafetyStockMethod.WEEKS
    safety_stock_weeks: Decimal = Decimal("1")
    service_level: Decimal = Decimal("0.95")
    forecast_window_weeks: int = 8
    lead_time_production_weeks: Decimal = Decimal("2")
    lead_time_slot_wait_weeks: Decimal = Decimal("0")
    lead_time_haulage_weeks: Decimal = Decimal("1")
    lead_time_putaway_weeks: Decimal = Decimal("0")
    lead_time_padding_weeks: Decimal = Decimal("0")
    include_samples: bool = True


class PlanningPolicyCreate(PlanningPolicyBase):
    pass


class PlanningPolicy(PlanningPolicyBase):
    id: int

    class Config:
        from_attributes = True


class InventorySnapshotBase(BaseModel):
    week_start: date
    sku: str
    warehouse_code: str
    on_hand_qty: Decimal = Decimal("0")


class InventorySnapshot(InventorySnapshotBase):
    id: int

    class Config:
        from_attributes = True


class ReceiptBase(BaseModel):
    week_start: date
    sku: str
    warehouse_code: str
    qty: Decimal
    source_type: Optional[str] = None


class Receipt(ReceiptBase):
    id: int

    class Config:
        from_attributes = True


class DemandActualBase(BaseModel):
    week_start: date
    sku: str
    warehouse_code: str
    demand_type: DemandType
    qty: Decimal


class DemandActual(DemandActualBase):
    id: int

    class Config:
        from_attributes = True


class PlanRunBase(BaseModel):
    scenario_name: str
    run_at: date
    created_at: date
    demand_source: str = "actuals"
    freeze_weeks: int = 4
    plan_start_week_start: Optional[date] = None
    created_by: Optional[str] = None
    notes: Optional[str] = None


class PlanRun(PlanRunBase):
    id: int

    class Config:
        from_attributes = True


class ProjectedInventoryBase(BaseModel):
    """Auditability: start_qty, receipts_qty, demand_qty, end_qty (projected_qty), weeks_cover (weeks_of_cover), stockout."""
    week_start: date
    sku: str
    warehouse_code: str
    start_qty: Optional[Decimal] = None
    receipts_qty: Optional[Decimal] = None
    demand_qty: Optional[Decimal] = None
    projected_qty: Decimal  # end_qty
    weeks_of_cover: Optional[Decimal] = None  # weeks_cover
    stockout: bool = False


class ProjectedInventory(ProjectedInventoryBase):
    id: int
    plan_run_id: int

    class Config:
        from_attributes = True


class PlannedOrderBase(BaseModel):
    week_start: date
    sku: str
    warehouse_code: str
    order_qty: Decimal


class PlannedOrder(PlannedOrderBase):
    id: int
    plan_run_id: int

    class Config:
        from_attributes = True


# SKU-week explainability (Phase 1: forecast transparency)
class SkuWeekExplanationPolicy(BaseModel):
    """Policy inputs used for this SKU/week."""
    mode: Optional[str] = None
    target_weeks: Optional[Decimal] = None
    safety_stock_weeks: Optional[Decimal] = None
    safety_stock_method: Optional[str] = None
    forecast_window_weeks: Optional[int] = None
    lead_time_production_weeks: Optional[Decimal] = None
    lead_time_slot_wait_weeks: Optional[Decimal] = None
    lead_time_haulage_weeks: Optional[Decimal] = None
    lead_time_putaway_weeks: Optional[Decimal] = None
    lead_time_padding_weeks: Optional[Decimal] = None
    include_samples: bool = True


class SkuWeekExplanationProjection(BaseModel):
    """Projection outputs for this SKU/week."""
    week_start: date
    start_qty: Optional[Decimal] = None
    receipts_qty: Optional[Decimal] = None
    demand_qty: Optional[Decimal] = None
    projected_qty: Decimal
    weeks_of_cover: Optional[Decimal] = None
    stockout: bool = False


class SkuWeekExplanation(BaseModel):
    """Explain-the-forecast payload for one SKU/week."""
    sku: str
    warehouse_code: str
    plan_run_id: int
    policy: Optional[SkuWeekExplanationPolicy] = None
    projection: Optional[SkuWeekExplanationProjection] = None
    forecast_method: str = "trailing_mean"


# Exceptions (Phase 3: derived from projected inventory)
class PlanningException(BaseModel):
    """One planning exception (stockout or low cover) for the exceptions queue."""
    type: str  # "stockout" | "low_cover"
    severity: str  # "error" | "warning"
    sku: str
    warehouse_code: str
    week_start: date
    message: str
    projected_qty: Optional[Decimal] = None
    weeks_of_cover: Optional[Decimal] = None
    plan_run_id: int


# Import validation
class ImportRowError(BaseModel):
    row: int
    errors: list[str]


class ImportDryRunResult(BaseModel):
    valid: bool
    total_rows: int
    valid_rows: int
    errors: list[ImportRowError] = Field(default_factory=list)
    preview: Optional[list[dict[str, Any]]] = None


# Warehouse Product Codes (external_code → sku mapping per warehouse)
class WarehouseProductCodeCreate(BaseModel):
    warehouse_code: str = Field(..., min_length=1, max_length=32)
    external_code: str = Field(..., min_length=1, max_length=128)
    sku: str = Field(..., min_length=1, max_length=64)
    external_name: Optional[str] = None
    hs_code: Optional[str] = Field(None, max_length=64)
    active: bool = True
    match_method: Optional[str] = Field(None, max_length=32)
    match_confidence: Optional[int] = Field(None, ge=0, le=100)


class WarehouseProductCodeUpdate(BaseModel):
    sku: Optional[str] = Field(None, min_length=1, max_length=64)
    external_name: Optional[str] = None
    hs_code: Optional[str] = Field(None, max_length=64)
    active: Optional[bool] = None
    match_method: Optional[str] = Field(None, max_length=32)
    match_confidence: Optional[int] = Field(None, ge=0, le=100)


class WarehouseProductCodeResponse(BaseModel):
    id: int
    warehouse_code: str
    external_code: str
    sku: str
    external_name: Optional[str]
    hs_code: Optional[str]
    active: bool
    match_method: Optional[str]
    match_confidence: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
