"""Stock coverage report: weeks_cover = on_hand_qty / avg_weekly_demand from actuals only."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import DemandActual, DemandType, InventorySnapshotWeekly, Product, Warehouse


def _status_bucket(weeks_cover: Decimal | None) -> str:
    """Critical <2, Low <4, Monitor <8, Healthy ≥8, No demand when avg=0."""
    if weeks_cover is None:
        return "No demand"
    f = float(weeks_cover)
    if f < 2:
        return "Critical"
    if f < 4:
        return "Low"
    if f < 8:
        return "Monitor"
    return "Healthy"


def _demand_types_for_warehouse(warehouse_code: str) -> list[DemandType]:
    """AAH → CUSTOMER only; BLP → CUSTOMER + SAMPLES."""
    wh = warehouse_code.strip().upper()
    if wh == "AAH":
        return [DemandType.CUSTOMER]
    if wh == "BLP":
        return [DemandType.CUSTOMER, DemandType.SAMPLES]
    # Default: CUSTOMER only for unknown warehouses
    return [DemandType.CUSTOMER]


def compute_stock_coverage(
    db: Session,
    warehouse_code: str | None = None,
    weeks_window: int = 13,
) -> dict[str, Any]:
    """
    Compute stock coverage per (sku, warehouse).
    - Latest SOH week per warehouse from inventory_snapshots_weekly.
    - Avg weekly demand from demand_actuals over last N weeks.
    - AAH: CUSTOMER only; BLP: CUSTOMER + SAMPLES.
    - weeks_cover = on_hand_qty / avg_weekly_demand; status_bucket per thresholds.
    """
    # Resolve warehouses to include
    if warehouse_code:
        wh_codes = [warehouse_code.strip().upper()]
    else:
        wh_codes = [w.code for w in db.query(Warehouse).filter(Warehouse.active == True).all()]
        if not wh_codes:
            return {"summary": [], "rows": []}

    summary: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []

    for wh in wh_codes:
        # Latest SOH week for this warehouse
        max_week = (
            db.query(func.max(InventorySnapshotWeekly.week_start))
            .filter(
                func.upper(InventorySnapshotWeekly.warehouse_code) == wh,
            )
            .scalar()
        )
        if max_week is None:
            summary.append({
                "warehouse_code": wh,
                "latest_soh_week": None,
                "row_count": 0,
                "critical_count": 0,
                "low_count": 0,
                "monitor_count": 0,
                "healthy_count": 0,
                "no_demand_count": 0,
            })
            continue

        latest_week = max_week if isinstance(max_week, date) else max_week
        from_week = latest_week - timedelta(days=(weeks_window - 1) * 7)
        to_week = latest_week

        demand_types = _demand_types_for_warehouse(str(wh))

        # Latest SOH per (sku, warehouse): subquery for max week per sku, then join
        soh_subq = (
            db.query(
                InventorySnapshotWeekly.sku,
                InventorySnapshotWeekly.warehouse_code,
                func.max(InventorySnapshotWeekly.week_start).label("max_week"),
            )
            .filter(
                func.upper(InventorySnapshotWeekly.warehouse_code) == wh,
                InventorySnapshotWeekly.week_start <= latest_week,
            )
            .group_by(InventorySnapshotWeekly.sku, InventorySnapshotWeekly.warehouse_code)
            .subquery()
        )

        # Get on_hand_qty for latest week per sku; prefer source_type='soh' over 'legacy'
        soh_raw = (
            db.query(
                InventorySnapshotWeekly.sku,
                InventorySnapshotWeekly.warehouse_code,
                InventorySnapshotWeekly.week_start,
                InventorySnapshotWeekly.on_hand_qty,
                InventorySnapshotWeekly.source_type,
            )
            .join(
                soh_subq,
                (InventorySnapshotWeekly.sku == soh_subq.c.sku)
                & (InventorySnapshotWeekly.warehouse_code == soh_subq.c.warehouse_code)
                & (InventorySnapshotWeekly.week_start == soh_subq.c.max_week),
            )
            .filter(func.upper(InventorySnapshotWeekly.warehouse_code) == wh)
            .all()
        )
        # Dedupe by sku: prefer 'soh' over 'legacy'
        seen: dict[str, Any] = {}
        for r in soh_raw:
            if r.sku not in seen or (r.source_type == "soh" and seen[r.sku].source_type != "soh"):
                seen[r.sku] = r
        soh_rows = list(seen.values())

        # Demand: sum per (sku, warehouse) over [from_week, to_week], filtered by demand_type
        demand_rows = (
            db.query(
                DemandActual.sku,
                DemandActual.warehouse_code,
                func.sum(DemandActual.qty).label("total_qty"),
            )
            .filter(
                func.upper(DemandActual.warehouse_code) == wh,
                DemandActual.week_start >= from_week,
                DemandActual.week_start <= to_week,
                DemandActual.demand_type.in_(demand_types),
            )
            .group_by(DemandActual.sku, DemandActual.warehouse_code)
            .all()
        )

        demand_map: dict[str, Decimal] = {}
        for r in demand_rows:
            total = Decimal(str(r.total_qty)) if r.total_qty is not None else Decimal("0")
            demand_map[r.sku] = total

        # Build rows: only SKUs that exist in products (active)
        product_skus = {p.sku for p in db.query(Product.sku).filter(Product.active == True).all()}

        wh_rows: list[dict[str, Any]] = []
        for r in soh_rows:
            sku = r.sku
            if sku not in product_skus:
                continue
            on_hand = Decimal(str(r.on_hand_qty)) if r.on_hand_qty is not None else Decimal("0")
            total_demand = demand_map.get(sku, Decimal("0"))

            # avg_weekly_demand = total over window / weeks_window
            if total_demand > 0 and weeks_window > 0:
                avg_demand = (total_demand / Decimal(str(weeks_window))).quantize(Decimal("0.0001"))
                weeks_cover = (on_hand / avg_demand).quantize(Decimal("0.01"))
            else:
                avg_demand = Decimal("0")
                weeks_cover = None

            status = _status_bucket(weeks_cover)
            row = {
                "sku": sku,
                "warehouse_code": r.warehouse_code,
                "on_hand_qty": float(on_hand),
                "avg_weekly_demand": float(avg_demand),
                "weeks_cover": float(weeks_cover) if weeks_cover is not None else None,
                "status_bucket": status,
            }
            wh_rows.append(row)
            all_rows.append(row)

        # Summary counts for this warehouse
        critical = sum(1 for x in wh_rows if x["status_bucket"] == "Critical")
        low = sum(1 for x in wh_rows if x["status_bucket"] == "Low")
        monitor = sum(1 for x in wh_rows if x["status_bucket"] == "Monitor")
        healthy = sum(1 for x in wh_rows if x["status_bucket"] == "Healthy")
        no_demand = sum(1 for x in wh_rows if x["status_bucket"] == "No demand")

        summary.append({
            "warehouse_code": wh,
            "latest_soh_week": latest_week.isoformat(),
            "row_count": len(wh_rows),
            "critical_count": critical,
            "low_count": low,
            "monitor_count": monitor,
            "healthy_count": healthy,
            "no_demand_count": no_demand,
        })

    # Sort rows by weeks_cover ascending (lowest first, nulls last)
    def sort_key(r: dict[str, Any]) -> tuple[bool, float]:
        wc = r.get("weeks_cover")
        if wc is None:
            return (True, 999999.0)  # No demand last
        return (False, wc)

    all_rows.sort(key=sort_key)

    return {"summary": summary, "rows": all_rows}


