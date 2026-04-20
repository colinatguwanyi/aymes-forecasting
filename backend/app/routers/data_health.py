"""Data health and setup readiness reports."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    DemandActual,
    DemandType,
    IngestionEntity,
    IngestionRun,
    IngestionStatus,
    InventorySnapshotWeekly,
    PlanningPolicy,
    Product,
    Receipt,
    Warehouse,
    WarehouseProductCode,
)
from app.security.auth import require_any_auth

router = APIRouter(dependencies=[Depends(require_any_auth)])


@router.get("")
def get_data_health(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return data health metrics for setup readiness and reports."""
    # Products
    product_count = db.query(Product).count()
    active_count = db.query(Product).filter(Product.active.is_(True)).count()

    # Demand (Sales Out path: demand_actuals CUSTOMER AAH)
    demand_latest = (
        db.query(func.max(DemandActual.week_start))
        .filter(
            DemandActual.demand_type == DemandType.CUSTOMER,
            DemandActual.warehouse_code == "AAH",
        )
        .scalar()
    )
    demand_weeks = (
        db.query(func.count(func.distinct(DemandActual.week_start)))
        .filter(
            DemandActual.demand_type == DemandType.CUSTOMER,
            DemandActual.warehouse_code == "AAH",
        )
        .scalar()
        or 0
    )
    demand_skus = (
        db.query(func.count(func.distinct(DemandActual.sku)))
        .filter(
            DemandActual.demand_type == DemandType.CUSTOMER,
            DemandActual.warehouse_code == "AAH",
        )
        .scalar()
        or 0
    )

    # SOH
    soh_latest = (
        db.query(func.max(InventorySnapshotWeekly.week_start))
        .filter(InventorySnapshotWeekly.warehouse_code == "AAH")
        .scalar()
    )
    soh_skus = (
        db.query(func.count(func.distinct(InventorySnapshotWeekly.sku)))
        .filter(InventorySnapshotWeekly.warehouse_code == "AAH")
        .scalar()
        or 0
    )

    # Receipts (inbound next 8 weeks)
    warehouses = [w.code for w in db.query(Warehouse).filter(Warehouse.active.is_(True)).all()]
    today = date.today()
    eight_weeks_later = today + timedelta(days=56)
    receipts_skus = (
        db.query(func.count(func.distinct(Receipt.sku)))
        .filter(
            Receipt.warehouse_code.in_(warehouses or ["AAH"]),
            Receipt.week_start >= today,
            Receipt.week_start <= eight_weeks_later,
        )
        .scalar()
        or 0
    )
    receipts_latest = (
        db.query(func.max(Receipt.week_start))
        .filter(Receipt.warehouse_code.in_(warehouses or ["AAH"]))
        .scalar()
    )

    # BLP mapping (from latest SOH run progress_meta or unmapped)
    blp_coverage_pct: float | None = None
    units_missing_pct: float | None = None
    latest_soh = (
        db.query(IngestionRun)
        .filter(
            IngestionRun.entity == IngestionEntity.STOCK_ON_HAND,
            IngestionRun.status == IngestionStatus.SUCCESS,
        )
        # MySQL has no NULLS LAST; put non-null finished_at first, then newest first.
        .order_by(IngestionRun.finished_at.is_(None).asc(), IngestionRun.finished_at.desc())
        .first()
    )
    pm = getattr(latest_soh, "progress_meta", None) if latest_soh else None
    if isinstance(pm, dict):
        blp_coverage_pct = pm.get("pct_coverage_codes")
        units_missing_pct = pm.get("pct_units_missing")
    # Warehouse product codes count (BLP mapping table)
    wpc_count = db.query(WarehouseProductCode).filter(WarehouseProductCode.active.is_(True)).count()

    # Ready to plan
    policy_count = db.query(PlanningPolicy).count()
    required_policies = active_count * max(1, len(warehouses))
    ready = (
        product_count > 0
        and demand_latest is not None
        and soh_latest is not None
        and policy_count > 0
    )

    return {
        "products": {"count": product_count, "active": active_count},
        "demand": {
            "latest_week": demand_latest.isoformat() if demand_latest else None,
            "weeks_available": demand_weeks,
            "skus_with_demand": demand_skus,
        },
        "soh": {
            "latest_week": soh_latest.isoformat() if soh_latest else None,
            "skus_with_stock": soh_skus,
        },
        "mapping": {
            "blp_coverage_pct": blp_coverage_pct,
            "units_missing_pct": units_missing_pct,
            "warehouse_product_codes_count": wpc_count,
        },
        "receipts": {
            "latest_week": receipts_latest.isoformat() if receipts_latest else None,
            "skus_with_inbound_next_8_weeks": receipts_skus,
        },
        "planning_policies": {"count": policy_count, "required_approx": required_policies},
        "warehouses_count": len(warehouses),
        "ready_to_plan": ready,
    }
