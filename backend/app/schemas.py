from __future__ import annotations
import logging
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models import DemandType, PlanningMode, SafetyStockMethod

logger = logging.getLogger(__name__)


class ProductBase(BaseModel):
    sku: str
    name: Optional[str] = None
    description: Optional[str] = None


class ProductCreate(ProductBase):
    pass


class Product(ProductBase):
    id: int

    class Config:
        from_attributes = True


class WarehouseBase(BaseModel):
    code: str
    name: Optional[str] = None


class WarehouseCreate(WarehouseBase):
    pass


class Warehouse(WarehouseBase):
    id: int

    class Config:
        from_attributes = True


class SupplierBase(BaseModel):
    code: str
    name: Optional[str] = None


class SupplierCreate(SupplierBase):
    pass


class Supplier(SupplierBase):
    id: int

    class Config:
        from_attributes = True


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


class PlanRun(PlanRunBase):
    id: int

    class Config:
        from_attributes = True


class ProjectedInventoryBase(BaseModel):
    week_start: date
    sku: str
    warehouse_code: str
    start_qty: Optional[Decimal] = None
    receipts_qty: Optional[Decimal] = None
    demand_qty: Optional[Decimal] = None
    projected_qty: Decimal
    weeks_of_cover: Optional[Decimal] = None
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
