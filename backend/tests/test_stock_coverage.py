"""Tests: Stock coverage report calculation (status_bucket, weeks_cover, demand filter)."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.database import engine
from app.models import DemandActual, DemandType, InventorySnapshotWeekly, Product, Warehouse
from app.services.stock_coverage import (
    _demand_types_for_warehouse,
    _status_bucket,
    compute_stock_coverage,
)


def _soh_available() -> bool:
    from sqlalchemy import inspect
    try:
        with engine.connect() as conn:
            return "inventory_snapshots_weekly" in inspect(conn).get_table_names()
    except Exception:
        return False


# --- Unit tests (no DB) ---


def test_status_bucket_critical() -> None:
    assert _status_bucket(Decimal("0")) == "Critical"
    assert _status_bucket(Decimal("1.5")) == "Critical"


def test_status_bucket_low() -> None:
    assert _status_bucket(Decimal("2")) == "Low"
    assert _status_bucket(Decimal("3.9")) == "Low"


def test_status_bucket_monitor() -> None:
    assert _status_bucket(Decimal("4")) == "Monitor"
    assert _status_bucket(Decimal("7.9")) == "Monitor"


def test_status_bucket_healthy() -> None:
    assert _status_bucket(Decimal("8")) == "Healthy"
    assert _status_bucket(Decimal("100")) == "Healthy"


def test_status_bucket_no_demand() -> None:
    assert _status_bucket(None) == "No demand"


def test_demand_types_aah() -> None:
    assert _demand_types_for_warehouse("AAH") == [DemandType.CUSTOMER]
    assert _demand_types_for_warehouse("aah") == [DemandType.CUSTOMER]


def test_demand_types_blp() -> None:
    assert _demand_types_for_warehouse("BLP") == [DemandType.CUSTOMER, DemandType.SAMPLES]
    assert _demand_types_for_warehouse("blp") == [DemandType.CUSTOMER, DemandType.SAMPLES]


def test_demand_types_unknown() -> None:
    assert _demand_types_for_warehouse("XYZ") == [DemandType.CUSTOMER]


# --- Integration tests (real DB, not SQLite) ---


@pytest.fixture
def db_session():
    if "sqlite" in (engine.url.drivername or ""):
        pytest.skip("Stock coverage tests require a non-SQLite DB (e.g. MySQL)")
    Session = sessionmaker(bind=engine, autoflush=True)
    session = Session()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


def _ensure_warehouses(db) -> None:
    for code in ["AAH", "BLP"]:
        if not db.query(Warehouse).filter(Warehouse.code == code).first():
            db.add(Warehouse(code=code, name=code, timezone="Europe/London", active=True))
    db.commit()


def _ensure_warehouse(db, code: str) -> None:
    """Ensure a warehouse exists (for isolated tests)."""
    if not db.query(Warehouse).filter(Warehouse.code == code).first():
        db.add(Warehouse(code=code, name=code, timezone="Europe/London", active=True))
    db.commit()


@pytest.mark.skipif(not _soh_available(), reason="inventory_snapshots_weekly not available")
def test_compute_stock_coverage_weeks_cover_calculation(db_session) -> None:
    """weeks_cover = on_hand_qty / avg_weekly_demand; status_bucket correct."""
    db = db_session
    # Use isolated warehouse so latest_week is not affected by other test data
    wh = "STKCOV-WH"
    _ensure_warehouse(db, wh)

    sku = "STKCOV-TEST-1"
    if not db.query(Product).filter(Product.sku == sku).first():
        db.add(Product(sku=sku, name="Test", uom="units", active=True))
    db.commit()

    w = date(2025, 2, 18)  # W-TUE
    # SOH: 100 units
    existing = db.query(InventorySnapshotWeekly).filter(
        InventorySnapshotWeekly.sku == sku,
        InventorySnapshotWeekly.warehouse_code == wh,
        InventorySnapshotWeekly.week_start == w,
    ).first()
    if not existing:
        db.add(InventorySnapshotWeekly(
            week_start=w,
            sku=sku,
            warehouse_code=wh,
            on_hand_qty=Decimal("100"),
            source_type="soh",
        ))
    db.commit()

    # Demand: 10 per week for 4 weeks = avg 10
    for i in range(4):
        wk = w - timedelta(days=i * 7)
        if not db.query(DemandActual).filter(
            DemandActual.sku == sku,
            DemandActual.warehouse_code == wh,
            DemandActual.week_start == wk,
            DemandActual.demand_type == DemandType.CUSTOMER,
        ).first():
            db.add(DemandActual(
                week_start=wk,
                sku=sku,
                warehouse_code=wh,
                demand_type=DemandType.CUSTOMER,
                qty=Decimal("10"),
            ))
    db.commit()

    result = compute_stock_coverage(db, warehouse_code=wh, weeks_window=4)
    assert "summary" in result
    assert "rows" in result

    rows = [r for r in result["rows"] if r["sku"] == sku]
    assert len(rows) == 1
    r = rows[0]
    assert r["on_hand_qty"] == 100.0
    # total demand 40 over 4 weeks = avg 10
    assert r["avg_weekly_demand"] == 10.0
    assert r["weeks_cover"] == 10.0  # 100/10
    assert r["status_bucket"] == "Healthy"


@pytest.mark.skipif(not _soh_available(), reason="inventory_snapshots_weekly not available")
def test_compute_stock_coverage_no_demand(db_session) -> None:
    """When avg demand = 0, weeks_cover = null, status = No demand."""
    db = db_session
    _ensure_warehouses(db)

    sku = "STKCOV-NODEMAND"
    if not db.query(Product).filter(Product.sku == sku).first():
        db.add(Product(sku=sku, name="No demand test", uom="units", active=True))
    db.commit()

    w = date(2025, 2, 18)
    if not db.query(InventorySnapshotWeekly).filter(
        InventorySnapshotWeekly.sku == sku,
        InventorySnapshotWeekly.warehouse_code == "AAH",
        InventorySnapshotWeekly.week_start == w,
    ).first():
        db.add(InventorySnapshotWeekly(
            week_start=w,
            sku=sku,
            warehouse_code="AAH",
            on_hand_qty=Decimal("50"),
            source_type="soh",
        ))
    db.commit()
    # No demand_actuals for this SKU

    result = compute_stock_coverage(db, warehouse_code="AAH", weeks_window=13)
    rows = [r for r in result["rows"] if r["sku"] == sku]
    assert len(rows) == 1
    r = rows[0]
    assert r["avg_weekly_demand"] == 0.0
    assert r["weeks_cover"] is None
    assert r["status_bucket"] == "No demand"


@pytest.mark.skipif(not _soh_available(), reason="inventory_snapshots_weekly not available")
def test_compute_stock_coverage_aah_excludes_samples(db_session) -> None:
    """AAH uses CUSTOMER only; SAMPLES not included in avg demand."""
    db = db_session
    _ensure_warehouses(db)

    sku = "STKCOV-AAH-SAMPLES"
    if not db.query(Product).filter(Product.sku == sku).first():
        db.add(Product(sku=sku, name="AAH samples test", uom="units", active=True))
    db.commit()

    # Use far-future date so our SOH is the latest for AAH (avoids other test data)
    w = date(2030, 2, 18)
    if not db.query(InventorySnapshotWeekly).filter(
        InventorySnapshotWeekly.sku == sku,
        InventorySnapshotWeekly.warehouse_code == "AAH",
        InventorySnapshotWeekly.week_start == w,
    ).first():
        db.add(InventorySnapshotWeekly(
            week_start=w,
            sku=sku,
            warehouse_code="AAH",
            on_hand_qty=Decimal("20"),
            source_type="soh",
        ))
    db.commit()

    # CUSTOMER: 5/week; SAMPLES: 5/week. AAH should use only CUSTOMER -> avg 5
    for i in range(4):
        wk = w - timedelta(days=i * 7)
        for dt in [DemandType.CUSTOMER, DemandType.SAMPLES]:
            if not db.query(DemandActual).filter(
                DemandActual.sku == sku,
                DemandActual.warehouse_code == "AAH",
                DemandActual.week_start == wk,
                DemandActual.demand_type == dt,
            ).first():
                db.add(DemandActual(
                    week_start=wk,
                    sku=sku,
                    warehouse_code="AAH",
                    demand_type=dt,
                    qty=Decimal("5"),
                ))
    db.commit()

    result = compute_stock_coverage(db, warehouse_code="AAH", weeks_window=4)
    rows = [r for r in result["rows"] if r["sku"] == sku]
    assert len(rows) == 1
    r = rows[0]
    # AAH excludes SAMPLES: total CUSTOMER 20 over 4 weeks = avg 5
    assert r["avg_weekly_demand"] == 5.0
    assert r["weeks_cover"] == 4.0  # 20/5
    assert r["status_bucket"] == "Monitor"
