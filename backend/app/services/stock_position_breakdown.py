"""
Stock position calculation breakdown for a plan run.
Per SKU x warehouse: inputs (on hand, inbound, demand), policy, derived (reorder point, target stock,
next breach week, recommended order week/qty rounded to MOQ/increment).
Consistent with planning engine (planning.py) and uses plan_run_id as scenario context.
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import case
from sqlalchemy.orm import Session

from app.models import (
    InventorySnapshotWeekly,
    Lane,
    PlanRun,
    PlanRunDemandInputWeekly,
    PlannedOrder,
    PlanningPolicy,
    PlanningMode,
    Product,
    ProjectedInventory,
    SafetyStockMethod,
    SupplierProduct,
    Warehouse,
    WarehouseProduct,
)

logger = logging.getLogger(__name__)


def _monday_before(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _next_monday(d: date) -> date:
    return _monday_before(d) + timedelta(days=7)


def _round_to_moq_and_increment(
    qty: float,
    moq_units: int | None,
    pack_size_units: int | None,
) -> float:
    """
    Round qty: if MOQ exists, ceil to MOQ multiple (qty in (0, MOQ) -> MOQ);
    if increment (pack_size) exists, ceil to increment multiple.
    """
    if qty <= 0:
        return 0.0
    if moq_units is not None and moq_units > 0:
        if qty < moq_units:
            qty = float(moq_units)
        else:
            qty = math.ceil(qty / moq_units) * moq_units
    if pack_size_units is not None and pack_size_units > 0:
        qty = math.ceil(qty / pack_size_units) * pack_size_units
    return qty


def _get_on_hand(
    db: Session,
    sku: str,
    warehouse_code: str,
    as_of_week: date,
) -> tuple[date | None, Decimal]:
    """Latest on_hand_qty from inventory_snapshots_weekly where week_start <= as_of_week; prefer source_type='soh' over 'legacy'."""
    rows = (
        db.query(InventorySnapshotWeekly)
        .filter(
            InventorySnapshotWeekly.sku == sku,
            InventorySnapshotWeekly.warehouse_code == warehouse_code,
            InventorySnapshotWeekly.week_start <= as_of_week,
        )
        .order_by(
            InventorySnapshotWeekly.week_start.desc(),
            case((InventorySnapshotWeekly.source_type == "soh", 1), else_=0).desc(),
        )
        .limit(1)
        .all()
    )
    if not rows:
        return (None, Decimal("0"))
    r = rows[0]
    return (
        cast(date, r.week_start),
        cast(Decimal, r.on_hand_qty) or Decimal("0"),
    )


def _get_avg_weekly_demand(
    db: Session,
    plan_run_id: int,
    sku: str,
    warehouse_code: str,
    from_week: date,
    num_weeks: int,
) -> Decimal:
    """Average demand from plan_run_demand_inputs_weekly over the window (trailing)."""
    to_week = from_week + timedelta(days=(num_weeks - 1) * 7)
    rows = (
        db.query(PlanRunDemandInputWeekly)
        .filter(
            PlanRunDemandInputWeekly.plan_run_id == plan_run_id,
            PlanRunDemandInputWeekly.sku == sku,
            PlanRunDemandInputWeekly.warehouse_code == warehouse_code,
            PlanRunDemandInputWeekly.week_start >= from_week,
            PlanRunDemandInputWeekly.week_start <= to_week,
        )
        .all()
    )
    if not rows:
        return Decimal("0")
    total = sum(cast(Decimal, r.demand_qty) for r in rows)
    return (total / len(rows)).quantize(Decimal("0.0001"))


def _get_supplier_lead_time_and_pack(
    db: Session,
    sku: str,
    warehouse_code: str,
) -> tuple[int, int | None, int | None]:
    """
    First active lane (supplier→warehouse) with active supplier_product for this SKU.
    Returns (lead_time_weeks, moq_units, pack_size_units).
    """
    product = db.query(Product).filter(Product.sku == sku).first()
    warehouse = db.query(Warehouse).filter(Warehouse.code == warehouse_code).first()
    if not product or not warehouse:
        return (0, None, None)
    lanes = (
        db.query(Lane)
        .filter(Lane.warehouse_id == warehouse.id)
        .order_by(Lane.id)
        .all()
    )
    for lane in lanes:
        sp = (
            db.query(SupplierProduct)
            .filter(
                SupplierProduct.supplier_id == lane.supplier_id,
                SupplierProduct.product_id == product.id,
                SupplierProduct.active.is_(True),
            )
            .first()
        )
        if sp:
            lt = int(cast(int, getattr(sp, "lead_time_weeks", 0)) or 0)
            moq = getattr(sp, "moq_units", None)
            pack = getattr(sp, "pack_size_units", None)
            return (lt, moq, pack)
    return (0, None, None)


def _get_haulage_stocking_buffer_weeks(
    db: Session,
    sku: str,
    warehouse_code: str,
) -> tuple[float, float]:
    """From warehouse_products if present, else (0, 0)."""
    product = db.query(Product).filter(Product.sku == sku).first()
    warehouse = db.query(Warehouse).filter(Warehouse.code == warehouse_code).first()
    if not product or not warehouse:
        return (0.0, 0.0)
    wp = (
        db.query(WarehouseProduct)
        .filter(
            WarehouseProduct.warehouse_id == warehouse.id,
            WarehouseProduct.product_id == product.id,
        )
        .first()
    )
    if not wp:
        return (0.0, 0.0)
    haul = float(cast(int, getattr(wp, "haulage_buffer_weeks", 0)) or 0)
    stock = float(cast(int, getattr(wp, "stocking_buffer_weeks", 0)) or 0)
    return (haul, stock)


def get_stock_position_breakdown(
    db: Session,
    plan_run_id: int,
    horizon_weeks: int = 52,
    warehouse_code: str | None = None,
    sku: str | None = None,
    product_family: str | None = None,
    breach_only: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    For each (sku, warehouse_code) in scope for this plan run, compute:
    - current stock inputs (on_hand, avg_weekly_demand)
    - policy (target_weeks, safety_stock, lead time components)
    - derived: effective_lead_time_weeks, safety_stock_units, reorder_point_units,
      target_stock_units, next_breach_week_start, recommended_order_week_start,
      recommended_order_qty (rounded MOQ/increment).
    """
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        return []
    current_week = cast(date, run.plan_start_week_start)

    # Scope: distinct (sku, warehouse_code) from projected_inventory for this run
    q = (
        db.query(ProjectedInventory.sku, ProjectedInventory.warehouse_code)
        .filter(ProjectedInventory.plan_run_id == plan_run_id)
        .distinct()
    )
    if warehouse_code:
        q = q.filter(ProjectedInventory.warehouse_code == warehouse_code)
    if sku:
        q = q.filter(ProjectedInventory.sku == sku)
    keys = [(r.sku, r.warehouse_code) for r in q.all()]
    if not keys:
        return []

    if product_family:
        rows = (
            db.query(Product.sku, Product.product_family)
            .filter(Product.sku.in_([k[0] for k in keys]))
            .all()
        )
        product_families = {r[0]: (r[1] or "") for r in rows}
        keys = [k for k in keys if (product_families.get(k[0]) or "") == product_family]
    if limit is not None and limit > 0:
        keys = keys[:limit]

    # Load projected_inventory for this run, ordered by week, per (sku, wh)
    proj_rows = (
        db.query(ProjectedInventory)
        .filter(
            ProjectedInventory.plan_run_id == plan_run_id,
            ProjectedInventory.week_start >= current_week,
        )
        .order_by(ProjectedInventory.sku, ProjectedInventory.warehouse_code, ProjectedInventory.week_start)
        .all()
    )
    proj_by_key: dict[tuple[str, str], list[ProjectedInventory]] = {}
    for r in proj_rows:
        k = (cast(str, r.sku), cast(str, r.warehouse_code))
        if k not in keys:
            continue
        proj_by_key.setdefault(k, []).append(r)

    # Planned orders for arrival overlay (week_start = order week; arrival = week_start + lead_time)
    planned = (
        db.query(PlannedOrder)
        .filter(
            PlannedOrder.plan_run_id == plan_run_id,
            PlannedOrder.week_start >= current_week,
        )
        .all()
    )
    planned_by_key_week: dict[tuple[str, str, date], Decimal] = {}
    for po in planned:
        k = (cast(str, po.sku), cast(str, po.warehouse_code))
        if k not in keys:
            continue
        w = cast(date, po.week_start)
        planned_by_key_week[(k[0], k[1], w)] = cast(Decimal, po.order_qty)

    policies = {
        (cast(str, p.sku), cast(str, p.warehouse_code)): p
        for p in db.query(PlanningPolicy).filter(
            PlanningPolicy.sku.in_([k[0] for k in keys]),
            PlanningPolicy.warehouse_code.in_([k[1] for k in keys]),
        ).all()
    }

    result: list[dict[str, Any]] = []
    for (sku_val, wh_code) in keys:
        policy = policies.get((sku_val, wh_code))
        if not policy:
            continue
        forecast_window = int(cast(int, getattr(policy, "forecast_window_weeks", 8)) or 8)
        from_week = current_week - timedelta(days=forecast_window * 7)
        avg_demand = _get_avg_weekly_demand(
            db, plan_run_id, sku_val, wh_code, from_week, forecast_window
        )
        if avg_demand <= 0:
            from_week = current_week - timedelta(days=8 * 7)
            avg_demand = _get_avg_weekly_demand(
                db, plan_run_id, sku_val, wh_code, from_week, 8
            )

        snapshot_week, on_hand = _get_on_hand(db, sku_val, wh_code, current_week)
        supplier_lt, moq_units, pack_units = _get_supplier_lead_time_and_pack(db, sku_val, wh_code)
        haul_buf, stock_buf = _get_haulage_stocking_buffer_weeks(db, sku_val, wh_code)
        lt_haul = float(cast(Decimal, getattr(policy, "lead_time_haulage_weeks", None)) or 0)
        lt_put = float(cast(Decimal, getattr(policy, "lead_time_putaway_weeks", None)) or 0)
        effective_lead_time_weeks = max(
            0,
            math.ceil(supplier_lt + haul_buf + stock_buf + lt_haul + lt_put),
        )
        if effective_lead_time_weeks == 0 and (lt_haul or lt_put):
            effective_lead_time_weeks = max(0, math.ceil(lt_haul + lt_put))

        safety_method = cast(
            SafetyStockMethod | None,
            getattr(policy, "safety_stock_method", None),
        ) or SafetyStockMethod.WEEKS
        safety_weeks = float(cast(Decimal, getattr(policy, "safety_stock_weeks", None)) or 0)
        if safety_method == SafetyStockMethod.WEEKS and avg_demand > 0:
            safety_stock_units = float(avg_demand) * safety_weeks
        else:
            safety_stock_units = 0.0
        target_weeks = float(cast(Decimal, getattr(policy, "target_weeks", None)) or 4)
        avg_f = float(avg_demand)
        reorder_point_units = effective_lead_time_weeks * avg_f + safety_stock_units
        target_stock_units = target_weeks * avg_f + safety_stock_units

        projections = proj_by_key.get((sku_val, wh_code), [])
        next_breach_week_start: date | None = None
        projected_qty_at_breach: float | None = None
        for proj in projections:
            qty = float(cast(Decimal, proj.projected_qty))
            if qty < reorder_point_units:
                next_breach_week_start = cast(date, proj.week_start)
                projected_qty_at_breach = qty
                break

        recommended_order_week_start: date | None = None
        recommended_order_qty: float = 0.0
        projected_qty_at_arrival: float | None = None
        if next_breach_week_start and avg_f > 0 and effective_lead_time_weeks >= 0:
            # Latest order week so that arrival is before breach: go back lead_time weeks from breach
            latest_order_week = next_breach_week_start - timedelta(days=7 * effective_lead_time_weeks)
            latest_order_week = _monday_before(latest_order_week)
            order_week = max(current_week, latest_order_week)
            if order_week <= next_breach_week_start:
                arrival_week = order_week
                for _ in range(effective_lead_time_weeks):
                    arrival_week = _next_monday(arrival_week)
                for proj in projections:
                    if cast(date, proj.week_start) == arrival_week:
                        projected_qty_at_arrival = float(cast(Decimal, proj.projected_qty))
                        break
                if projected_qty_at_arrival is None:
                    projected_qty_at_arrival = 0.0
                shortfall = max(target_stock_units - projected_qty_at_arrival, 0)
                recommended_order_qty = _round_to_moq_and_increment(
                    shortfall, moq_units, pack_units
                )
                recommended_order_week_start = order_week

        if breach_only and next_breach_week_start is None:
            continue

        result.append({
            "plan_run_id": plan_run_id,
            "sku": sku_val,
            "warehouse_code": wh_code,
            "current_week_start": current_week.isoformat(),
            "on_hand_qty": str(on_hand),
            "on_hand_snapshot_week": snapshot_week.isoformat() if snapshot_week else None,
            "avg_weekly_demand": str(avg_demand),
            "forecast_window_weeks": forecast_window,
            "target_weeks": target_weeks,
            "safety_stock_weeks": safety_weeks,
            "safety_stock_method": getattr(safety_method, "value", str(safety_method)),
            "safety_stock_units": round(safety_stock_units, 4),
            "supplier_lead_time_weeks": supplier_lt,
            "haulage_buffer_weeks": haul_buf,
            "stocking_buffer_weeks": stock_buf,
            "effective_lead_time_weeks": effective_lead_time_weeks,
            "reorder_point_units": round(reorder_point_units, 4),
            "target_stock_units": round(target_stock_units, 4),
            "next_breach_week_start": next_breach_week_start.isoformat() if next_breach_week_start else None,
            "projected_qty_at_breach": round(projected_qty_at_breach, 4) if projected_qty_at_breach is not None else None,
            "recommended_order_week_start": recommended_order_week_start.isoformat() if recommended_order_week_start else None,
            "recommended_order_qty": round(recommended_order_qty, 4),
            "projected_qty_at_arrival": round(projected_qty_at_arrival, 4) if projected_qty_at_arrival is not None else None,
            "moq_units": moq_units,
            "pack_size_units": pack_units,
            "mode": getattr(getattr(policy, "mode", None), "value", None) or "WOS_TARGET",
        })
    return result


def get_rolling_stock_position(
    db: Session,
    plan_run_id: int,
    warehouse_code: str,
    sku: str,
    weeks: int = 12,
) -> list[dict[str, Any]]:
    """
    Rolling 12-week (or N-week) stock position: projected_inventory rows (opening/receipts/demand/closing)
    plus planned_orders overlay for the selected sku x warehouse.
    """
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        return []
    current_week = cast(date, run.plan_start_week_start)

    proj = (
        db.query(ProjectedInventory)
        .filter(
            ProjectedInventory.plan_run_id == plan_run_id,
            ProjectedInventory.sku == sku,
            ProjectedInventory.warehouse_code == warehouse_code,
            ProjectedInventory.week_start >= current_week,
        )
        .order_by(ProjectedInventory.week_start)
        .limit(weeks)
        .all()
    )
    planned = (
        db.query(PlannedOrder)
        .filter(
            PlannedOrder.plan_run_id == plan_run_id,
            PlannedOrder.sku == sku,
            PlannedOrder.warehouse_code == warehouse_code,
            PlannedOrder.week_start >= current_week,
        )
        .all()
    )
    planned_by_week = {cast(date, po.week_start): cast(Decimal, po.order_qty) for po in planned}

    out: list[dict[str, Any]] = []
    for r in proj:
        w = cast(date, r.week_start)
        order_qty = planned_by_week.get(w)
        out.append({
            "week_start": w.isoformat(),
            "opening_qty": str(r.start_qty),
            "receipts_qty": str(r.receipts_qty),
            "demand_qty": str(r.demand_qty),
            "closing_qty": str(r.projected_qty),
            "weeks_of_cover": float(cast(Decimal, r.weeks_of_cover)) if getattr(r, "weeks_of_cover", None) is not None else None,
            "stockout": bool(r.stockout),
            "planned_order_qty": str(order_qty) if order_qty is not None else None,
        })
    return out
