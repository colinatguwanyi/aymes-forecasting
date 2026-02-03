"""
Weekly supply planning logic:
- Baseline demand forecast: trailing mean over forecast_window_weeks for CUSTOMER; SAMPLES from trailing mean or overrides.
- Project inventory: end = start + receipts - demand.
- Weeks of cover, stockout flags.
- Planned orders: WOS_TARGET (order to reach target weeks) or ROP (order when below ROP).
"""
from __future__ import annotations
import logging
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


def _weeks_between(start: date, end: date) -> int:
    """Number of full weeks (Monday boundaries) between start and end (inclusive of end week)."""
    m_start = _monday_before(start)
    m_end = _monday_before(end)
    return max(0, (m_end - m_start).days // 7 + 1)


def _next_monday(d: date) -> date:
    return _monday_before(d) + timedelta(days=7)


def run_plan(db: Session, scenario_name: str, run_at: date | None = None) -> PlanRun:
    if run_at is None:
        run_at = date.today()

    # Latest inventory snapshot per (sku, warehouse) - use latest week_start
    inv_q = (
        db.query(InventorySnapshotWeekly.week_start, InventorySnapshotWeekly.sku, InventorySnapshotWeekly.warehouse_code, InventorySnapshotWeekly.on_hand_qty)
        .distinct(InventorySnapshotWeekly.sku, InventorySnapshotWeekly.warehouse_code)
        .order_by(InventorySnapshotWeekly.sku, InventorySnapshotWeekly.warehouse_code, InventorySnapshotWeekly.week_start.desc())
    )
    # Simpler: get max week per sku/wh then lookup
    all_inv = db.query(InventorySnapshotWeekly).all()
    latest_week = {}
    for row in all_inv:
        key = (row.sku, row.warehouse_code)
        if key not in latest_week or row.week_start > latest_week[key]:
            latest_week[key] = row.week_start
    starting_inv = {}
    for row in all_inv:
        key = (row.sku, row.warehouse_code)
        if row.week_start == latest_week[key]:
            starting_inv[key] = row.on_hand_qty

    # Receipts by (week_start, sku, warehouse_code) -> qty (sum if multiple)
    receipts_rows = db.query(Receipt).all()
    receipts = defaultdict(lambda: Decimal("0"))
    for r in receipts_rows:
        receipts[(r.week_start, r.sku, r.warehouse_code)] += r.qty

    # Demand actuals by (week_start, sku, warehouse_code, demand_type) -> qty
    demand_rows = db.query(DemandActual).all()
    demand_by_type = defaultdict(lambda: Decimal("0"))
    for d in demand_rows:
        demand_by_type[(d.week_start, d.sku, d.warehouse_code, d.demand_type)] += d.qty

    # All (sku, warehouse_code) from policies
    policies = db.query(PlanningPolicy).all()
    policy_by_key = {(p.sku, p.warehouse_code): p for p in policies}

    # Build set of week_starts we need (from min start to max needed for projection)
    min_week = min(latest_week.values()) if latest_week else run_at
    all_weeks_set = set()
    for (w_start, sku, wh) in receipts:
        all_weeks_set.add(w_start)
    for (w_start, sku, wh, _) in demand_by_type:
        all_weeks_set.add(w_start)
    all_weeks = sorted(all_weeks_set)
    if not all_weeks:
        # No data: use run_at and 52 weeks forward
        start_monday = _monday_before(run_at)
        all_weeks = [start_monday + timedelta(days=7 * i) for i in range(53)]
    else:
        max_week = max(all_weeks)
        w = _next_monday(max_week)
        for _ in range(52):
            all_weeks.append(w)
            w = _next_monday(w)

    # Demand forecast: trailing mean per (sku, warehouse_code) for CUSTOMER and SAMPLES
    forecast_customer = {}
    forecast_samples = {}
    for (sku, wh_code) in policy_by_key:
        policy = policy_by_key[(sku, wh_code)]
        n = policy.forecast_window_weeks or 8
        customer_vals = []
        sample_vals = []
        for w in all_weeks:
            c = demand_by_type.get((w, sku, wh_code, DemandType.CUSTOMER), Decimal("0"))
            s = demand_by_type.get((w, sku, wh_code, DemandType.SAMPLES), Decimal("0"))
            customer_vals.append((w, float(c)))
            sample_vals.append((w, float(s)))
        if len(customer_vals) >= n:
            customer_vals = customer_vals[-n:]
            sample_vals = sample_vals[-n:]
        avg_c = sum(v for _, v in customer_vals) / len(customer_vals) if customer_vals else 0
        avg_s = sum(v for _, v in sample_vals) / len(sample_vals) if sample_vals else 0
        forecast_customer[(sku, wh_code)] = Decimal(str(round(avg_c, 4)))
        forecast_samples[(sku, wh_code)] = Decimal(str(round(avg_s, 4)))

    # Create plan run
    plan_run = PlanRun(scenario_name=scenario_name, run_at=run_at, created_at=run_at)
    db.add(plan_run)
    db.flush()

    # Mutable receipts: base receipts + planned order arrivals (updated as we place orders)
    receipts_plus_orders = defaultdict(lambda: Decimal("0"))
    for k, v in receipts.items():
        receipts_plus_orders[k] += v

    # Project per (sku, warehouse_code) week by week
    sku_wh_set = set(policy_by_key.keys()) | set(starting_inv.keys())
    projected_rows = []
    planned_order_rows = []

    for (sku, wh_code) in sku_wh_set:
        policy = policy_by_key.get((sku, wh_code))
        if not policy:
            continue
        start_qty = starting_inv.get((sku, wh_code), Decimal("0"))
        total_lt_weeks = float(
            (policy.lead_time_production_weeks or 0)
            + (policy.lead_time_slot_wait_weeks or 0)
            + (policy.lead_time_haulage_weeks or 0)
            + (policy.lead_time_putaway_weeks or 0)
            + (policy.lead_time_padding_weeks or 0)
        )
        fc_c = forecast_customer.get((sku, wh_code), Decimal("0"))
        fc_s = forecast_samples.get((sku, wh_code), Decimal("0"))
        total_forecast_per_week = fc_c + fc_s
        safety_weeks = float(policy.safety_stock_weeks or 0)
        target_weeks = float(policy.target_weeks or 4)
        mode = policy.mode or PlanningMode.WOS_TARGET

        inv = start_qty

        for w in all_weeks:
            rec = receipts_plus_orders.get((w, sku, wh_code), Decimal("0"))
            # Demand: use actuals if present for that week, else forecast
            d_c = demand_by_type.get((w, sku, wh_code, DemandType.CUSTOMER))
            d_s = demand_by_type.get((w, sku, wh_code, DemandType.SAMPLES))
            d_adj = demand_by_type.get((w, sku, wh_code, DemandType.ADJUSTMENT), Decimal("0"))
            if d_c is not None:
                demand_c = d_c
            else:
                demand_c = fc_c
            if d_s is not None:
                demand_s = d_s
            else:
                demand_s = fc_s
            demand = demand_c + demand_s + d_adj
            inv = inv + rec - demand

            # Weeks of cover
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
                "projected_qty": inv,
                "weeks_of_cover": Decimal(str(round(woc, 2))),
                "stockout": stockout,
            })

            # Planned order: order placed this week arrives in total_lt_weeks
            order_qty = Decimal("0")
            if mode == PlanningMode.WOS_TARGET:
                if woc < target_weeks and total_forecast_per_week > 0:
                    shortfall_weeks = target_weeks - woc
                    order_qty = Decimal(str(round(float(shortfall_weeks * total_forecast_per_week), 4)))
            else:
                demand_during_lt = total_forecast_per_week * Decimal(str(total_lt_weeks))
                safety_stock = total_forecast_per_week * Decimal(str(safety_weeks)) if policy.safety_stock_method == SafetyStockMethod.WEEKS else Decimal("0")
                rop = demand_during_lt + safety_stock
                if inv < rop and total_forecast_per_week > 0:
                    order_qty = rop - inv + (total_forecast_per_week * Decimal(str(total_lt_weeks)))
                    order_qty = max(order_qty, Decimal("0"))
                    order_qty = Decimal(str(round(float(order_qty), 4)))

            if order_qty > 0:
                arrival_week = w
                for _ in range(int(total_lt_weeks)):
                    arrival_week = _next_monday(arrival_week)
                receipts_plus_orders[(arrival_week, sku, wh_code)] += order_qty
                planned_order_rows.append({
                    "plan_run_id": plan_run.id,
                    "week_start": w,
                    "sku": sku,
                    "warehouse_code": wh_code,
                    "order_qty": order_qty,
                })
                if total_lt_weeks == 0:
                    inv += order_qty
                    woc = float(inv) / float(total_forecast_per_week) if total_forecast_per_week > 0 else 999.0
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
