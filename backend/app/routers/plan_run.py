from __future__ import annotations

import logging
from datetime import date
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PlanRun, PlannedOrder, PlanningPolicy, ProjectedInventory
from app.schemas import (
    PlanRun as PlanRunSchema,
    PlannedOrder as PlannedOrderSchema,
    ProjectedInventory as ProjectedInventorySchema,
    SkuWeekExplanation,
    SkuWeekExplanationPolicy,
    SkuWeekExplanationProjection,
)
from app.services.planning import run_plan

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/run", response_model=PlanRunSchema)
def run_planning(
    scenario_name: str = Query(..., description="Scenario name for this run"),
    run_at: str | None = Query(None, description="Date to use as run date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> PlanRun:
    run_date = date.fromisoformat(run_at) if run_at else date.today()
    plan_run = run_plan(db, scenario_name=scenario_name, run_at=run_date)
    return plan_run


@router.get("/runs", response_model=list[PlanRunSchema])
def list_plan_runs(db: Session = Depends(get_db)) -> list[PlanRun]:
    return db.query(PlanRun).order_by(PlanRun.created_at.desc()).all()


@router.get("/runs/{plan_run_id}", response_model=PlanRunSchema)
def get_plan_run(plan_run_id: int, db: Session = Depends(get_db)) -> PlanRun:
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    return run


@router.get("/runs/{plan_run_id}/projected-inventory", response_model=list[ProjectedInventorySchema])
def get_projected_inventory(
    plan_run_id: int,
    sku: str | None = None,
    warehouse_code: str | None = None,
    db: Session = Depends(get_db),
) -> list[ProjectedInventory]:
    q = db.query(ProjectedInventory).filter(ProjectedInventory.plan_run_id == plan_run_id)
    if sku:
        q = q.filter(ProjectedInventory.sku == sku)
    if warehouse_code:
        q = q.filter(ProjectedInventory.warehouse_code == warehouse_code)
    return q.order_by(ProjectedInventory.week_start, ProjectedInventory.sku).all()


@router.get("/runs/{plan_run_id}/planned-orders", response_model=list[PlannedOrderSchema])
def get_planned_orders(
    plan_run_id: int,
    sku: str | None = None,
    warehouse_code: str | None = None,
    db: Session = Depends(get_db),
) -> list[PlannedOrder]:
    q = db.query(PlannedOrder).filter(PlannedOrder.plan_run_id == plan_run_id)
    if sku:
        q = q.filter(PlannedOrder.sku == sku)
    if warehouse_code:
        q = q.filter(PlannedOrder.warehouse_code == warehouse_code)
    return q.order_by(PlannedOrder.week_start, PlannedOrder.sku).all()


@router.get("/runs/{plan_run_id}/explanation", response_model=SkuWeekExplanation)
def get_sku_week_explanation(
    plan_run_id: int,
    sku: str = Query(..., description="SKU"),
    warehouse_code: str = Query(..., description="Warehouse code"),
    week_start: str = Query(..., description="Week start (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> SkuWeekExplanation:
    """Explain-the-forecast: policy + projection for one SKU/week. Used by RightPanel drill-down."""
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    week = date.fromisoformat(week_start)
    proj = (
        db.query(ProjectedInventory)
        .filter(
            ProjectedInventory.plan_run_id == plan_run_id,
            ProjectedInventory.sku == sku,
            ProjectedInventory.warehouse_code == warehouse_code,
            ProjectedInventory.week_start == week,
        )
        .first()
    )
    policy_row = (
        db.query(PlanningPolicy)
        .filter(
            PlanningPolicy.sku == sku,
            PlanningPolicy.warehouse_code == warehouse_code,
        )
        .first()
    )
    policy: SkuWeekExplanationPolicy | None = None
    if policy_row:
        _p: Any = policy_row
        policy = SkuWeekExplanationPolicy(
            mode=getattr(_p.mode, "value", None) if _p.mode is not None else None,
            target_weeks=_p.target_weeks,
            safety_stock_weeks=_p.safety_stock_weeks,
            safety_stock_method=getattr(_p.safety_stock_method, "value", None) if _p.safety_stock_method is not None else None,
            forecast_window_weeks=_p.forecast_window_weeks,
            lead_time_production_weeks=_p.lead_time_production_weeks,
            lead_time_slot_wait_weeks=_p.lead_time_slot_wait_weeks,
            lead_time_haulage_weeks=_p.lead_time_haulage_weeks,
            lead_time_putaway_weeks=_p.lead_time_putaway_weeks,
            lead_time_padding_weeks=_p.lead_time_padding_weeks,
            include_samples=bool(getattr(_p, "include_samples", True)),
        )
    projection: SkuWeekExplanationProjection | None = None
    if proj:
        _r: Any = proj
        projection = SkuWeekExplanationProjection(
            week_start=_r.week_start,
            start_qty=_r.start_qty,
            receipts_qty=_r.receipts_qty,
            demand_qty=_r.demand_qty,
            projected_qty=_r.projected_qty,
            weeks_of_cover=_r.weeks_of_cover,
            stockout=bool(_r.stockout),
        )
    return SkuWeekExplanation(
        sku=sku,
        warehouse_code=warehouse_code,
        plan_run_id=plan_run_id,
        policy=policy,
        projection=projection,
        forecast_method="trailing_mean",
    )
