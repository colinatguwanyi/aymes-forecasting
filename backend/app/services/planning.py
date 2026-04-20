"""
Weekly supply planning logic (corrected):
- Starting snapshot: max(week_start) where week_start <= run_week per (sku, warehouse).
- Forecast: trailing mean over last forecast_window_weeks of history (week_start <= run_week only).
- Project: from snapshot week forward; end_qty = start_qty + receipts_qty - demand_qty.
- WOS_TARGET: order to reach target weeks of cover.
- ROP: order_qty = ROP - position when position < ROP; ROP = (avg_weekly_demand * lt_weeks_int) + safety_stock_qty.
- Lead time: ceil(sum(components)) weeks to arrival.
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    DemandActual,
    DemandType,
    InventorySnapshotWeekly,
    PlanRunDemandInputWeekly,
    PlannedOrder,
    PlannedOrderOverrideWeekly,
    PlanRun,
    PlanningMode,
    PlanningPolicy,
    Product,
    ProjectedInventory,
    Receipt,
    SafetyStockMethod,
    Warehouse,
)
from app.services.time_bucketing import week_start_for_date

logger = logging.getLogger(__name__)


def _monday_before(d: date) -> date:
    """Return Monday of the week containing d (ISO week)."""
    return d - timedelta(days=d.weekday())


def _next_monday(d: date) -> date:
    return _monday_before(d) + timedelta(days=7)


def _demand_inputs_for_run(
    db: Session,
    plan_run_id: int,
    from_week: date,
    to_week: date,
) -> dict[tuple[date, str, str], Decimal]:
    """Load plan_run_demand_inputs_weekly for run and range; return (week_start, sku, warehouse_code) -> demand_qty."""
    from app.services.demand_resolver import resolve_demand_for_run

    rows = (
        db.query(PlanRunDemandInputWeekly)
        .filter(
            PlanRunDemandInputWeekly.plan_run_id == plan_run_id,
            PlanRunDemandInputWeekly.week_start >= from_week,
            PlanRunDemandInputWeekly.week_start <= to_week,
        )
        .all()
    )
    if not rows:
        resolve_demand_for_run(db, plan_run_id, from_week, to_week, recompute_non_frozen_only=False)
        db.flush()
        rows = (
            db.query(PlanRunDemandInputWeekly)
            .filter(
                PlanRunDemandInputWeekly.plan_run_id == plan_run_id,
                PlanRunDemandInputWeekly.week_start >= from_week,
                PlanRunDemandInputWeekly.week_start <= to_week,
            )
            .all()
        )
    out: dict[tuple[date, str, str], Decimal] = {}
    for r in rows:
        out[(cast(date, r.week_start), cast(str, r.sku), cast(str, r.warehouse_code))] = cast(Decimal, r.demand_qty)
    return out


class AllWarehousesSkippedError(Exception):
    """Raised when run_plan skips all warehouses due to readiness failures."""

    def __init__(self, skipped_warehouses: list[dict[str, Any]]) -> None:
        self.skipped_warehouses = skipped_warehouses
        super().__init__(
            "All warehouses skipped: " + "; ".join(
                f"{s['warehouse_code']}: {', '.join(s['blockers'])}" for s in skipped_warehouses
            )
        )


def run_plan(
    db: Session,
    scenario_name: str,
    run_at: date | None = None,
    demand_source: str = "actuals",
    freeze_weeks: int = 4,
    created_by: str | None = None,
    notes: str | None = None,
    warehouses_scope: list[str] | None = None,
) -> PlanRun:
    if run_at is None:
        run_at = date.today()
    run_week = _monday_before(run_at)

    from app.services.warehouse_readiness import check_planning_readiness

    readiness = check_planning_readiness(db, demand_source=demand_source)
    readiness_by_wh: dict[str, dict[str, Any]] = {r["warehouse_code"]: r for r in readiness}

    # Determine target warehouses
    if warehouses_scope is not None and len(warehouses_scope) > 0:
        target_warehouses = [w.strip() for w in warehouses_scope if w and w.strip()]
    else:
        # Legacy: all warehouses present in planning_policies
        target_warehouses = list(
            {r[0] for r in db.query(PlanningPolicy.warehouse_code).distinct().all() if r[0]}
        )

    # Check readiness per target warehouse; collect skipped
    skipped_warehouses: list[dict[str, Any]] = []
    ready_warehouses: list[str] = []
    for wh in target_warehouses:
        r = readiness_by_wh.get(wh)
        if r and r.get("ready"):
            ready_warehouses.append(wh)
        else:
            blockers = r.get("blockers", []) if r else [f"Warehouse {wh} not in readiness check"]
            skipped_warehouses.append({"warehouse_code": wh, "blockers": blockers})

    if not ready_warehouses and target_warehouses:
        raise AllWarehousesSkippedError(skipped_warehouses)

    # Use ready_warehouses for filtering; if legacy and no explicit scope, use all from policies
    scope_warehouses = ready_warehouses if ready_warehouses else target_warehouses

    # 1) Starting snapshot per (sku, warehouse): max(week_start) where week_start <= run_week
    # Filter by scope_warehouses
    inv_q = db.query(InventorySnapshotWeekly).filter(InventorySnapshotWeekly.week_start <= run_week)
    if scope_warehouses:
        inv_q = inv_q.filter(InventorySnapshotWeekly.warehouse_code.in_(scope_warehouses))
    all_inv = inv_q.all()
    latest_week_per_key: dict[tuple[str, str], date] = {}
    starting_inv: dict[tuple[str, str], tuple[date, Decimal]] = {}
    for row in all_inv:
        sku_val = cast(str, row.sku)
        wh_val = cast(str, row.warehouse_code)
        key = (sku_val, wh_val)
        ws = cast(date, row.week_start)
        qty_val = cast(Decimal | None, row.on_hand_qty) or Decimal("0")
        src = (getattr(row, "source_type", None) or "").strip().lower()
        if key not in latest_week_per_key or ws > latest_week_per_key[key]:
            latest_week_per_key[key] = ws
            starting_inv[key] = (ws, qty_val)
        elif ws == latest_week_per_key[key] and src == "soh":
            starting_inv[key] = (ws, qty_val)

    # 2) Receipts: (week_start, sku, warehouse_code) -> qty (sum)
    receipts_rows = db.query(Receipt).all()
    receipts: defaultdict[tuple[date, str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    for r in receipts_rows:
        receipts[(cast(date, r.week_start), cast(str, r.sku), cast(str, r.warehouse_code))] += cast(
            Decimal, r.qty
        )

    # 3) Demand actuals: (week_start, sku, warehouse_code, demand_type) -> qty (sum)
    def _to_demand_type(val: Any) -> DemandType | None:
        """Safely resolve to DemandType; use DemandType.ADJUSTMENT for ADJUSTMENT."""
        if val is None:
            return None
        if isinstance(val, DemandType):
            return val
        s = str(val).strip().upper()
        if s == "CUSTOMER":
            return DemandType.CUSTOMER
        if s == "SAMPLES":
            return DemandType.SAMPLES
        if s == "ADJUSTMENT":
            return DemandType.ADJUSTMENT
        return None

    demand_rows = db.query(DemandActual).all()
    demand_by_type: defaultdict[tuple[date, str, str, DemandType], Decimal] = defaultdict(
        lambda: Decimal("0")
    )
    for d in demand_rows:
        dt = _to_demand_type(getattr(d, "demand_type", None))
        if dt is None:
            continue
        demand_by_type[
            (
                cast(date, d.week_start),
                cast(str, d.sku),
                cast(str, d.warehouse_code),
                dt,
            )
        ] += cast(Decimal, d.qty)

    policies = db.query(PlanningPolicy).all()
    if scope_warehouses:
        policies = [p for p in policies if cast(str, p.warehouse_code) in scope_warehouses]
    policy_by_key: dict[tuple[str, str], PlanningPolicy] = {
        (cast(str, p.sku), cast(str, p.warehouse_code)): p for p in policies
    }

    # 4) Forecast: history_weeks = demand where week_start <= run_week; trailing mean = last forecast_window_weeks
    forecast_customer: dict[tuple[str, str], Decimal] = {}
    forecast_samples: dict[tuple[str, str], Decimal] = {}
    for (sku, wh_code), policy in policy_by_key.items():
        n = cast(int | None, policy.forecast_window_weeks) or 8
        history_c: list[tuple[date, Decimal]] = []
        history_s: list[tuple[date, Decimal]] = []
        for (w, s, wc, dt), qty in demand_by_type.items():
            if s != sku or wc != wh_code:
                continue
            if w > run_week:
                continue
            if dt == DemandType.CUSTOMER:
                history_c.append((w, qty))
            elif dt == DemandType.SAMPLES and wh_code != "AAH":
                history_s.append((w, qty))  # AAH never uses SAMPLES
        history_c.sort(key=lambda x: x[0])
        history_s.sort(key=lambda x: x[0])
        last_n_c = history_c[-n:] if len(history_c) >= n else history_c
        last_n_s = history_s[-n:] if len(history_s) >= n else history_s
        avg_c = sum(float(q) for _, q in last_n_c) / len(last_n_c) if last_n_c else Decimal("0")
        avg_s = sum(float(q) for _, q in last_n_s) / len(last_n_s) if last_n_s else Decimal("0")
        forecast_customer[(sku, wh_code)] = Decimal(str(round(avg_c, 4)))
        forecast_samples[(sku, wh_code)] = Decimal(str(round(avg_s, 4)))

    plan_start_week_start = week_start_for_date(run_at)
    plan_run = PlanRun(
        scenario_name=scenario_name,
        run_at=run_at,
        created_at=run_at,
        demand_source=demand_source,
        freeze_weeks=freeze_weeks,
        plan_start_week_start=plan_start_week_start,
        created_by=created_by,
        notes=notes,
        warehouses_scope=warehouses_scope if warehouses_scope else None,
    )
    db.add(plan_run)
    db.flush()

    plan_run_id_val = int(getattr(plan_run, "id", 0))
    to_week = run_week + timedelta(days=53 * 7)
    demand_inputs = _demand_inputs_for_run(db, plan_run_id_val, run_week, to_week)

    order_overrides: dict[tuple[date, str, str], Decimal] = {}
    for o in db.query(PlannedOrderOverrideWeekly).filter(PlannedOrderOverrideWeekly.plan_run_id == plan_run.id).all():
        order_overrides[(cast(date, o.week_start), cast(str, o.sku), cast(str, o.warehouse_code))] = cast(Decimal, o.override_order_qty)

    receipts_plus_orders: defaultdict[tuple[date, str, str], Decimal] = defaultdict(
        lambda: Decimal("0")
    )
    for k, v in receipts.items():
        receipts_plus_orders[k] += v

    sku_wh_set = set(policy_by_key.keys()) | set(starting_inv.keys())
    projected_rows: list[dict[str, Any]] = []
    planned_order_rows: list[dict[str, Any]] = []

    for (sku, wh_code) in sku_wh_set:
        policy = policy_by_key.get((sku, wh_code))
        if not policy:
            continue
        start_data = starting_inv.get((sku, wh_code))
        if not start_data:
            continue
        snapshot_week, start_qty = start_data
        lt_prod = float(cast(Decimal | None, policy.lead_time_production_weeks) or 0)
        lt_slot = float(cast(Decimal | None, policy.lead_time_slot_wait_weeks) or 0)
        lt_haul = float(cast(Decimal | None, policy.lead_time_haulage_weeks) or 0)
        lt_put = float(cast(Decimal | None, policy.lead_time_putaway_weeks) or 0)
        lt_pad = float(cast(Decimal | None, policy.lead_time_padding_weeks) or 0)
        total_lt_float = lt_prod + lt_slot + lt_haul + lt_put + lt_pad
        lt_weeks_int = max(0, math.ceil(total_lt_float))
        include_samples: bool = cast(bool, getattr(policy, "include_samples", True))
        if wh_code == "AAH":
            include_samples = False  # AAH never includes SAMPLES (Sales Out = CUSTOMER only)
        fc_c: Decimal = forecast_customer.get((sku, wh_code), Decimal("0"))
        fc_s: Decimal = (
            forecast_samples.get((sku, wh_code), Decimal("0")) if include_samples else Decimal("0")
        )
        total_forecast_per_week: Decimal = fc_c + fc_s
        safety_weeks = float(cast(Decimal | None, policy.safety_stock_weeks) or 0)
        ss_method: SafetyStockMethod = cast(
            SafetyStockMethod | None, policy.safety_stock_method
        ) or SafetyStockMethod.WEEKS
        safety_stock_qty: Decimal = (
            total_forecast_per_week * Decimal(str(safety_weeks))
            if ss_method == SafetyStockMethod.WEEKS and total_forecast_per_week > 0
            else Decimal("0")
        )
        target_weeks = float(cast(Decimal | None, policy.target_weeks) or 4)
        mode: PlanningMode = cast(PlanningMode | None, policy.mode) or PlanningMode.WOS_TARGET

        inv = start_qty
        # Build projection weeks: from snapshot_week forward only (next 52 weeks)
        proj_weeks: list[date] = []
        w = snapshot_week
        for _ in range(53):
            proj_weeks.append(w)
            w = _next_monday(w)

        for w in proj_weeks:
            rec: Decimal = receipts_plus_orders.get((w, sku, wh_code), Decimal("0"))
            demand_resolved: Decimal | None = demand_inputs.get((w, sku, wh_code))
            if demand_resolved is not None:
                demand: Decimal = demand_resolved
            else:
                d_c: Decimal | None = demand_by_type.get((w, sku, wh_code, DemandType.CUSTOMER))
                d_s: Decimal | None = (
                    demand_by_type.get((w, sku, wh_code, DemandType.SAMPLES)) if include_samples else None
                )
                d_adj: Decimal = demand_by_type.get(
                    (w, sku, wh_code, DemandType.ADJUSTMENT), Decimal("0")
                )
                demand_c = d_c if d_c is not None else fc_c
                demand_s = d_s if d_s is not None else (fc_s if include_samples else Decimal("0"))
                demand = demand_c + demand_s + d_adj
            start_qty_week: Decimal = inv
            inv = inv + rec - demand
            end_qty_week: Decimal = inv

            if total_forecast_per_week > 0:
                woc: float = float(inv) / float(total_forecast_per_week)
            else:
                woc = 999.0 if inv > 0 else 0.0
            stockout: bool = inv < 0

            projected_rows.append({
                "plan_run_id": plan_run.id,
                "week_start": w,
                "sku": sku,
                "warehouse_code": wh_code,
                "start_qty": start_qty_week,
                "receipts_qty": rec,
                "demand_qty": demand,
                "projected_qty": end_qty_week,
                "weeks_of_cover": Decimal(str(round(woc, 2))),
                "stockout": stockout,
            })

            # Planned order
            order_qty: Decimal = Decimal("0")
            if mode == PlanningMode.WOS_TARGET:
                if woc < target_weeks and total_forecast_per_week > 0:
                    shortfall_weeks = target_weeks - woc
                    order_qty = Decimal(
                        str(round(shortfall_weeks * float(total_forecast_per_week), 4))
                    )
            else:
                rop: Decimal = (
                    total_forecast_per_week * Decimal(str(lt_weeks_int))
                ) + safety_stock_qty
                if inv < rop and total_forecast_per_week > 0:
                    order_qty = max(rop - inv, Decimal("0"))
                    order_qty = Decimal(str(round(float(order_qty), 4)))

            if order_qty > 0 or order_overrides.get((w, sku, wh_code)) is not None:
                order_qty_used = order_overrides.get((w, sku, wh_code))
                if order_qty_used is not None:
                    order_qty = order_qty_used
                if order_qty > 0:
                    arrival_week = w
                    for _ in range(lt_weeks_int):
                        arrival_week = _next_monday(arrival_week)
                    receipts_plus_orders[(arrival_week, sku, wh_code)] += order_qty
                planned_order_rows.append({
                    "plan_run_id": plan_run.id,
                    "week_start": w,
                    "sku": sku,
                    "warehouse_code": wh_code,
                    "order_qty": order_qty,
                    "is_frozen": False,
                })
                if lt_weeks_int == 0:
                    inv += order_qty
                    end_qty_week = inv
                    woc = (
                        float(inv) / float(total_forecast_per_week)
                        if total_forecast_per_week > 0
                        else 999.0
                    )
                    last_proj: dict[str, Any] = projected_rows[-1]
                    last_proj["projected_qty"] = inv
                    last_proj["weeks_of_cover"] = Decimal(str(round(woc, 2)))
                    last_proj["stockout"] = inv < 0

    # Safety guard: all SKUs and warehouses in outputs must exist in products/warehouses
    output_skus = {r["sku"] for r in projected_rows} | {r["sku"] for r in planned_order_rows}
    output_whs = {r["warehouse_code"] for r in projected_rows} | {r["warehouse_code"] for r in planned_order_rows}
    demo_skus = {"SKU1", "SKU2", "SKU3", "SKU4", "SKU001", "SKU002", "SKU003", "SKU004"}
    if output_skus or output_whs:
        existing_skus = {r[0] for r in db.query(Product.sku).filter(Product.sku.in_(output_skus)).all() if r[0]}
        existing_whs = {r[0] for r in db.query(Warehouse.code).filter(Warehouse.code.in_(output_whs)).all() if r[0]}
        missing_skus = output_skus - existing_skus
        missing_whs = output_whs - existing_whs
        if missing_skus or missing_whs:
            raise ValueError(
                f"Planning outputs reference unknown SKUs ({missing_skus}) or warehouses ({missing_whs}). "
                "Ensure products and warehouses exist before running a plan."
            )
        if not settings.allow_demo_data and (output_skus & demo_skus):
            raise ValueError(
                "Demo data disabled: outputs contain demo SKUs (SKU1/SKU2/SKU3/SKU4 or SKU001-004). "
                "Set ALLOW_DEMO_DATA=true for dev, or load real data via Imports and remove demo products. "
                "See docs/FAKE_DATA_ROOT_CAUSE_REPORT.md."
            )

    for r in projected_rows:
        db.add(ProjectedInventory(**r))
    for r in planned_order_rows:
        db.add(PlannedOrder(**r))

    # Record progress_meta with per-warehouse explainability
    planned_wh = list({r["warehouse_code"] for r in projected_rows})
    warehouses_planned_detail: list[dict[str, Any]] = []
    for wh in planned_wh:
        r = readiness_by_wh.get(wh, {})
        policy_pairs = sum(1 for (_, w) in policy_by_key if w == wh)
        start_pairs = sum(1 for (_, w) in starting_inv if w == wh)
        skus_planned = len({r["sku"] for r in projected_rows if r["warehouse_code"] == wh})
        warehouses_planned_detail.append({
            "warehouse_code": wh,
            "latest_soh_week_start": r.get("soh_latest_week"),
            "latest_demand_week_start": r.get("demand_latest_week"),
            "policy_pairs_count": policy_pairs,
            "starting_inv_pairs_count": start_pairs,
            "overlap_pairs_count": r.get("overlap_pairs", 0),
            "skus_planned": skus_planned,
        })
    plan_run.progress_meta = {
        "demand_source": demand_source,
        "plan_start_week_start": plan_start_week_start.isoformat() if plan_start_week_start else None,
        "warehouses_planned": planned_wh,
        "warehouses_planned_detail": warehouses_planned_detail,
        "warehouses_skipped": [s["warehouse_code"] for s in skipped_warehouses],
        "projected_inventory_rows_written": len(projected_rows),
        "planned_orders_rows_written": len(planned_order_rows),
        "skipped_warehouses_detail": skipped_warehouses,
    }

    db.commit()
    db.refresh(plan_run)
    return plan_run
