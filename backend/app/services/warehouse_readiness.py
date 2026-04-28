"""Per-warehouse planning readiness check."""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import DemandActual, DemandType, InventorySnapshotWeekly, PlanningPolicy


def check_planning_readiness(
    db: Session,
    demand_source: str = "actuals",
    planning_mode: str = "stock_aware",
) -> list[dict[str, Any]]:
    """
    Check planning readiness per warehouse.
    Returns list of {warehouse_code, has_soh, has_demand, has_policies, overlap_pairs, ready, blockers[]}.

    - has_soh: inventory_snapshots_weekly exists for that warehouse (latest week_start)
    - has_demand: demand_actuals exists for that warehouse. AAH: CUSTOMER only (Sales Out). BLP: CUSTOMER and/or SAMPLES.
    - has_policies: planning_policies exists for that warehouse
    - overlap_pairs: count of (sku, warehouse) present in BOTH SOH and policies (and demand for actuals)
    - ready (stock_aware): has_soh && has_policies && has_demand (actuals) or has_soh && has_policies (baseline/blended)
    - ready (demand_only): SOH not required; has_policies && has_demand (actuals) or has_policies (baseline/blended)
    """
    # All distinct warehouse codes from policies, SOH, and demand
    policy_wh = {r[0] for r in db.query(PlanningPolicy.warehouse_code).distinct().all() if r[0]}
    soh_wh = {r[0] for r in db.query(InventorySnapshotWeekly.warehouse_code).distinct().all() if r[0]}
    demand_wh = {
        r[0]
        for r in db.query(DemandActual.warehouse_code)
        .filter(DemandActual.demand_type.in_([DemandType.CUSTOMER, DemandType.SAMPLES]))
        .distinct()
        .all()
        if r[0]
    }
    # AAH: CUSTOMER only (Sales Out). BLP: CUSTOMER or SAMPLES.
    all_warehouses = sorted(policy_wh | soh_wh | demand_wh)
    if not all_warehouses:
        return []

    result: list[dict[str, Any]] = []
    for wh in all_warehouses:
        # has_soh
        soh_latest = (
            db.query(func.max(InventorySnapshotWeekly.week_start))
            .filter(InventorySnapshotWeekly.warehouse_code == wh)
            .scalar()
        )
        has_soh = soh_latest is not None

        # has_demand: AAH = Sales Out (CUSTOMER only); BLP = Direct sales (CUSTOMER) or Samples (SAMPLES)
        if wh == "AAH":
            demand_latest = (
                db.query(func.max(DemandActual.week_start))
                .filter(
                    DemandActual.warehouse_code == wh,
                    DemandActual.demand_type == DemandType.CUSTOMER,
                )
                .scalar()
            )
        else:
            demand_latest = (
                db.query(func.max(DemandActual.week_start))
                .filter(
                    DemandActual.warehouse_code == wh,
                    DemandActual.demand_type.in_([DemandType.CUSTOMER, DemandType.SAMPLES]),
                )
                .scalar()
            )
        has_demand = demand_latest is not None

        # has_policies
        policy_count = db.query(PlanningPolicy).filter(PlanningPolicy.warehouse_code == wh).count()
        has_policies = policy_count > 0

        # overlap_pairs: (sku, wh) in BOTH SOH and policies
        soh_skus = {
            r[0]
            for r in db.query(InventorySnapshotWeekly.sku)
            .filter(InventorySnapshotWeekly.warehouse_code == wh)
            .distinct()
            .all()
            if r[0]
        }
        policy_skus = {
            r[0]
            for r in db.query(PlanningPolicy.sku)
            .filter(PlanningPolicy.warehouse_code == wh)
            .distinct()
            .all()
            if r[0]
        }
        overlap_soh_policy = len(soh_skus & policy_skus)

        # For actuals, demand overlap matters. AAH: CUSTOMER only (Sales Out). BLP: CUSTOMER or SAMPLES.
        if demand_source == "actuals" and has_demand:
            if wh == "AAH":
                demand_skus = {
                    r[0]
                    for r in db.query(DemandActual.sku)
                    .filter(
                        DemandActual.warehouse_code == wh,
                        DemandActual.demand_type == DemandType.CUSTOMER,
                    )
                    .distinct()
                    .all()
                    if r[0]
                }
            else:
                demand_skus = {
                    r[0]
                    for r in db.query(DemandActual.sku)
                    .filter(
                        DemandActual.warehouse_code == wh,
                        DemandActual.demand_type.in_([DemandType.CUSTOMER, DemandType.SAMPLES]),
                    )
                    .distinct()
                    .all()
                    if r[0]
                }
            overlap_pairs = len(soh_skus & policy_skus & demand_skus)
        else:
            overlap_pairs = overlap_soh_policy

        # ready
        demand_only = planning_mode == "demand_only"
        if demand_only:
            if demand_source == "actuals":
                ready = has_policies and has_demand
            else:
                ready = has_policies
        elif demand_source == "actuals":
            ready = has_soh and has_policies and has_demand
        else:
            # baseline/blended: demand from forecast; SOH and policies required
            ready = has_soh and has_policies

        # blockers
        blockers: list[str] = []
        if not has_soh and not demand_only:
            blockers.append(f"No SOH loaded for {wh} → Import Stock On Hand for {wh}")
        if not has_demand and demand_source == "actuals":
            if wh == "AAH":
                blockers.append(
                    f"No Sales Out (AAH) loaded for {wh} → Import Sales Out for AAH"
                )
            elif wh == "BLP":
                blockers.append(
                    f"No Direct sales or Samples (BLP only) loaded for {wh} → Import Demand for BLP"
                )
            else:
                blockers.append(
                    f"No demand loaded for {wh} → Import Demand for {wh}"
                )
        if not has_policies:
            blockers.append(f"No policies for {wh} → Generate default policies for {wh}")

        result.append({
            "warehouse_code": wh,
            "has_soh": has_soh,
            "has_demand": has_demand,
            "has_policies": has_policies,
            "overlap_pairs": overlap_pairs,
            "ready": ready,
            "blockers": blockers,
            "soh_latest_week": soh_latest.isoformat() if soh_latest else None,
            "demand_latest_week": demand_latest.isoformat() if demand_latest else None,
        })

    return result
