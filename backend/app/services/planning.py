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
        sku_val = cast(str, row.sku)
        wh_val = cast(str, row.warehouse_code)
        key = (sku_val, wh_val)
        ws = cast(date, row.week_start)
        qty_val = cast(Decimal | None, row.on_hand_qty) or Decimal("0")
        if key not in latest_week_per_key or ws > latest_week_per_key[key]:
            latest_week_per_key[key] = ws
            starting_inv[key] = (ws, qty_val)
        elif ws == latest_week_per_key[key]:
            starting_inv[key] = (ws, qty_val)

    # 2) Receipts: (week_start, sku, warehouse_code) -> qty (sum)
    receipts_rows = db.query(Receipt).all()
    receipts: defaultdict[tuple[date, str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    for r in receipts_rows:
        receipts[(cast(date, r.week_start), cast(str, r.sku), cast(str, r.warehouse_code))] += cast(
            Decimal, r.qty
        )

    # 3) Demand actuals: (week_start, sku, warehouse_code, demand_type) -> qty (sum)
    demand_rows = db.query(DemandActual).all()
    demand_by_type: defaultdict[tuple[date, str, str, DemandType], Decimal] = defaultdict(
        lambda: Decimal("0")
    )
    for d in demand_rows:
        demand_by_type[
            (
                cast(date, d.week_start),
                cast(str, d.sku),
                cast(str, d.warehouse_code),
                cast(DemandType, d.demand_type),
            )
        ] += cast(Decimal, d.qty)

    policies = db.query(PlanningPolicy).all()
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
            d_c: Decimal | None = demand_by_type.get((w, sku, wh_code, DemandType.CUSTOMER))
            d_s: Decimal | None = (
                demand_by_type.get((w, sku, wh_code, DemandType.SAMPLES)) if include_samples else None
            )
            d_adj: Decimal = demand_by_type.get(
                (w, sku, wh_code, DemandType.ADJUSTMENT), Decimal("0")
            )
            demand_c = d_c if d_c is not None else fc_c
            demand_s = d_s if d_s is not None else (fc_s if include_samples else Decimal("0"))
            demand: Decimal = demand_c + demand_s + d_adj
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
                    last_proj: dict[str, Any] = projected_rows[-1]
                    last_proj["projected_qty"] = inv
                    last_proj["weeks_of_cover"] = Decimal(str(round(woc, 2)))
                    last_proj["stockout"] = inv < 0

    for r in projected_rows:
        db.add(ProjectedInventory(**r))
    for r in planned_order_rows:
        db.add(PlannedOrder(**r))

    db.commit()
    db.refresh(plan_run)
    return plan_run
