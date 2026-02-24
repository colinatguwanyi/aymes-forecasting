"""Tests: forecast runs list, reset-forecast-run, PATCH override validation (409 when run not found)."""
from __future__ import annotations

from datetime import date

from app.database import SessionLocal
from app.models import PlanRun


def test_list_forecast_runs_orders_desc_and_counts(client, admin_headers) -> None:
    """GET /api/forecast/runs returns list ordered by train_end_week_start desc; each item has count_rows."""
    r = client.get("/api/forecast/runs", params={"warehouse_code": "AAH"}, headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    for i, item in enumerate(data):
        assert "train_end_week_start" in item
        assert "count_rows" in item
        if i < len(data) - 1:
            # Desc order: current >= next
            cur = item["train_end_week_start"]
            nxt = data[i + 1]["train_end_week_start"]
            assert cur >= nxt, f"Expected desc order: {cur} >= {nxt}"


def test_reset_forecast_run_clears_selected_only_by_default(client, admin_headers) -> None:
    """POST reset-forecast-run (default reset_all=false) clears selected_train_end_week_start only."""
    db = SessionLocal()
    plan_run_id = None
    try:
        run_date = date.today()
        run = PlanRun(
            scenario_name="test_reset_selected",
            run_at=run_date,
            created_at=run_date,
            demand_source="baseline",
            freeze_weeks=4,
            plan_start_week_start=run_date,
            selected_train_end_week_start=date(2025, 1, 6),
            baseline_train_end_week_start=date(2025, 1, 6),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        plan_run_id = run.id

        r = client.post(f"/api/plan/runs/{plan_run_id}/reset-forecast-run", headers=admin_headers)
        assert r.status_code == 200
        out = r.json()
        assert out.get("selected_train_end_week_start") is None
        assert out.get("baseline_train_end_week_start") == "2025-01-06"
    finally:
        if plan_run_id is not None:
            db.query(PlanRun).filter(PlanRun.id == plan_run_id).delete()
            db.commit()
        db.close()


def test_reset_forecast_run_reset_all_clears_selected_and_baseline_override(client, admin_headers) -> None:
    """POST reset-forecast-run?reset_all=true clears both selected and baseline_train_end_week_start."""
    db = SessionLocal()
    plan_run_id = None
    try:
        run_date = date.today()
        run = PlanRun(
            scenario_name="test_reset_all",
            run_at=run_date,
            created_at=run_date,
            demand_source="baseline",
            freeze_weeks=4,
            plan_start_week_start=run_date,
            selected_train_end_week_start=date(2025, 1, 6),
            baseline_train_end_week_start=date(2025, 1, 6),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        plan_run_id = run.id

        r = client.post(f"/api/plan/runs/{plan_run_id}/reset-forecast-run", params={"reset_all": "true"}, headers=admin_headers)
        assert r.status_code == 200
        out = r.json()
        assert out.get("selected_train_end_week_start") is None
        assert out.get("baseline_train_end_week_start") is None
    finally:
        if plan_run_id is not None:
            db.query(PlanRun).filter(PlanRun.id == plan_run_id).delete()
            db.commit()
        db.close()


def test_override_run_not_found_returns_409_clear_message(client, admin_headers) -> None:
    """PATCH with baseline_train_end_week_start that does not exist in published runs returns 409 with clear message."""
    db = SessionLocal()
    plan_run_id = None
    try:
        run_date = date.today()
        run = PlanRun(
            scenario_name="test_override_409",
            run_at=run_date,
            created_at=run_date,
            demand_source="baseline",
            freeze_weeks=4,
            plan_start_week_start=run_date,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        plan_run_id = run.id

        # Use a date that will not exist in published_baseline_forecasts_weekly (e.g. far past)
        r = client.patch(
            f"/api/plan/runs/{plan_run_id}",
            params={"baseline_train_end_week_start": "1999-01-04"},
            headers=admin_headers,
        )
        assert r.status_code == 409
        data = r.json()
        assert "detail" in data
        detail = data["detail"]
        assert "1999-01-04" in detail or "not found" in detail.lower()
        assert "reset" in detail.lower() or "choose" in detail.lower()
    finally:
        if plan_run_id is not None:
            db.query(PlanRun).filter(PlanRun.id == plan_run_id).delete()
            db.commit()
        db.close()
