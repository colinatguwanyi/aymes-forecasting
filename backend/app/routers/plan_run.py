from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.auth import require_admin_or_planner, require_any_auth
from app.models import (
    DemandOverrideWeekly,
    PlanRun,
    PlanRunDemandInputWeekly,
    PlanRunEvent,
    PlanRunFreezeEvent,
    PlannedOrder,
    PlannedOrderOverrideWeekly,
    PlanningPolicy,
    ProjectedInventory,
)
from app.schemas import (
    PlanRun as PlanRunSchema,
    PlannedOrder as PlannedOrderSchema,
    ProjectedInventory as ProjectedInventorySchema,
    PlanningException,
    SkuWeekExplanation,
    SkuWeekExplanationPolicy,
    SkuWeekExplanationProjection,
)
from app.services.demand_resolver import NoBaselineRunsError, published_run_exists, resolve_demand_for_run, _frozen_mondays_for_plan
from app.services.planning import AllWarehousesSkippedError, _monday_before, run_plan

logger = logging.getLogger(__name__)
router = APIRouter()


def _human_breakdown(breakdown: dict[str, Any] | None, source: str) -> str | None:
    """Human-readable demand breakdown for explain UI."""
    if not breakdown:
        return None
    if "override" in breakdown:
        return f"Override: {breakdown['override']}"
    if "forecast_total" in breakdown:
        return f"Forecast total: {breakdown['forecast_total']}"
    if "preserved" in breakdown:
        return f"Preserved (frozen): {breakdown['preserved']}"
    parts = [f"{k}: {v}" for k, v in sorted(breakdown.items()) if isinstance(v, (int, float))]
    return ", ".join(parts) if parts else None


@router.post("/run", response_model=PlanRunSchema, dependencies=[Depends(require_admin_or_planner)])
def run_planning(
    scenario_name: str = Query(..., description="Scenario name for this run"),
    run_at: str | None = Query(None, description="Date to use as run date (YYYY-MM-DD)"),
    demand_source: str = Query("actuals", description="Demand source: actuals | baseline | blended"),
    freeze_weeks: int = Query(4, ge=0, le=52),
    created_by: str | None = Query(None),
    notes: str | None = Query(None),
    warehouses_scope: str | None = Query(None, description="Comma-separated warehouse codes, e.g. AAH,BLP. Omit for legacy (all from policies)."),
    db: Session = Depends(get_db),
) -> PlanRun:
    run_date = date.fromisoformat(run_at) if run_at else date.today()
    wh_list: list[str] | None = None
    if warehouses_scope and warehouses_scope.strip():
        wh_list = [w.strip() for w in warehouses_scope.split(",") if w.strip()]
    try:
        plan_run = run_plan(
            db,
            scenario_name=scenario_name,
            run_at=run_date,
            demand_source=demand_source,
            freeze_weeks=freeze_weeks,
            created_by=created_by,
            notes=notes,
            warehouses_scope=wh_list,
        )
    except NoBaselineRunsError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except AllWarehousesSkippedError as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail={
                "code": "all_warehouses_skipped",
                "message": str(e),
                "skipped_warehouses": e.skipped_warehouses,
            },
        )
    except ValueError as e:
        db.rollback()
        msg = str(e)
        code = "demo_data_detected" if "Demo data disabled" in msg or "demo" in msg.lower() else "planning_outputs_invalid"
        raise HTTPException(status_code=400, detail={"code": code, "message": msg})
    return plan_run


@router.get("/runs", response_model=list[PlanRunSchema], dependencies=[Depends(require_any_auth)])
def list_plan_runs(db: Session = Depends(get_db)) -> list[PlanRun]:
    return db.query(PlanRun).order_by(PlanRun.created_at.desc()).all()


@router.get("/runs/{plan_run_id}", response_model=PlanRunSchema, dependencies=[Depends(require_any_auth)])
def get_plan_run(plan_run_id: int, db: Session = Depends(get_db)) -> PlanRun:
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    return run


@router.patch("/runs/{plan_run_id}", response_model=PlanRunSchema, dependencies=[Depends(require_admin_or_planner)])
def update_plan_run(
    plan_run_id: int,
    demand_source: str | None = Query(None),
    baseline_train_end_week_start: date | None = Query(None, description="When demand_source=baseline, which published run to use (latest if null)"),
    clear_baseline_train_end_week_start: bool = Query(False, description="If true, set baseline_train_end_week_start to null (use latest on next recalc)"),
    freeze_weeks: int | None = Query(None, ge=0, le=52),
    notes: str | None = Query(None),
    db: Session = Depends(get_db),
) -> PlanRun:
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    if demand_source is not None:
        run.demand_source = demand_source
    if clear_baseline_train_end_week_start:
        run.baseline_train_end_week_start = None
    elif baseline_train_end_week_start is not None:
        if not published_run_exists(db, baseline_train_end_week_start, warehouse_code="AAH"):
            raise HTTPException(
                status_code=409,
                detail=f"Selected forecast run {baseline_train_end_week_start!s} not found. Choose another run or reset to latest.",
            )
        run.baseline_train_end_week_start = baseline_train_end_week_start
    if freeze_weeks is not None:
        run.freeze_weeks = freeze_weeks
    if notes is not None:
        run.notes = notes
    db.commit()
    db.refresh(run)
    return run


@router.post("/runs/{plan_run_id}/reset-forecast-run", response_model=PlanRunSchema, dependencies=[Depends(require_admin_or_planner)])
def reset_forecast_run(
    plan_run_id: int,
    reset_all: bool = Query(False, description="If true, also clear baseline_train_end_week_start (user override)"),
    created_by: str | None = Query(None),
    db: Session = Depends(get_db),
) -> PlanRun:
    """Clear pinned forecast run (selected_train_end_week_start). Next recalc will pick latest. Optionally clear user override (reset_all=true)."""
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    prev_selected = getattr(run, "selected_train_end_week_start", None)
    prev_baseline = getattr(run, "baseline_train_end_week_start", None)
    run.selected_train_end_week_start = None
    if reset_all:
        run.baseline_train_end_week_start = None
    db.add(
        PlanRunEvent(
            plan_run_id=plan_run_id,
            event_type="RESET_FORECAST_RUN",
            created_by=created_by,
            details_json={
                "previous_selected_train_end_week_start": prev_selected.isoformat() if prev_selected else None,
                "previous_baseline_train_end_week_start": prev_baseline.isoformat() if prev_baseline else None,
                "reset_all": reset_all,
            },
        )
    )
    db.commit()
    db.refresh(run)
    return run


@router.get("/runs/{plan_run_id}/projected-inventory", response_model=list[ProjectedInventorySchema], dependencies=[Depends(require_any_auth)])
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


@router.get("/runs/{plan_run_id}/planned-orders", response_model=list[PlannedOrderSchema], dependencies=[Depends(require_any_auth)])
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


@router.get("/runs/{plan_run_id}/exceptions", response_model=list[PlanningException], dependencies=[Depends(require_any_auth)])
def get_plan_exceptions(
    plan_run_id: int,
    within_weeks: int = Query(12, ge=1, le=52, description="Only weeks within this many weeks from today"),
    include_low_cover: bool = Query(True, description="Include low weeks-of-cover as warnings"),
    db: Session = Depends(get_db),
) -> list[PlanningException]:
    """Exceptions queue: stockout and optionally low-cover SKU-weeks within horizon."""
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    run_at: date = cast(date, run.run_at)
    cutoff = run_at + timedelta(weeks=within_weeks)
    q = (
        db.query(ProjectedInventory)
        .filter(
            ProjectedInventory.plan_run_id == plan_run_id,
            ProjectedInventory.week_start >= run_at,
            ProjectedInventory.week_start <= cutoff,
        )
    )
    rows = q.order_by(ProjectedInventory.week_start, ProjectedInventory.sku).all()
    out: list[PlanningException] = []
    for r in rows:
        r_stockout: bool = cast(bool, r.stockout)
        r_sku: str = cast(str, r.sku)
        r_wh: str = cast(str, r.warehouse_code)
        r_week: date = cast(date, r.week_start)
        r_proj: Decimal | None = cast(Decimal | None, r.projected_qty)
        r_woc: Decimal | None = cast(Decimal | None, r.weeks_of_cover)
        if r_stockout:
            out.append(
                PlanningException(
                    type="stockout",
                    severity="error",
                    sku=r_sku,
                    warehouse_code=r_wh,
                    week_start=r_week,
                    message=f"Projected stockout week {r_week}",
                    projected_qty=r_proj,
                    weeks_of_cover=r_woc,
                    plan_run_id=plan_run_id,
                )
            )
        elif include_low_cover and r_woc is not None:
            try:
                woc = float(r_woc)
                if woc < 2:
                    out.append(
                        PlanningException(
                            type="low_cover",
                            severity="warning",
                            sku=r_sku,
                            warehouse_code=r_wh,
                            week_start=r_week,
                            message=f"Low cover ({r_woc} weeks) week {r_week}",
                            projected_qty=r_proj,
                            weeks_of_cover=r_woc,
                            plan_run_id=plan_run_id,
                        )
                    )
            except (TypeError, ValueError):
                pass
    return out


@router.get("/runs/{plan_run_id}/demand-inputs", dependencies=[Depends(require_any_auth)])
def get_demand_inputs(
    plan_run_id: int,
    from_week: str | None = Query(None),
    to_week: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    q = db.query(PlanRunDemandInputWeekly).filter(PlanRunDemandInputWeekly.plan_run_id == plan_run_id)
    if from_week:
        q = q.filter(PlanRunDemandInputWeekly.week_start >= date.fromisoformat(from_week))
    if to_week:
        q = q.filter(PlanRunDemandInputWeekly.week_start <= date.fromisoformat(to_week))
    rows = q.order_by(PlanRunDemandInputWeekly.week_start, PlanRunDemandInputWeekly.sku).all()
    return [
        {
            "week_start": r.week_start.isoformat(),
            "sku": r.sku,
            "warehouse_code": r.warehouse_code,
            "demand_qty": float(cast(Decimal, r.demand_qty)),
            "source": r.source,
            "source_ref": r.source_ref,
            "demand_breakdown_json": getattr(r, "demand_breakdown_json", None),
            "demand_includes_samples": bool(getattr(r, "demand_includes_samples", True)),
            "is_frozen": bool(r.is_frozen),
        }
        for r in rows
    ]


@router.post("/runs/{plan_run_id}/demand-overrides", dependencies=[Depends(require_admin_or_planner)])
def upsert_demand_overrides(
    plan_run_id: int,
    body: list[dict[str, Any]] = Body(..., description="List of {week_start, sku, warehouse_code, override_qty, reason_code, notes?, created_by?}"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    for row in body:
        week_start = date.fromisoformat(row["week_start"])
        sku = str(row["sku"])
        warehouse_code = str(row["warehouse_code"])
        override_qty = Decimal(str(row["override_qty"]))
        reason_code = str(row.get("reason_code", "other"))
        notes = row.get("notes")
        created_by = row.get("created_by")
        existing = (
            db.query(DemandOverrideWeekly)
            .filter(
                DemandOverrideWeekly.plan_run_id == plan_run_id,
                DemandOverrideWeekly.week_start == week_start,
                DemandOverrideWeekly.sku == sku,
                DemandOverrideWeekly.warehouse_code == warehouse_code,
            )
            .first()
        )
        if existing:
            existing.override_qty = override_qty
            existing.reason_code = reason_code
            existing.notes = notes
            if created_by is not None:
                existing.created_by = created_by
        else:
            db.add(
                DemandOverrideWeekly(
                    plan_run_id=plan_run_id,
                    week_start=week_start,
                    sku=sku,
                    warehouse_code=warehouse_code,
                    override_qty=override_qty,
                    reason_code=reason_code,
                    notes=notes,
                    created_by=created_by,
                )
            )
    db.commit()
    return {"updated": len(body)}


@router.delete("/runs/{plan_run_id}/demand-overrides", dependencies=[Depends(require_admin_or_planner)])
def delete_demand_overrides(
    plan_run_id: int,
    body: list[dict[str, Any]] = Body(..., description="List of {week_start, sku, warehouse_code}"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    deleted = 0
    for row in body:
        week_start = date.fromisoformat(row["week_start"])
        sku = str(row["sku"])
        warehouse_code = str(row["warehouse_code"])
        n = (
            db.query(DemandOverrideWeekly)
            .filter(
                DemandOverrideWeekly.plan_run_id == plan_run_id,
                DemandOverrideWeekly.week_start == week_start,
                DemandOverrideWeekly.sku == sku,
                DemandOverrideWeekly.warehouse_code == warehouse_code,
            )
            .delete()
        )
        deleted += n
    db.commit()
    return {"deleted": deleted}


@router.get("/runs/{plan_run_id}/order-overrides", dependencies=[Depends(require_any_auth)])
def get_order_overrides(
    plan_run_id: int,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    rows = (
        db.query(PlannedOrderOverrideWeekly)
        .filter(PlannedOrderOverrideWeekly.plan_run_id == plan_run_id)
        .order_by(PlannedOrderOverrideWeekly.week_start, PlannedOrderOverrideWeekly.sku)
        .all()
    )
    out_list: list[dict[str, Any]] = []
    for r in rows:
        _cat = getattr(r, "created_at", None)
        out_list.append({
            "week_start": r.week_start.isoformat(),
            "sku": r.sku,
            "warehouse_code": r.warehouse_code,
            "override_order_qty": float(cast(Decimal, r.override_order_qty)),
            "reason_code": r.reason_code,
            "notes": r.notes,
            "created_at": _cat.isoformat() if _cat is not None else None,
            "created_by": r.created_by,
        })
    return out_list


@router.post("/runs/{plan_run_id}/order-overrides", dependencies=[Depends(require_admin_or_planner)])
def upsert_order_overrides(
    plan_run_id: int,
    body: list[dict[str, Any]] = Body(..., description="List of {week_start, sku, warehouse_code, override_order_qty, reason_code, notes?, created_by?}"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    for row in body:
        week_start = date.fromisoformat(row["week_start"])
        sku = str(row["sku"])
        warehouse_code = str(row["warehouse_code"])
        override_order_qty = Decimal(str(row["override_order_qty"]))
        reason_code = str(row.get("reason_code", "other"))
        notes = row.get("notes")
        created_by = row.get("created_by")
        existing = (
            db.query(PlannedOrderOverrideWeekly)
            .filter(
                PlannedOrderOverrideWeekly.plan_run_id == plan_run_id,
                PlannedOrderOverrideWeekly.week_start == week_start,
                PlannedOrderOverrideWeekly.sku == sku,
                PlannedOrderOverrideWeekly.warehouse_code == warehouse_code,
            )
            .first()
        )
        if existing:
            existing.override_order_qty = override_order_qty
            existing.reason_code = reason_code
            existing.notes = notes
            if created_by is not None:
                existing.created_by = created_by
        else:
            db.add(
                PlannedOrderOverrideWeekly(
                    plan_run_id=plan_run_id,
                    week_start=week_start,
                    sku=sku,
                    warehouse_code=warehouse_code,
                    override_order_qty=override_order_qty,
                    reason_code=reason_code,
                    notes=notes,
                    created_by=created_by,
                )
            )
    db.commit()
    return {"updated": len(body)}


@router.delete("/runs/{plan_run_id}/order-overrides", dependencies=[Depends(require_admin_or_planner)])
def delete_order_overrides(
    plan_run_id: int,
    body: list[dict[str, Any]] = Body(..., description="List of {week_start, sku, warehouse_code}"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    deleted = 0
    for row in body:
        week_start = date.fromisoformat(row["week_start"])
        sku = str(row["sku"])
        warehouse_code = str(row["warehouse_code"])
        n = (
            db.query(PlannedOrderOverrideWeekly)
            .filter(
                PlannedOrderOverrideWeekly.plan_run_id == plan_run_id,
                PlannedOrderOverrideWeekly.week_start == week_start,
                PlannedOrderOverrideWeekly.sku == sku,
                PlannedOrderOverrideWeekly.warehouse_code == warehouse_code,
            )
            .delete()
        )
        deleted += n
    db.commit()
    return {"deleted": deleted}


@router.post("/runs/{plan_run_id}/freeze", dependencies=[Depends(require_admin_or_planner)])
def freeze_plan_run(
    plan_run_id: int,
    body: dict[str, Any] = Body(..., description="{ scope: 'demand'|'orders'|'both', freeze_weeks?: int, notes?: str, frozen_by?: str }"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    scope = str(body.get("scope", "both"))
    freeze_weeks = int(body.get("freeze_weeks", run.freeze_weeks))
    notes = body.get("notes")
    frozen_by = body.get("frozen_by")
    plan_start = cast(date, getattr(run, "plan_start_week_start", run.run_at))
    frozen_mondays = _frozen_mondays_for_plan(plan_start, freeze_weeks)
    if scope in ("demand", "both"):
        for w in frozen_mondays:
            db.query(PlanRunDemandInputWeekly).filter(
                PlanRunDemandInputWeekly.plan_run_id == plan_run_id,
                PlanRunDemandInputWeekly.week_start == w,
            ).update({"is_frozen": True}, synchronize_session=False)
    if scope in ("orders", "both"):
        for w in frozen_mondays:
            db.query(PlannedOrder).filter(
                PlannedOrder.plan_run_id == plan_run_id,
                PlannedOrder.week_start == w,
            ).update({"is_frozen": True}, synchronize_session=False)
    db.add(
        PlanRunFreezeEvent(
            plan_run_id=plan_run_id,
            frozen_by=frozen_by,
            freeze_weeks=freeze_weeks,
            scope=scope,
            notes=notes,
        )
    )
    db.commit()
    return {"scope": scope, "freeze_weeks": freeze_weeks}


@router.post("/runs/{plan_run_id}/unfreeze", dependencies=[Depends(require_admin_or_planner)])
def unfreeze_plan_run(
    plan_run_id: int,
    body: dict[str, Any] = Body(..., description="{ scope: 'demand'|'orders'|'both', from_week?: str, to_week?: str }"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    scope = str(body.get("scope", "both"))
    from_week = date.fromisoformat(body["from_week"]) if body.get("from_week") else None
    to_week = date.fromisoformat(body["to_week"]) if body.get("to_week") else None
    if scope in ("demand", "both"):
        q = db.query(PlanRunDemandInputWeekly).filter(PlanRunDemandInputWeekly.plan_run_id == plan_run_id, PlanRunDemandInputWeekly.is_frozen.is_(True))
        if from_week:
            q = q.filter(PlanRunDemandInputWeekly.week_start >= from_week)
        if to_week:
            q = q.filter(PlanRunDemandInputWeekly.week_start <= to_week)
        q.update({"is_frozen": False}, synchronize_session=False)
    if scope in ("orders", "both"):
        q = db.query(PlannedOrder).filter(PlannedOrder.plan_run_id == plan_run_id, PlannedOrder.is_frozen.is_(True))
        if from_week:
            q = q.filter(PlannedOrder.week_start >= from_week)
        if to_week:
            q = q.filter(PlannedOrder.week_start <= to_week)
        q.update({"is_frozen": False}, synchronize_session=False)
    db.commit()
    return {"scope": scope}


@router.post("/runs/{plan_run_id}/recalculate-demand", dependencies=[Depends(require_admin_or_planner)])
def recalculate_demand_inputs(
    plan_run_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Recompute demand inputs for non-frozen weeks only (does not re-run full planning)."""
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    run_at = cast(date, run.run_at)
    run_week = _monday_before(run_at)
    to_week = run_week + timedelta(days=53 * 7)
    try:
        resolve_demand_for_run(db, plan_run_id, run_week, to_week, recompute_non_frozen_only=True)
    except NoBaselineRunsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    db.commit()
    return {"plan_run_id": plan_run_id, "status": "ok"}


@router.get("/runs/{plan_run_id}/explain", dependencies=[Depends(require_any_auth)])
def explain_plan_run_cell(
    plan_run_id: int,
    sku: str = Query(...),
    warehouse_code: str = Query(...),
    week_start: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Explain demand_used, receipts, policy, why_order_qty for one SKU/warehouse/week."""
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found")
    week = date.fromisoformat(week_start)
    demand_row = (
        db.query(PlanRunDemandInputWeekly)
        .filter(
            PlanRunDemandInputWeekly.plan_run_id == plan_run_id,
            PlanRunDemandInputWeekly.sku == sku,
            PlanRunDemandInputWeekly.warehouse_code == warehouse_code,
            PlanRunDemandInputWeekly.week_start == week,
        )
        .first()
    )
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
        .filter(PlanningPolicy.sku == sku, PlanningPolicy.warehouse_code == warehouse_code)
        .first()
    )
    planned = (
        db.query(PlannedOrder)
        .filter(
            PlannedOrder.plan_run_id == plan_run_id,
            PlannedOrder.sku == sku,
            PlannedOrder.warehouse_code == warehouse_code,
            PlannedOrder.week_start == week,
        )
        .first()
    )
    plan_start = cast(date, getattr(run, "plan_start_week_start", run.run_at))
    freeze_weeks = int(getattr(run, "freeze_weeks", 4) or 4)
    frozen_mondays = _frozen_mondays_for_plan(plan_start, freeze_weeks)
    in_freeze_window = week in frozen_mondays

    demand_used: dict[str, Any] = {
        "qty": 0,
        "source": "none",
        "override": False,
        "is_frozen": False,
        "demand_breakdown": None,
        "in_freeze_window": in_freeze_window,
        "freeze_window_anchor": plan_start.isoformat(),
    }
    if demand_row:
        breakdown = getattr(demand_row, "demand_breakdown_json", None)
        demand_used = {
            "qty": float(cast(Decimal, demand_row.demand_qty)),
            "source": demand_row.source,
            "source_ref": demand_row.source_ref,
            "is_frozen": bool(demand_row.is_frozen),
            "override": demand_row.source == "override",
            "demand_breakdown": breakdown,
            "in_freeze_window": in_freeze_window,
            "freeze_window_anchor": plan_start.isoformat(),
            "breakdown_summary": _human_breakdown(breakdown, str(demand_row.source)) if breakdown else None,
        }
    receipts_used: dict[str, Any] = {"qty": 0}
    if proj:
        receipts_used = {"qty": float(cast(Decimal, proj.receipts_qty))}
    policy_params: dict[str, Any] = {}
    if policy_row:
        _tw = getattr(policy_row, "target_weeks", None)
        _ss = getattr(policy_row, "safety_stock_weeks", None)
        policy_params = {
            "mode": getattr(policy_row.mode, "value", None),
            "target_weeks": float(cast(Decimal, _tw)) if _tw is not None else None,
            "safety_stock_weeks": float(cast(Decimal, _ss)) if _ss is not None else None,
            "lead_time_weeks": sum(
                float(getattr(policy_row, f, 0) or 0)
                for f in ("lead_time_production_weeks", "lead_time_slot_wait_weeks", "lead_time_haulage_weeks", "lead_time_putaway_weeks", "lead_time_padding_weeks")
            ),
        }
    why_order_qty: dict[str, Any] = {"order_qty": 0, "is_frozen": False, "steps": []}
    if planned:
        why_order_qty = {
            "order_qty": float(cast(Decimal, planned.order_qty)),
            "is_frozen": bool(planned.is_frozen),
            "steps": ["Computed from WOS/ROP or applied override; frozen=" + str(bool(planned.is_frozen))],
        }
    proj_out: dict[str, Any] | None = None
    if proj:
        _woc = getattr(proj, "weeks_of_cover", None)
        proj_out = {
            "start_qty": float(cast(Decimal, proj.start_qty)),
            "demand_qty": float(cast(Decimal, proj.demand_qty)),
            "projected_qty": float(cast(Decimal, proj.projected_qty)),
            "weeks_of_cover": float(_woc) if _woc is not None else None,
            "stockout": bool(proj.stockout),
        }
    return {
        "plan_run_id": plan_run_id,
        "sku": sku,
        "warehouse_code": warehouse_code,
        "week_start": week_start,
        "demand_used": demand_used,
        "receipts_used": receipts_used,
        "policy_params": policy_params,
        "why_order_qty": why_order_qty,
        "projection": proj_out,
    }


@router.get("/runs/{plan_run_id}/explanation", response_model=SkuWeekExplanation, dependencies=[Depends(require_any_auth)])
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
    demand_input = (
        db.query(PlanRunDemandInputWeekly)
        .filter(
            PlanRunDemandInputWeekly.plan_run_id == plan_run_id,
            PlanRunDemandInputWeekly.sku == sku,
            PlanRunDemandInputWeekly.warehouse_code == warehouse_code,
            PlanRunDemandInputWeekly.week_start == week,
        )
        .first()
    )
    demand_breakdown = getattr(demand_input, "demand_breakdown_json", None) if demand_input else None
    demand_includes_samples = bool(getattr(demand_input, "demand_includes_samples", True)) if demand_input else None
    return SkuWeekExplanation(
        sku=sku,
        warehouse_code=warehouse_code,
        plan_run_id=plan_run_id,
        policy=policy,
        projection=projection,
        forecast_method="trailing_mean",
        demand_breakdown=demand_breakdown,
        demand_includes_samples=demand_includes_samples,
    )
