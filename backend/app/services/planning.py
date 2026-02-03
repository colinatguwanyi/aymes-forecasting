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

from sqlalchemy.orm import Session

from app.models import (
    DemandActual,
    DemandType,
    InventorySnapshotWeekly,
    PlannedOrder,
    PlanRun,
    PlanningMode,
    PlanningPolicy,
    ProjectedInventory,
    Receipt,
    SafetyStockMethod,
)

logger = logging.getLogger(__name__)


def _monday_before(d: date) -> date:
    """Return Monday of the week containing d (ISO week)."""
    return d - timedelta(days=d.weekday())


def _next_monday(d: date) -> date:
    return _monday_before(d) + timedelta(days=7)


def run_plan(db: Session, scenario_name: str, run_at: date | None = None) -> PlanRun:
    if run_at is None:
        run_at = date.today()
    run_week = _monday_before(run_at)

    # 1) Starting snapshot per (sku, warehouse): max(week_start) where week_start <= run_week
    all_inv = (
        db.query(InventorySnapshotWeekly)
        .filter(InventorySnapshotWeekly.week_start <= run_week)
        .all()
    )
    latest_week_per_key: dict[tuple[str, str], date] = {}
    starting_inv: dict[tuple[str, str], tuple[date, Decimal]] = {}
    for row in all_inv:
        key = (row.sku, row.warehouse_code)
        if key not in latest_week_per_key or row.week_start > latest_week_per_key[key]:
            latest_week_per_key[key] = row.week_start
            starting_inv[key] = (row.week_start, row.on_hand_qty)
        elif row.week_start == latest_week_per_key[key]:
            starting_inv[key] = (row.week_start, row.on_hand_qty)

    # 2) Receipts: (week_start, sku, warehouse_code) -> qty (sum)
    receipts_rows = db.query(Receipt).all()
    receipts: defaultdict[tuple[date, str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    for r in receipts_rows:
        receipts[(r.week_start, r.sku, r.warehouse_code)] += r.qty

    # 3) Demand actuals: (week_start, sku, warehouse_code, demand_type) -> qty (sum)
    demand_rows = db.query(DemandActual).all()
    demand_by_type: defaultdict[tuple[date, str, str, DemandType], Decimal] = defaultdict(
        lambda: Decimal("0")
    )
    for d in demand_rows:
        demand_by_type[(d.week_start, d.sku, d.warehouse_code, d.demand_type)] += d.qty

    policies = db.query(PlanningPolicy).all()
    policy_by_key = {(p.sku, p.warehouse_code): p for p in policies}

    # 4) Forecast: history_weeks = demand where week_start <= run_week; trailing mean = last forecast_window_weeks
    forecast_customer: dict[tuple[str, str], Decimal] = {}
    forecast_samples: dict[tuple[str, str], Decimal] = {}
    for (sku, wh_code), policy in policy_by_key.items():
        n = policy.forecast_window_weeks or 8
        history_c: list[tuple[date, Decimal]] = []
        history_s: list[tuple[date, Decimal]] = []
        for (w, s, wc, dt), qty in demand_by_type.items():
            if s != sku or wc != wh_code:
                continue
            if w > run_week:
                continue
            if dt == DemandType.CUSTOMER:
                history_c.append((w, qty))
            elif dt == DemandType.SAMPLES:
                history_s.append((w, qty))
        history_c.sort(key=lambda x: x[0])
        history_s.sort(key=lambda x: x[0])
        last_n_c = history_c[-n:] if len(history_c) >= n else history_c
        last_n_s = history_s[-n:] if len(history_s) >= n else history_s
        avg_c = sum(float(q) for _, q in last_n_c) / len(last_n_c) if last_n_c else Decimal("0")
        avg_s = sum(float(q) for _, q in last_n_s) / len(last_n_s) if last_n_s else Decimal("0")
        forecast_customer[(sku, wh_code)] = Decimal(str(round(avg_c, 4)))
        forecast_samples[(sku, wh_code)] = Decimal(str(round(avg_s, 4)))

    plan_run = PlanRun(scenario_name=scenario_name, run_at=run_at, created_at=run_at)
    db.add(plan_run)
    db.flush()

    receipts_plus_orders: defaultdict[tuple[date, str, str], Decimal] = defaultdict(
        lambda: Decimal("0")
    )
    for k, v in receipts.items():
        receipts_plus_orders[k] += v

    sku_wh_set = set(policy_by_key.keys()) | set(starting_inv.keys())
    projected_rows: list[dict] = []
    planned_order_rows: list[dict] = []

    for (sku, wh_code) in sku_wh_set:
        policy = policy_by_key.get((sku, wh_code))
        if not policy:
            continue
        start_data = starting_inv.get((sku, wh_code))
        if not start_data:
            continue
        snapshot_week, start_qty = start_data
        total_lt_float = float(
            (policy.lead_time_production_weeks or 0)
            + (policy.lead_time_slot_wait_weeks or 0)
            + (policy.lead_time_haulage_weeks or 0)
            + (policy.lead_time_putaway_weeks or 0)
            + (policy.lead_time_padding_weeks or 0)
        )
        lt_weeks_int = max(0, math.ceil(total_lt_float))
        include_samples = getattr(policy, "include_samples", True)
        fc_c = forecast_customer.get((sku, wh_code), Decimal("0"))
        fc_s = forecast_samples.get((sku, wh_code), Decimal("0")) if include_samples else Decimal("0")
        total_forecast_per_week = fc_c + fc_s
        safety_weeks = float(policy.safety_stock_weeks or 0)
        safety_stock_qty = (
            total_forecast_per_week * Decimal(str(safety_weeks))
            if policy.safety_stock_method == SafetyStockMethod.WEEKS and total_forecast_per_week > 0
            else Decimal("0")
        )
        target_weeks = float(policy.target_weeks or 4)
        mode = policy.mode or PlanningMode.WOS_TARGET

        inv = start_qty
        # Build projection weeks: from snapshot_week forward only (next 52 weeks)
        proj_weeks: list[date] = []
        w = snapshot_week
        for _ in range(53):
            proj_weeks.append(w)
            w = _next_monday(w)

        for w in proj_weeks:
            rec = receipts_plus_orders.get((w, sku, wh_code), Decimal("0"))
            d_c = demand_by_type.get((w, sku, wh_code, DemandType.CUSTOMER))
            d_s = demand_by_type.get((w, sku, wh_code, DemandType.SAMPLES)) if include_samples else None
            d_adj = demand_by_type.get((w, sku, wh_code, DemandType.ADJUSTMENT), Decimal("0"))
            demand_c = d_c if d_c is not None else fc_c
            demand_s = d_s if d_s is not None else (fc_s if include_samples else Decimal("0"))
            demand = demand_c + demand_s + d_adj
            start_qty_week = inv
            inv = inv + rec - demand
            end_qty_week = inv

            if total_forecast_per_week > 0:
                woc = float(inv) / float(total_forecast_per_week)
            else:
                woc = 999.0 if inv > 0 else 0.0
            stockout = inv < 0

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
            order_qty = Decimal("0")
            if mode == PlanningMode.WOS_TARGET:
                if woc < target_weeks and total_forecast_per_week > 0:
                    shortfall_weeks = target_weeks - woc
                    order_qty = Decimal(
                        str(round(float(shortfall_weeks * total_forecast_per_week), 4))
                    )
            else:
                rop = (total_forecast_per_week * Decimal(str(lt_weeks_int))) + safety_stock_qty
                if inv < rop and total_forecast_per_week > 0:
                    order_qty = rop - inv
                    order_qty = max(order_qty, Decimal("0"))
                    order_qty = Decimal(str(round(float(order_qty), 4)))

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
                })
                if lt_weeks_int == 0:
                    inv += order_qty
                    end_qty_week = inv
                    woc = (
                        float(inv) / float(total_forecast_per_week)
                        if total_forecast_per_week > 0
                        else 999.0
                    )
                    projected_rows[-1]["projected_qty"] = inv
                    projected_rows[-1]["weeks_of_cover"] = Decimal(str(round(woc, 2)))
                    projected_rows[-1]["stockout"] = inv < 0

    for r in projected_rows:
        db.add(ProjectedInventory(**r))
    for r in planned_order_rows:
        db.add(PlannedOrder(**r))

    db.commit()
    db.refresh(plan_run)
    return plan_run
