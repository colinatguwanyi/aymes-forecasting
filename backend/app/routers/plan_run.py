from __future__ import annotations
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PlanRun, PlannedOrder, ProjectedInventory
from app.schemas import (
    PlanRun as PlanRunSchema,
    PlannedOrder as PlannedOrderSchema,
    ProjectedInventory as ProjectedInventorySchema,
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
