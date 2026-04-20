"""Tests: forecast output ingestion — unknown AAH rejected, multi-model ingested, selection published, planning uses published baseline.
Requires PostgreSQL (SQLite does not support UUID columns used by ingestion_runs). Use pytest with postgres URL or run against real DB.
"""
# pyright: reportMissingImports=false
from datetime import date
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    BaselineForecastWeekly,
    IngestionEntity,
    IngestionRejection,
    IngestionRun,
    IngestionSourceType,
    IngestionStatus,
    PlanRun,
    PlanRunDemandInputWeekly,
    Product,
    PublishedBaselineForecastWeekly,
    Warehouse,
)
from app.services.demand_resolver import NoBaselineRunsError, resolve_demand_for_run
from app.services.import_forecast_output import (
    _aah_to_sku_map,
    _get_cell,
    _parse_date,
    build_baseline_from_stage,
    import_from_stage,
    publish_baseline_from_stage,
    validate_and_stage_row,
)

def test_get_cell_returns_first_non_empty() -> None:
    """_get_cell returns first key present and non-empty."""
    row = {"a": "", "b": "val", "c": "other"}
    assert _get_cell(row, "a", "b", "c") == "val"
    assert _get_cell(row, "x", "b") == "val"
    assert _get_cell(row, "x", "y") is None


def test_parse_date_iso_and_slash() -> None:
    """_parse_date accepts YYYY-MM-DD and DD/MM/YYYY."""
    assert _parse_date("2025-01-07") == date(2025, 1, 7)
    assert _parse_date("07/01/2025") == date(2025, 1, 7)
    assert _parse_date("") is None
    assert _parse_date(None) is None


@pytest.fixture
def db_session():
    """Session for forecast output tests. Uses app.database engine (expects PostgreSQL)."""
    from app.database import engine
    if "sqlite" in (engine.url.drivername or ""):
        pytest.skip("Forecast output tests require PostgreSQL (UUID columns)")
    Session = sessionmaker(bind=engine, autoflush=True)
    session = Session()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


def test_unknown_aah_code_rejected(db_session) -> None:
    """Row with aah_product_code not in products.aah_code is rejected with reason unknown_aah_code."""
    run_id = uuid4()
    db_session.add(
        IngestionRun(
            id=run_id,
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.FORECAST_OUTPUT,
            status=IngestionStatus.PENDING,
            row_count=1,
        )
    )
    db_session.commit()
    # No product with aah_code = 'UNKNOWN-AAH'
    aah_to_sku = _aah_to_sku_map(db_session)
    row = {
        "AAH_Product_Code": "UNKNOWN-AAH",
        "Inference_Date": "2025-01-07",
        "Forecast_Week": "2025-01-14",
        "Model": "Prophet",
        "Forecast": 100,
    }
    ok, reason = validate_and_stage_row(db_session, run_id, row, 2, aah_to_sku)
    db_session.commit()
    assert ok is False
    assert reason == "unknown_aah_code"
    rej = db_session.query(IngestionRejection).filter(IngestionRejection.ingestion_run_id == run_id).first()
    assert rej is not None
    assert rej.reason == "unknown_aah_code"


def test_multiple_models_ingested(db_session) -> None:
    """Multiple model rows for same SKU are staged and written to baseline_forecasts_weekly."""
    u = uuid4().hex[:8]
    wh_code, sku, aah = f"WHFO{u}", f"SKUFA{u}", f"AAHFA{u}"
    # Product with aah_code (isolated keys: shared Postgres DB retains commits from other tests)
    db_session.add(Product(sku=sku, name="Product A", uom="units", active=True, aah_code=aah))
    db_session.add(Warehouse(code=wh_code, name="AAH", timezone="Europe/London", active=True))
    db_session.commit()
    run_id = uuid4()
    db_session.add(
        IngestionRun(
            id=run_id,
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.FORECAST_OUTPUT,
            status=IngestionStatus.PENDING,
            row_count=2,
        )
    )
    db_session.commit()
    aah_to_sku = _aah_to_sku_map(db_session)
    for i, model in enumerate(["Prophet", "ARIMA"]):
        row = {
            "AAH_Product_Code": aah,
            "Inference_Date": "2025-01-07",
            "Forecast_Week": "2025-01-14",
            "Model": model,
            "Model_Details": f"v{i}",
            "Forecast": 50.0 + i,
        }
        validate_and_stage_row(db_session, run_id, row, 2 + i, aah_to_sku)
    db_session.commit()
    baseline_count = build_baseline_from_stage(db_session, run_id)
    db_session.commit()
    assert baseline_count >= 2
    rows = (
        db_session.query(BaselineForecastWeekly)
        .filter(
            BaselineForecastWeekly.sku == sku,
            BaselineForecastWeekly.warehouse_code == wh_code,
            BaselineForecastWeekly.week_start == date(2025, 1, 14),
            BaselineForecastWeekly.train_end_week_start == date(2025, 1, 7),
        )
        .all()
    )
    models = {(r.model_name, r.model_version) for r in rows}
    assert ("Prophet", "v0") in models
    assert ("ARIMA", "v1") in models


def test_selected_model_series_published_deterministically(db_session) -> None:
    """When is_best_model is true for one model, that model's series is published."""
    u = uuid4().hex[:8]
    wh_code, sku, aah = f"WHFB{u}", f"SKUFB{u}", f"AAHFB{u}"
    db_session.add(Product(sku=sku, name="B", uom="units", active=True, aah_code=aah))
    db_session.add(Warehouse(code=wh_code, name="AAH", timezone="Europe/London", active=True))
    db_session.commit()
    run_id = uuid4()
    db_session.add(
        IngestionRun(
            id=run_id,
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.FORECAST_OUTPUT,
            status=IngestionStatus.PENDING,
            row_count=2,
        )
    )
    db_session.commit()
    aah_to_sku = _aah_to_sku_map(db_session)
    # Row 1: Prophet, not best
    row1 = {
        "AAH_Product_Code": aah,
        "Inference_Date": "2025-01-07",
        "Forecast_Week": "2025-01-14",
        "Model": "Prophet",
        "Forecast": 10.0,
        "Is_Best_Model": False,
    }
    # Row 2: ARIMA, best
    row2 = {
        "AAH_Product_Code": aah,
        "Inference_Date": "2025-01-07",
        "Forecast_Week": "2025-01-14",
        "Model": "ARIMA",
        "Forecast": 20.0,
        "Is_Best_Model": True,
    }
    validate_and_stage_row(db_session, run_id, row1, 2, aah_to_sku)
    validate_and_stage_row(db_session, run_id, row2, 3, aah_to_sku)
    db_session.commit()
    build_baseline_from_stage(db_session, run_id)
    db_session.commit()
    published_count = publish_baseline_from_stage(db_session, run_id)
    db_session.commit()
    assert published_count >= 1
    pub = (
        db_session.query(PublishedBaselineForecastWeekly)
        .filter(
            PublishedBaselineForecastWeekly.sku == sku,
            PublishedBaselineForecastWeekly.train_end_week_start == date(2025, 1, 7),
            PublishedBaselineForecastWeekly.week_start == date(2025, 1, 14),
        )
        .first()
    )
    assert pub is not None
    assert pub.selected_model_name == "ARIMA"
    assert float(pub.forecast_qty) == 20.0


def test_planning_demand_source_baseline_uses_published(db_session) -> None:
    """When plan_run.demand_source=baseline, resolve_demand pulls from published_baseline_forecasts_weekly."""
    u = uuid4().hex[:8]
    wh_code, sku, aah = f"WHFC{u}", f"SKUFC{u}", f"AAHFC{u}"
    db_session.add(Product(sku=sku, name="C", uom="units", active=True, aah_code=aah))
    db_session.add(Warehouse(code=wh_code, name="AAH", timezone="Europe/London", active=True))
    db_session.commit()
    train_end = date(2025, 1, 7)
    # week_start in published = W-TUE (Tuesday); Monday 2025-01-13 falls in week starting 2025-01-07
    db_session.add(
        PublishedBaselineForecastWeekly(
            sku=sku,
            warehouse_code=wh_code,
            week_start=date(2025, 1, 7),  # W-TUE week containing Mon 2025-01-13
            forecast_qty=Decimal("100"),
            train_end_week_start=train_end,
            selected_model_name="Prophet",
            selected_model_version="1.0",
        )
    )
    db_session.commit()
    run = PlanRun(
        scenario_name="Baseline test",
        run_at=date(2025, 1, 10),
        created_at=date(2025, 1, 10),
        demand_source="baseline",
        freeze_weeks=4,
        plan_start_week_start=date(2025, 1, 7),  # W-TUE
        baseline_train_end_week_start=train_end,
    )
    db_session.add(run)
    db_session.commit()
    plan_run_id = run.id
    from_week = date(2025, 1, 13)
    to_week = date(2025, 1, 20)
    plan_run_id = cast(int, run.id)
    resolve_demand_for_run(db_session, plan_run_id, from_week, to_week, recompute_non_frozen_only=False)
    db_session.commit()
    demand_row = (
        db_session.query(PlanRunDemandInputWeekly)
        .filter(
            PlanRunDemandInputWeekly.plan_run_id == plan_run_id,
            PlanRunDemandInputWeekly.sku == sku,
            PlanRunDemandInputWeekly.warehouse_code == wh_code,
        )
        .first()
    )
    assert demand_row is not None
    assert float(demand_row.demand_qty) == 100.0


def test_baseline_selects_max_train_end_when_multiple_runs(db_session) -> None:
    """When multiple published runs exist, resolver selects MAX(train_end_week_start) and persists to selected_train_end_week_start."""
    u = uuid4().hex[:8]
    wh_code, sku, aah = f"WHFD{u}", f"SKUFD{u}", f"AAHFD{u}"
    db_session.add(Product(sku=sku, name="D", uom="units", active=True, aah_code=aah))
    db_session.add(Warehouse(code=wh_code, name="AAH", timezone="Europe/London", active=True))
    db_session.commit()
    older = date(2025, 1, 7)
    newer = date(2025, 2, 4)
    for train_end in (older, newer):
        db_session.add(
            PublishedBaselineForecastWeekly(
                sku=sku,
                warehouse_code=wh_code,
                week_start=date(2025, 1, 7),
                forecast_qty=Decimal("50"),
                train_end_week_start=train_end,
                selected_model_name="Prophet",
                selected_model_version="1.0",
            )
        )
    db_session.commit()
    run = PlanRun(
        scenario_name="Max selection",
        run_at=date(2025, 1, 15),
        created_at=date(2025, 1, 15),
        demand_source="baseline",
        freeze_weeks=4,
        plan_start_week_start=date(2025, 1, 7),
        selected_train_end_week_start=None,
        baseline_train_end_week_start=None,
    )
    db_session.add(run)
    db_session.commit()
    plan_run_id = cast(int, run.id)
    resolve_demand_for_run(db_session, plan_run_id, date(2025, 1, 13), date(2025, 1, 20), recompute_non_frozen_only=False)
    db_session.commit()
    db_session.refresh(run)
    assert getattr(run, "selected_train_end_week_start", None) == newer


def test_baseline_reuses_persisted_selected_run(db_session) -> None:
    """After selection is persisted, re-running planning uses the same selected run even if a newer run is ingested."""
    u = uuid4().hex[:8]
    wh_code, sku, aah = f"WHFE{u}", f"SKUFE{u}", f"AAHFE{u}"
    db_session.add(Product(sku=sku, name="E", uom="units", active=True, aah_code=aah))
    db_session.add(Warehouse(code=wh_code, name="AAH", timezone="Europe/London", active=True))
    db_session.commit()
    first_run = date(2025, 1, 7)
    db_session.add(
        PublishedBaselineForecastWeekly(
            sku=sku,
            warehouse_code=wh_code,
            week_start=date(2025, 1, 7),
            forecast_qty=Decimal("60"),
            train_end_week_start=first_run,
            selected_model_name="Prophet",
            selected_model_version="1.0",
        )
    )
    db_session.commit()
    run = PlanRun(
        scenario_name="Persisted reuse",
        run_at=date(2025, 1, 10),
        created_at=date(2025, 1, 10),
        demand_source="baseline",
        freeze_weeks=4,
        plan_start_week_start=date(2025, 1, 7),
        selected_train_end_week_start=None,
        baseline_train_end_week_start=None,
    )
    db_session.add(run)
    db_session.commit()
    plan_run_id = cast(int, run.id)
    resolve_demand_for_run(db_session, plan_run_id, date(2025, 1, 13), date(2025, 1, 20), recompute_non_frozen_only=False)
    db_session.commit()
    db_session.refresh(run)
    assert getattr(run, "selected_train_end_week_start", None) == first_run
    # Ingest a newer run
    newer = date(2025, 2, 4)
    db_session.add(
        PublishedBaselineForecastWeekly(
            sku=sku,
            warehouse_code=wh_code,
            week_start=date(2025, 1, 7),
            forecast_qty=Decimal("99"),
            train_end_week_start=newer,
            selected_model_name="Prophet",
            selected_model_version="2.0",
        )
    )
    db_session.commit()
    # Re-run resolve; should still use first_run (persisted)
    resolve_demand_for_run(db_session, plan_run_id, date(2025, 1, 13), date(2025, 1, 20), recompute_non_frozen_only=False)
    db_session.commit()
    db_session.refresh(run)
    assert getattr(run, "selected_train_end_week_start", None) == first_run
    demand_row = (
        db_session.query(PlanRunDemandInputWeekly)
        .filter(
            PlanRunDemandInputWeekly.plan_run_id == plan_run_id,
            PlanRunDemandInputWeekly.sku == sku,
            PlanRunDemandInputWeekly.warehouse_code == wh_code,
        )
        .first()
    )
    assert demand_row is not None
    assert float(demand_row.demand_qty) == 60.0


def test_baseline_no_runs_raises_clear_error(db_session) -> None:
    """When no published baseline runs exist, baseline planning raises NoBaselineRunsError with clear message."""
    run = PlanRun(
        scenario_name="No runs",
        run_at=date(2025, 1, 10),
        created_at=date(2025, 1, 10),
        demand_source="baseline",
        freeze_weeks=4,
        plan_start_week_start=date(2025, 1, 7),
        selected_train_end_week_start=None,
        baseline_train_end_week_start=None,
    )
    db_session.add(run)
    db_session.commit()
    plan_run_id = cast(int, run.id)
    with pytest.raises(NoBaselineRunsError) as exc_info:
        resolve_demand_for_run(db_session, plan_run_id, date(2025, 1, 13), date(2025, 1, 20), recompute_non_frozen_only=False)
    assert "No baseline forecast runs available" in str(exc_info.value)
    assert "Import forecast output" in str(exc_info.value)
