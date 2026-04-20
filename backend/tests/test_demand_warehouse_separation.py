"""Tests: AAH never includes SAMPLES; BLP includes SAMPLES only when include_samples=True."""
# pyright: reportMissingImports=false
from datetime import date
from typing import cast

import pytest
from decimal import Decimal
from sqlalchemy.orm import sessionmaker

from app.database import engine
from app.models import (
    DemandActual,
    DemandType,
    PlanRun,
    PlanRunDemandInputWeekly,
    PlanningPolicy,
    Product,
    Warehouse,
)
from app.services.demand_resolver import _actuals_by_week_with_breakdown, resolve_demand_for_run


@pytest.fixture
def db_session():
    """Session for demand warehouse separation tests."""
    if "sqlite" in (engine.url.drivername or ""):
        pytest.skip("Demand warehouse separation tests require a non-SQLite DB (e.g. MySQL)")
    Session = sessionmaker(bind=engine, autoflush=True)
    session = Session()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


def _ensure_warehouses(db):
    """Ensure AAH and BLP exist."""
    for code in ["AAH", "BLP"]:
        if not db.query(Warehouse).filter(Warehouse.code == code).first():
            db.add(Warehouse(code=code, name=code, timezone="Europe/London", active=True))
    db.commit()


def test_aah_never_includes_samples_in_breakdown(db_session) -> None:
    """AAH: _actuals_by_week_with_breakdown excludes SAMPLES even when policy has include_samples=True."""
    _ensure_warehouses(db_session)
    db = db_session
    db.add(Product(sku="SKU-A", name="P", uom="units", active=True))
    db.add(
        PlanningPolicy(
            sku="SKU-A",
            warehouse_code="AAH",
            include_samples=True,  # Policy says include, but AAH must ignore
            target_weeks=Decimal("4"),
        )
    )
    db.commit()

    w = date(2025, 2, 17)
    db.add(
        DemandActual(
            week_start=w,
            sku="SKU-A",
            warehouse_code="AAH",
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("100"),
        )
    )
    db.add(
        DemandActual(
            week_start=w,
            sku="SKU-A",
            warehouse_code="AAH",
            demand_type=DemandType.SAMPLES,
            qty=Decimal("20"),
        )
    )
    db.commit()

    policy_include_samples = {("SKU-A", "AAH"): True}
    totals, breakdowns = _actuals_by_week_with_breakdown(
        db, w, w, policy_include_samples
    )
    key = (w, "SKU-A", "AAH")
    assert key in totals
    assert totals[key] == Decimal("100")  # CUSTOMER only, SAMPLES excluded
    assert breakdowns[key]["included"] == ["CUSTOMER", "ADJUSTMENT"]
    assert "SAMPLES" in breakdowns[key]["excluded"]


def test_blp_includes_samples_when_policy_true(db_session) -> None:
    """BLP: _actuals_by_week_with_breakdown includes SAMPLES when include_samples=True."""
    _ensure_warehouses(db_session)
    db = db_session
    db.add(Product(sku="SKU-B", name="P", uom="units", active=True))
    db.add(
        PlanningPolicy(
            sku="SKU-B",
            warehouse_code="BLP",
            include_samples=True,
            target_weeks=Decimal("4"),
        )
    )
    db.commit()

    w = date(2025, 2, 17)
    db.add(
        DemandActual(
            week_start=w,
            sku="SKU-B",
            warehouse_code="BLP",
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("50"),
        )
    )
    db.add(
        DemandActual(
            week_start=w,
            sku="SKU-B",
            warehouse_code="BLP",
            demand_type=DemandType.SAMPLES,
            qty=Decimal("10"),
        )
    )
    db.commit()

    policy_include_samples = {("SKU-B", "BLP"): True}
    totals, breakdowns = _actuals_by_week_with_breakdown(
        db, w, w, policy_include_samples
    )
    key = (w, "SKU-B", "BLP")
    assert key in totals
    assert totals[key] == Decimal("60")  # CUSTOMER + SAMPLES
    assert "SAMPLES" in breakdowns[key]["included"]


def test_blp_excludes_samples_when_policy_false(db_session) -> None:
    """BLP: _actuals_by_week_with_breakdown excludes SAMPLES when include_samples=False."""
    _ensure_warehouses(db_session)
    db = db_session
    db.add(Product(sku="SKU-C", name="P", uom="units", active=True))
    db.add(
        PlanningPolicy(
            sku="SKU-C",
            warehouse_code="BLP",
            include_samples=False,
            target_weeks=Decimal("4"),
        )
    )
    db.commit()

    w = date(2025, 2, 17)
    db.add(
        DemandActual(
            week_start=w,
            sku="SKU-C",
            warehouse_code="BLP",
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("30"),
        )
    )
    db.add(
        DemandActual(
            week_start=w,
            sku="SKU-C",
            warehouse_code="BLP",
            demand_type=DemandType.SAMPLES,
            qty=Decimal("5"),
        )
    )
    db.commit()

    policy_include_samples = {("SKU-C", "BLP"): False}
    totals, breakdowns = _actuals_by_week_with_breakdown(
        db, w, w, policy_include_samples
    )
    key = (w, "SKU-C", "BLP")
    assert key in totals
    assert totals[key] == Decimal("30")  # CUSTOMER only
    assert "SAMPLES" in breakdowns[key]["excluded"]


def test_resolve_demand_aah_excludes_samples(db_session) -> None:
    """resolve_demand_for_run: AAH demand excludes SAMPLES in plan_run_demand_inputs_weekly."""
    _ensure_warehouses(db_session)
    db = db_session
    db.add(Product(sku="SKU-D", name="P", uom="units", active=True))
    db.add(
        PlanningPolicy(
            sku="SKU-D",
            warehouse_code="AAH",
            include_samples=True,
            target_weeks=Decimal("4"),
        )
    )
    db.commit()

    w = date(2025, 2, 17)
    db.add(
        DemandActual(
            week_start=w,
            sku="SKU-D",
            warehouse_code="AAH",
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("80"),
        )
    )
    db.add(
        DemandActual(
            week_start=w,
            sku="SKU-D",
            warehouse_code="AAH",
            demand_type=DemandType.SAMPLES,
            qty=Decimal("15"),
        )
    )
    run = PlanRun(
        scenario_name="test",
        run_at=w,
        created_at=w,
        demand_source="actuals",
        freeze_weeks=0,
        plan_start_week_start=w,
    )
    db.add(run)
    db.commit()

    resolve_demand_for_run(db, cast(int, run.id), w, w, recompute_non_frozen_only=False)

    row = (
        db.query(PlanRunDemandInputWeekly)
        .filter(
            PlanRunDemandInputWeekly.plan_run_id == run.id,
            PlanRunDemandInputWeekly.sku == "SKU-D",
            PlanRunDemandInputWeekly.warehouse_code == "AAH",
        )
        .first()
    )
    assert row is not None
    assert float(row.demand_qty) == 80.0  # CUSTOMER only, SAMPLES excluded
    assert row.demand_includes_samples is False
