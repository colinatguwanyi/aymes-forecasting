"""
Resolve demand for a plan run: build base series from actuals/baseline/blended,
apply overrides, respect freeze. Writes plan_run_demand_inputs_weekly.
Planning uses Monday weeks; baseline forecasts use W-TUE week_start (we map Monday -> W-TUE for lookup).
Freeze window is anchored to plan_start_week_start (W-TUE): first N weeks from that date.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy.orm import Session

from app.models import (
    BaselineForecastWeekly,
    DemandActual,
    DemandOverrideWeekly,
    PlanRun,
    PlanRunDemandInputWeekly,
    PlanningPolicy,
    PublishedBaselineForecastWeekly,
)
from app.services.time_bucketing import week_start_for_date

# Canonical demand types for breakdown (must match DemandType enum)
DEMAND_TYPES = ("CUSTOMER", "SAMPLES", "ADJUSTMENT")

# Raised when baseline demand is requested but no published runs exist (caller should return 409/422)
class NoBaselineRunsError(ValueError):
    """No baseline forecast runs available for the requested warehouse."""
    pass


def build_actuals_breakdown(
    by_type: dict[str, float], include_samples: bool
) -> tuple[Decimal, dict[str, Any]]:
    """Pure: given per-type qty and include_samples, return (total_qty, breakdown_json)."""
    included = ["CUSTOMER", "ADJUSTMENT"] + (["SAMPLES"] if include_samples else [])
    excluded = [] if include_samples else ["SAMPLES"]
    total = sum(by_type.get(t, 0.0) for t in included)
    breakdown = {
        **{t: round(by_type.get(t, 0.0), 4) for t in DEMAND_TYPES},
        "included": included,
        "excluded": excluded,
    }
    return Decimal(str(round(total, 4))), breakdown

logger = logging.getLogger(__name__)

# Planning uses Monday weeks
def _monday_before(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _next_monday(d: date) -> date:
    return _monday_before(d) + timedelta(days=7)


def _frozen_mondays_for_plan(plan_start_week_start: date, freeze_weeks: int) -> set[date]:
    """Mondays that fall in the first freeze_weeks W-TUE weeks starting at plan_start_week_start."""
    # W-TUE week k starts at plan_start_week_start + 7*k; its Monday (ISO) is plan_start_week_start + 6 + 7*k
    return {
        plan_start_week_start + timedelta(days=6 + 7 * k)
        for k in range(freeze_weeks)
    }


def _actuals_by_week(db: Session, from_week: date, to_week: date) -> dict[tuple[date, str, str], Decimal]:
    """Sum demand_actuals per (week_start, sku, warehouse_code) in range. Monday weeks."""
    rows = (
        db.query(DemandActual)
        .filter(
            DemandActual.week_start >= from_week,
            DemandActual.week_start <= to_week,
        )
        .all()
    )
    out: dict[tuple[date, str, str], Decimal] = defaultdict(Decimal)
    for r in rows:
        w = cast(date, r.week_start)
        s = cast(str, r.sku)
        wh = cast(str, r.warehouse_code)
        q = cast(Decimal, r.qty)
        out[(w, s, wh)] += q
    return dict(out)


def _actuals_by_week_with_breakdown(
    db: Session,
    from_week: date,
    to_week: date,
    policy_include_samples: dict[tuple[str, str], bool],
) -> tuple[dict[tuple[date, str, str], Decimal], dict[tuple[date, str, str], dict[str, Any]]]:
    """Sum demand_actuals per (week, sku, wh) grouped by demand_type; apply include_samples per (sku, wh).
    Returns (demand_qty per key, breakdown_json per key with CUSTOMER/SAMPLES/ADJUSTMENT, included, excluded).
    """
    rows = (
        db.query(DemandActual)
        .filter(
            DemandActual.week_start >= from_week,
            DemandActual.week_start <= to_week,
        )
        .all()
    )
    raw_breakdowns: dict[tuple[date, str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        w = cast(date, r.week_start)
        s = cast(str, r.sku)
        wh = cast(str, r.warehouse_code)
        q = float(cast(Decimal, r.qty))
        dt = getattr(r, "demand_type", None)
        dt_name = (getattr(dt, "value", None) or str(dt)) if dt is not None else "unknown"
        raw_breakdowns[(w, s, wh)][dt_name] += q
    totals: dict[tuple[date, str, str], Decimal] = {}
    breakdowns: dict[tuple[date, str, str], dict[str, Any]] = {}
    for key, by_type in raw_breakdowns.items():
        _w, sku, wh = key
        # AAH: never include SAMPLES (Sales Out = CUSTOMER only). BLP: include SAMPLES only when policy says.
        if wh == "AAH":
            include_samples = False
        else:
            include_samples = policy_include_samples.get((sku, wh), True)
        total, breakdown = build_actuals_breakdown(dict(by_type), include_samples)
        totals[key] = total
        breakdowns[key] = breakdown
    return dict(totals), dict(breakdowns)


def _baseline_by_week(db: Session, from_week: date, to_week: date) -> dict[tuple[date, str, str], Decimal]:
    """Get baseline forecast qty per planning week (Monday). week_start in table = target week (W-TUE); map Monday to W-TUE for lookup."""
    # Iterate Mondays in range
    out: dict[tuple[date, str, str], Decimal] = {}
    w = from_week
    while w <= to_week:
        week_tue = week_start_for_date(w)
        rows = (
            db.query(BaselineForecastWeekly)
            .filter(
                BaselineForecastWeekly.week_start == week_tue,
            )
            .all()
        )
        for r in rows:
            s = cast(str, r.sku)
            wh = cast(str, r.warehouse_code)
            q = cast(Decimal, r.forecast_qty)
            out[(w, s, wh)] = out.get((w, s, wh), Decimal("0")) + q
        w = _next_monday(w)
    return out


def _baseline_by_week_with_ref(
    db: Session, from_week: date, to_week: date
) -> tuple[dict[tuple[date, str, str], Decimal], dict[tuple[date, str, str], dict[str, Any]]]:
    """Same as _baseline_by_week but also return source_ref (model_name, model_version) per key for first row."""
    out: dict[tuple[date, str, str], Decimal] = {}
    refs: dict[tuple[date, str, str], dict[str, Any]] = {}
    w = from_week
    while w <= to_week:
        week_tue = week_start_for_date(w)
        rows = (
            db.query(BaselineForecastWeekly)
            .filter(BaselineForecastWeekly.week_start == week_tue)
            .all()
        )
        for r in rows:
            s = cast(str, r.sku)
            wh = cast(str, r.warehouse_code)
            q = cast(Decimal, r.forecast_qty)
            key = (w, s, wh)
            out[key] = out.get(key, Decimal("0")) + q
            if key not in refs:
                refs[key] = {
                    "model_name": getattr(r, "model_name", None),
                    "model_version": getattr(r, "model_version", None),
                }
        w = _next_monday(w)
    return out, refs


def get_latest_train_end_week_start(
    db: Session,
    warehouse_code: str = "AAH",
) -> date | None:
    """MAX(train_end_week_start) in published_baseline_forecasts_weekly for the given warehouse."""
    from sqlalchemy import func
    row = (
        db.query(func.max(PublishedBaselineForecastWeekly.train_end_week_start))
        .filter(PublishedBaselineForecastWeekly.warehouse_code == warehouse_code)
        .first()
    )
    return row[0] if row and row[0] is not None else None


def published_run_exists(db: Session, train_end_week_start: date, warehouse_code: str = "AAH") -> bool:
    """True if at least one row exists in published_baseline_forecasts_weekly for this train_end and warehouse."""
    return (
        db.query(PublishedBaselineForecastWeekly.id)
        .filter(
            PublishedBaselineForecastWeekly.train_end_week_start == train_end_week_start,
            PublishedBaselineForecastWeekly.warehouse_code == warehouse_code,
        )
        .limit(1)
        .first()
        is not None
    )


def _resolve_baseline_train_end(db: Session, run: PlanRun, warehouse_code: str = "AAH") -> date:
    """
    Choose train_end_week_start for baseline/blended: use selected (persisted), else user override, else latest.
    Persist to run.selected_train_end_week_start on first choice for reproducibility.
    Raises NoBaselineRunsError if no published runs exist when we need to pick latest.
    """
    selected = getattr(run, "selected_train_end_week_start", None)
    if selected is not None:
        return cast(date, selected)
    user_override = getattr(run, "baseline_train_end_week_start", None)
    if user_override is not None:
        if not published_run_exists(db, user_override, warehouse_code):
            raise NoBaselineRunsError(
                f"Selected forecast run {user_override!s} not found. Choose another run or reset to latest."
            )
        run.selected_train_end_week_start = user_override
        db.flush()
        return user_override
    latest = get_latest_train_end_week_start(db, warehouse_code=warehouse_code)
    if latest is None:
        raise NoBaselineRunsError("No baseline forecast runs available. Import forecast output first.")
    run.selected_train_end_week_start = latest
    db.flush()
    return latest


def _published_baseline_by_week(
    db: Session,
    from_week: date,
    to_week: date,
    train_end_week_start: date | None,
) -> tuple[dict[tuple[date, str, str], Decimal], dict[tuple[date, str, str], dict[str, Any]]]:
    """
    Get published baseline forecast qty per (Monday_week, sku, warehouse).
    train_end_week_start must be set by caller (resolver chooses it and may persist to plan_run.selected_train_end_week_start).
    """
    if train_end_week_start is None:
        return {}, {}
    out: dict[tuple[date, str, str], Decimal] = {}
    refs: dict[tuple[date, str, str], dict[str, Any]] = {}
    w = from_week
    while w <= to_week:
        week_tue = week_start_for_date(w)
        rows = (
            db.query(PublishedBaselineForecastWeekly)
            .filter(
                PublishedBaselineForecastWeekly.week_start == week_tue,
                PublishedBaselineForecastWeekly.train_end_week_start == train_end_week_start,
            )
            .all()
        )
        for r in rows:
            s = cast(str, r.sku)
            wh = cast(str, r.warehouse_code)
            q = cast(Decimal, r.forecast_qty)
            key = (w, s, wh)
            out[key] = q
            refs[key] = {
                "model_name": getattr(r, "selected_model_name", None),
                "model_version": getattr(r, "selected_model_version", None),
            }
        w = _next_monday(w)
    return out, refs


def _overrides_by_key(
    db: Session, plan_run_id: int
) -> dict[tuple[date, str, str], tuple[Decimal, str]]:
    """Return (override_qty, reason_code) per (week_start, sku, warehouse_code)."""
    rows = (
        db.query(DemandOverrideWeekly)
        .filter(DemandOverrideWeekly.plan_run_id == plan_run_id)
        .all()
    )
    return {
        (cast(date, r.week_start), cast(str, r.sku), cast(str, r.warehouse_code)): (
            cast(Decimal, r.override_qty),
            getattr(r, "reason_code", None) or "other",
        )
        for r in rows
    }


def resolve_demand_for_run(
    db: Session,
    plan_run_id: int,
    from_week: date,
    to_week: date,
    *,
    recompute_non_frozen_only: bool = True,
) -> None:
    """
    Build demand series for plan_run from demand_source (actuals/baseline/blended),
    apply overrides, preserve frozen rows. Write/upsert plan_run_demand_inputs_weekly.
    Freeze window is anchored to plan_start_week_start (W-TUE): first freeze_weeks weeks.
    Populates demand_breakdown_json for explainability (per demand_type or forecast_total/override).
    """
    run = db.query(PlanRun).filter(PlanRun.id == plan_run_id).first()
    if not run:
        raise ValueError(f"Plan run not found: {plan_run_id}")
    run_at = cast(date, run.run_at)
    run_week = _monday_before(run_at)
    demand_source = (getattr(run, "demand_source", None) or "actuals").lower()
    freeze_n = int(getattr(run, "freeze_weeks", 4) or 4)
    plan_start = getattr(run, "plan_start_week_start", None) or week_start_for_date(run_at)
    plan_start = cast(date, plan_start)
    frozen_mondays = _frozen_mondays_for_plan(plan_start, freeze_n)

    overrides = _overrides_by_key(db, plan_run_id)
    policy_rows = db.query(PlanningPolicy).all()
    policy_include_samples: dict[tuple[str, str], bool] = {
        (cast(str, p.sku), cast(str, p.warehouse_code)): bool(getattr(p, "include_samples", True))
        for p in policy_rows
    }

    base: dict[tuple[date, str, str], Decimal] = {}
    base_breakdowns: dict[tuple[date, str, str], dict[str, Any]] = {}
    base_refs: dict[tuple[date, str, str], dict[str, Any]] = {}
    base_includes_samples: dict[tuple[date, str, str], bool] = {}

    if demand_source == "actuals":
        base, base_breakdowns = _actuals_by_week_with_breakdown(db, from_week, to_week, policy_include_samples)
        base_source = "actuals"
        for (w, sku, wh) in base:
            base_includes_samples[(w, sku, wh)] = False if wh == "AAH" else policy_include_samples.get((sku, wh), True)
    elif demand_source == "baseline":
        train_end = _resolve_baseline_train_end(db, run, warehouse_code="AAH")
        base, base_refs = _published_baseline_by_week(db, from_week, to_week, train_end)
        for k, v in base.items():
            ref = base_refs.get(k, {})
            base_breakdowns[k] = {
                "FORECAST_TOTAL": float(v),
                "model": ref.get("model_name"),
                "model_version": ref.get("model_version"),
                "included_types": "forecast",
            }
        base_source = "baseline"
        for k in base:
            base_includes_samples[k] = True
    elif demand_source == "blended":
        actuals, actuals_breakdown = _actuals_by_week_with_breakdown(db, from_week, to_week, policy_include_samples)
        train_end = _resolve_baseline_train_end(db, run, warehouse_code="AAH")
        baseline, baseline_refs = _published_baseline_by_week(db, from_week, to_week, train_end)
        for k in set(actuals) | set(baseline):
            w, s, wh = k
            if w <= run_week:
                base[k] = actuals.get(k, Decimal("0"))
                base_breakdowns[k] = actuals_breakdown.get(k, {})
                base_includes_samples[k] = False if wh == "AAH" else policy_include_samples.get((s, wh), True)
            else:
                base[k] = baseline.get(k, Decimal("0"))
                ref = baseline_refs.get(k, {})
                base_breakdowns[k] = {
                    "FORECAST_TOTAL": float(base[k]),
                    "model": ref.get("model_name"),
                    "model_version": ref.get("model_version"),
                    "included_types": "forecast",
                }
                base_includes_samples[k] = True
            base_refs[k] = baseline_refs.get(k, {})
        base_source = "blended"
    else:
        base, base_breakdowns = _actuals_by_week_with_breakdown(db, from_week, to_week, policy_include_samples)
        base_source = "actuals"
        for (w, sku, wh) in base:
            base_includes_samples[(w, sku, wh)] = False if wh == "AAH" else policy_include_samples.get((sku, wh), True)

    all_keys = set(base) | set(overrides)
    if not all_keys:
        return

    existing_frozen: dict[tuple[date, str, str], tuple[Decimal, Any, Any, str, bool]] = {}
    if recompute_non_frozen_only:
        existing = (
            db.query(PlanRunDemandInputWeekly)
            .filter(
                PlanRunDemandInputWeekly.plan_run_id == plan_run_id,
                PlanRunDemandInputWeekly.week_start >= from_week,
                PlanRunDemandInputWeekly.week_start <= to_week,
                PlanRunDemandInputWeekly.is_frozen.is_(True),
            )
            .all()
        )
        for r in existing:
            k = (cast(date, r.week_start), cast(str, r.sku), cast(str, r.warehouse_code))
            existing_frozen[k] = (
                cast(Decimal, r.demand_qty),
                getattr(r, "source_ref", None),
                getattr(r, "demand_breakdown_json", None),
                getattr(r, "source", None) or "actuals",
                bool(getattr(r, "demand_includes_samples", True)),
            )

    for (w, sku, wh) in all_keys:
        in_freeze_window = w in frozen_mondays
        if (w, sku, wh) in overrides:
            override_qty, reason_code = overrides[(w, sku, wh)]
            demand_qty = override_qty
            source = "override"
            source_ref = None
            breakdown = {"OVERRIDE": float(demand_qty), "reason_code": reason_code}
            includes_samples = True
            is_frozen = (w, sku, wh) in existing_frozen or in_freeze_window
        elif (w, sku, wh) in existing_frozen:
            demand_qty, source_ref, prev_breakdown, prev_source, includes_samples = existing_frozen[(w, sku, wh)]
            source = prev_source
            breakdown = prev_breakdown if isinstance(prev_breakdown, dict) else {"preserved": float(demand_qty)}
            is_frozen = True
        else:
            demand_qty = base.get((w, sku, wh), Decimal("0"))
            source = base_source
            source_ref = base_refs.get((w, sku, wh))
            breakdown = base_breakdowns.get(
                (w, sku, wh),
                {"FORECAST_TOTAL": float(demand_qty), "included_types": "forecast"},
            )
            includes_samples = base_includes_samples.get((w, sku, wh), True)
            is_frozen = in_freeze_window

        existing_row = (
            db.query(PlanRunDemandInputWeekly)
            .filter(
                PlanRunDemandInputWeekly.plan_run_id == plan_run_id,
                PlanRunDemandInputWeekly.week_start == w,
                PlanRunDemandInputWeekly.sku == sku,
                PlanRunDemandInputWeekly.warehouse_code == wh,
            )
            .first()
        )
        if existing_row:
            if getattr(existing_row, "is_frozen", False):
                continue
            existing_row.demand_qty = demand_qty
            existing_row.source = source
            existing_row.source_ref = source_ref
            existing_row.demand_breakdown_json = breakdown
            existing_row.demand_includes_samples = includes_samples
        else:
            db.add(
                PlanRunDemandInputWeekly(
                    plan_run_id=plan_run_id,
                    week_start=w,
                    sku=sku,
                    warehouse_code=wh,
                    demand_qty=demand_qty,
                    source=source,
                    source_ref=source_ref,
                    demand_breakdown_json=breakdown,
                    demand_includes_samples=includes_samples,
                    is_frozen=is_frozen,
                )
            )
    db.flush()
