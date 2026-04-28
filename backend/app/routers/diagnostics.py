"""Planning readiness diagnostics: why pages are empty."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    DemandActual,
    DemandType,
    InventorySnapshotWeekly,
    PlannedOrder,
    PlanRun,
    PlanningPolicy,
    Product,
    ProjectedInventory,
    Receipt,
    Warehouse,
)
from app.security.auth import require_any_auth
from app.services.app_settings import get_sample_sales_soh_warehouses
from app.services.warehouse_readiness import check_planning_readiness

router = APIRouter(dependencies=[Depends(require_any_auth)])


@router.get("/warehouse-readiness")
def get_warehouse_readiness(
    demand_source: str = Query("actuals", description="actuals | baseline | blended"),
    planning_mode: str = Query(
        "stock_aware",
        description="stock_aware | demand_only — SOH not required for ready when demand_only",
    ),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    Per-warehouse planning readiness.
    Returns list of {warehouse_code, has_soh, has_demand, has_policies, overlap_pairs, ready, blockers[]}.
    """
    mode = planning_mode if planning_mode in ("stock_aware", "demand_only") else "stock_aware"
    return check_planning_readiness(db, demand_source=demand_source, planning_mode=mode)


@router.get("/planning-readiness")
def get_planning_readiness(
    plan_run_id: int | None = Query(None, description="Optional plan run ID for run-specific stats"),
    planning_mode: str = Query(
        "stock_aware",
        description="stock_aware | demand_only — missing SOH is informational only for demand_only",
    ),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Return planning readiness diagnostics: why pages may be empty.
    Used by frontend NoDataWithReason to show actionable blockers.
    Default is stock-aware oriented (SOH can block ready_to_plan). demand_only relaxes SOH-related gates.
    """
    mode = planning_mode if planning_mode in ("stock_aware", "demand_only") else "stock_aware"
    demand_only_ctx = mode == "demand_only"
    products_count = db.query(Product).filter(Product.active.is_(True)).count()
    policies_count = db.query(PlanningPolicy).count()
    policy_warehouses = (
        db.query(PlanningPolicy.warehouse_code)
        .distinct()
        .all()
    )
    policy_warehouses_list = [r[0] for r in policy_warehouses if r[0]]

    soh_warehouses = get_sample_sales_soh_warehouses(db)

    # Demand (all warehouses for planning; Data Health uses AAH)
    demand_rows = db.query(DemandActual).filter(
        DemandActual.demand_type == DemandType.CUSTOMER,
    ).count()
    demand_latest = (
        db.query(func.max(DemandActual.week_start))
        .filter(DemandActual.demand_type == DemandType.CUSTOMER)
        .scalar()
    )
    demand_warehouses = (
        db.query(DemandActual.warehouse_code)
        .filter(DemandActual.demand_type == DemandType.CUSTOMER)
        .distinct()
        .all()
    )
    demand_warehouses_list = [r[0] for r in demand_warehouses if r[0]]

    # SOH (all warehouses)
    soh_rows = db.query(InventorySnapshotWeekly).count()
    soh_latest = db.query(func.max(InventorySnapshotWeekly.week_start)).scalar()
    soh_warehouses_in_db = (
        db.query(InventorySnapshotWeekly.warehouse_code)
        .distinct()
        .all()
    )
    soh_warehouses_list = [r[0] for r in soh_warehouses_in_db if r[0]]

    # Receipts
    warehouses = [w.code for w in db.query(Warehouse).filter(Warehouse.active.is_(True)).all()]
    today = date.today()
    eight_weeks_later = today + timedelta(days=56)
    receipts_rows = (
        db.query(Receipt)
        .filter(
            Receipt.warehouse_code.in_(warehouses or ["AAH"]),
            Receipt.week_start >= today,
            Receipt.week_start <= eight_weeks_later,
        )
        .count()
    )
    receipts_latest = (
        db.query(func.max(Receipt.week_start))
        .filter(Receipt.warehouse_code.in_(warehouses or ["AAH"]))
        .scalar()
    )

    plan_runs_count = db.query(PlanRun).count()
    projected_inventory_rows_for_run = 0
    planned_orders_rows_for_run = 0
    if plan_run_id:
        projected_inventory_rows_for_run = (
            db.query(ProjectedInventory).filter(ProjectedInventory.plan_run_id == plan_run_id).count()
        )
        planned_orders_rows_for_run = (
            db.query(PlannedOrder).filter(PlannedOrder.plan_run_id == plan_run_id).count()
        )

    # Build blockers
    blockers: list[dict[str, str]] = []
    ready_to_plan = True

    if products_count == 0:
        blockers.append({
            "code": "no_products",
            "message": "No active products. Import product master first.",
            "action_label": "Import Products",
            "action_href": "/imports",
        })
        ready_to_plan = False

    if policies_count == 0:
        blockers.append({
            "code": "no_policies",
            "message": "No planning policies. Create policies for (SKU, warehouse) in Admin → Policies.",
            "action_label": "Admin → Policies",
            "action_href": "/admin/policies",
        })
        ready_to_plan = False

    if demand_rows == 0 or demand_latest is None:
        blockers.append({
            "code": "no_demand",
            "message": "No demand data. AAH: Import Sales Out (AAH). BLP: Import Direct sales or Samples (BLP only).",
            "action_label": "Imports",
            "action_href": "/imports",
        })
        ready_to_plan = False

    if soh_rows == 0 or soh_latest is None:
        blockers.append({
            "code": "no_soh",
            "message": (
                "No stock on hand. Required for stock-aware planning; optional for demand-only (modeled position)."
                if demand_only_ctx
                else "No stock on hand. Import SOH for configured warehouses."
            ),
            "action_label": "Imports",
            "action_href": "/imports",
        })
        if not demand_only_ctx:
            ready_to_plan = False

    # Warehouse mismatch: planning uses sample_sales_soh_warehouses (default BLP)
    # but SOH/demand may be for AAH
    soh_wh_set = set(soh_warehouses_list)
    soh_config_set = set(soh_warehouses)
    if soh_config_set and not (soh_wh_set & soh_config_set):
        blockers.append({
            "code": "soh_warehouse_mismatch",
            "message": (
                f"SOH warehouse mismatch: planning expects {list(soh_config_set)} but SOH is for {soh_warehouses_list}. "
                "Blocks stock-aware runs; demand-only may still run if policies and demand exist."
                if demand_only_ctx
                else f"Planning expects SOH for warehouses {list(soh_config_set)} but SOH data is for {soh_warehouses_list}. Update Admin → Settings → SOH warehouses to match your data."
            ),
            "action_label": "Admin → Settings",
            "action_href": "/admin/settings",
        })
        if not demand_only_ctx:
            ready_to_plan = False

    # Policy vs SOH warehouse mismatch
    policy_wh_set = set(policy_warehouses_list)
    if policy_wh_set and soh_config_set and not (policy_wh_set & soh_config_set):
        blockers.append({
            "code": "policy_warehouse_mismatch",
            "message": (
                f"Policies are for {policy_warehouses_list} but SOH config is {list(soh_config_set)}. "
                "Fix for stock-aware alignment; less critical for demand-only."
                if demand_only_ctx
                else f"Policies exist for {policy_warehouses_list} but planning uses SOH from {list(soh_config_set)}. Create policies for warehouses in SOH config."
            ),
            "action_label": "Admin → Policies",
            "action_href": "/admin/policies",
        })
        if not demand_only_ctx:
            ready_to_plan = False

    if plan_runs_count == 0 and plan_run_id is None:
        blockers.append({
            "code": "no_plan_runs",
            "message": "No plan runs yet. Run a plan on the Dashboard.",
            "action_label": "Dashboard",
            "action_href": "/",
        })
    elif plan_runs_count > 0 and plan_run_id is None:
        blockers.append({
            "code": "no_plan_selected",
            "message": "Select a plan run from the dropdown, or go to Dashboard to run a new plan.",
            "action_label": "Dashboard",
            "action_href": "/",
        })

    if plan_run_id and projected_inventory_rows_for_run == 0 and plan_runs_count > 0:
        blockers.append({
            "code": "no_projections",
            "message": "Plan run produced no projections. Ensure policies and demand align; SOH must align for stock-aware (not required for demand-only). See Admin → Settings → SOH warehouses.",
            "action_label": "Data Health",
            "action_href": "/reports/data-health",
        })

    return {
        "ready_to_plan": ready_to_plan,
        "planning_mode": mode,
        "blockers": blockers,
        "stats": {
            "products_count": products_count,
            "policies_count": policies_count,
            "demand_rows": demand_rows,
            "demand_latest_week": demand_latest.isoformat() if demand_latest else None,
            "demand_warehouses": demand_warehouses_list,
            "soh_rows": soh_rows,
            "soh_latest_week": soh_latest.isoformat() if soh_latest else None,
            "soh_warehouses": soh_warehouses_list,
            "soh_config_warehouses": soh_warehouses,
            "receipts_rows": receipts_rows,
            "receipts_latest_week": receipts_latest.isoformat() if receipts_latest else None,
            "plan_runs_count": plan_runs_count,
            "projected_inventory_rows_for_run": projected_inventory_rows_for_run,
            "planned_orders_rows_for_run": planned_orders_rows_for_run,
        },
    }
