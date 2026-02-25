"""Tests: warehouse-scoped planning — readiness endpoint, run_plan with scope [AAH], [BLP], [AAH,BLP]."""
# pyright: reportMissingImports=false
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.database import engine
from app.models import (
    DemandActual,
    DemandType,
    InventorySnapshotWeekly,
    PlanningPolicy,
    Product,
    ProjectedInventory,
    Warehouse,
)
from app.services.planning import AllWarehousesSkippedError, run_plan
from app.services.warehouse_readiness import check_planning_readiness


@pytest.fixture
def db_session():
    """Session for warehouse scope tests. Uses app.database engine."""
    if "sqlite" in (engine.url.drivername or ""):
        pytest.skip("Warehouse scope tests require PostgreSQL (JSONB)")
    Session = sessionmaker(bind=engine, autoflush=True)
    session = Session()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


def _ensure_aah_blp(db):
    """Ensure AAH and BLP warehouses exist."""
    for code in ["AAH", "BLP"]:
        if not db.query(Warehouse).filter(Warehouse.code == code).first():
            db.add(Warehouse(code=code, name=code, timezone="Europe/London", active=True))
    db.commit()


def test_readiness_only_aah_has_data(db_session) -> None:
    """When only AAH has SOH/demand/policies, readiness returns correct flags."""
    _ensure_aah_blp(db_session)
    db = db_session
    db.add(Product(sku="SKU1", name="P1", uom="units", active=True))
    db.commit()
    db.add(
        PlanningPolicy(
            sku="SKU1",
            warehouse_code="AAH",
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    db.add(
        InventorySnapshotWeekly(
            week_start=date(2025, 2, 17),
            sku="SKU1",
            warehouse_code="AAH",
            on_hand_qty=Decimal("100"),
            source_type="soh",
        )
    )
    db.add(
        DemandActual(
            week_start=date(2025, 2, 17),
            sku="SKU1",
            warehouse_code="AAH",
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("10"),
        )
    )
    db.commit()

    readiness = check_planning_readiness(db, demand_source="actuals")
    aa = next((r for r in readiness if r["warehouse_code"] == "AAH"), None)
    bl = next((r for r in readiness if r["warehouse_code"] == "BLP"), None)
    assert aa is not None
    assert aa["ready"] is True
    assert aa["has_soh"] is True
    assert aa["has_demand"] is True
    assert aa["has_policies"] is True
    if bl:
        assert bl["ready"] is False
        assert "No SOH" in str(bl.get("blockers", []))


def test_run_plan_scope_aah_produces_rows(db_session) -> None:
    """run_plan with scope [AAH] produces projected_inventory rows when AAH has data."""
    _ensure_aah_blp(db_session)
    db = db_session
    db.add(Product(sku="SKU2", name="P2", uom="units", active=True))
    db.commit()
    db.add(
        PlanningPolicy(
            sku="SKU2",
            warehouse_code="AAH",
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    db.add(
        InventorySnapshotWeekly(
            week_start=date(2025, 2, 17),
            sku="SKU2",
            warehouse_code="AAH",
            on_hand_qty=Decimal("100"),
            source_type="soh",
        )
    )
    db.add(
        DemandActual(
            week_start=date(2025, 2, 17),
            sku="SKU2",
            warehouse_code="AAH",
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("10"),
        )
    )
    db.commit()

    run = run_plan(db, "baseline", demand_source="actuals", warehouses_scope=["AAH"])
    db.refresh(run)
    proj_count = db.query(ProjectedInventory).filter(ProjectedInventory.plan_run_id == run.id).count()
    assert proj_count > 0
    assert run.progress_meta is not None
    assert "AAH" in (run.progress_meta.get("warehouses_planned") or [])


def test_run_plan_scope_blp_not_ready_returns_400(db_session) -> None:
    """run_plan with scope [BLP] when BLP has no SOH/demand/policies raises AllWarehousesSkippedError."""
    _ensure_aah_blp(db_session)
    db = db_session
    db.add(Product(sku="SKU3", name="P3", uom="units", active=True))
    db.commit()
    # No policies, SOH, or demand for BLP

    with pytest.raises(AllWarehousesSkippedError) as exc_info:
        run_plan(db, "baseline", demand_source="actuals", warehouses_scope=["BLP"])
    assert len(exc_info.value.skipped_warehouses) >= 1
    assert any(s["warehouse_code"] == "BLP" for s in exc_info.value.skipped_warehouses)


def test_run_plan_scope_aah_blp_plans_aah_skips_blp(db_session) -> None:
    """run_plan with scope [AAH, BLP]: plans AAH, records BLP skipped."""
    _ensure_aah_blp(db_session)
    db = db_session
    db.add(Product(sku="SKU4", name="P4", uom="units", active=True))
    db.commit()
    db.add(
        PlanningPolicy(
            sku="SKU4",
            warehouse_code="AAH",
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    db.add(
        InventorySnapshotWeekly(
            week_start=date(2025, 2, 17),
            sku="SKU4",
            warehouse_code="AAH",
            on_hand_qty=Decimal("100"),
            source_type="soh",
        )
    )
    db.add(
        DemandActual(
            week_start=date(2025, 2, 17),
            sku="SKU4",
            warehouse_code="AAH",
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("10"),
        )
    )
    db.commit()

    run = run_plan(db, "baseline", demand_source="actuals", warehouses_scope=["AAH", "BLP"])
    db.refresh(run)
    proj_count = db.query(ProjectedInventory).filter(ProjectedInventory.plan_run_id == run.id).count()
    assert proj_count > 0
    assert run.progress_meta is not None
    assert "AAH" in (run.progress_meta.get("warehouses_planned") or [])
    assert "BLP" in (run.progress_meta.get("warehouses_skipped") or [])
