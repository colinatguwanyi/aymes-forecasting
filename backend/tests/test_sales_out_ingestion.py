"""Tests: Sales Out ingestion — date parsing DD/MM/YYYY, unknown AAH rejected, aggregation, idempotency.

Requires migration 014 (sales_out_stage, ingestion_entity_enum 'sales_out') to be applied.
Tests that need the DB are skipped if the enum value or table is missing.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest  # type: ignore[reportMissingImports]

from app.database import SessionLocal
from app.models import DemandActual, DemandType, IngestionEntity, IngestionRejection, IngestionRun, IngestionSourceType, IngestionStatus, Product, SalesOutStage, Warehouse
from app.services.csv_import import parse_date_ddmmyyyy
from app.services.sales_out_ingestion import build_demand_from_sales_out


def _sales_out_schema_available() -> bool:
    """True if migration 014 table exists. Works for Postgres, MySQL, SQLite."""
    try:
        from sqlalchemy import inspect

        from app.database import engine

        insp = inspect(engine)
        return "sales_out_stage" in set(insp.get_table_names())
    except Exception:
        return False


def test_parse_date_ddmmyyyy() -> None:
    """DD/MM/YYYY parses correctly; invalid returns error."""
    ok, val = parse_date_ddmmyyyy("25/12/2024")
    assert ok is True
    assert val == date(2024, 12, 25)

    ok2, val2 = parse_date_ddmmyyyy("01/01/2025")
    assert ok2 is True
    assert val2 == date(2025, 1, 1)

    ok3, val3 = parse_date_ddmmyyyy("")
    assert ok3 is False
    assert "Empty" in str(val3)

    ok4, val4 = parse_date_ddmmyyyy("2025-01-06")  # YYYY-MM-DD also accepted
    assert ok4 is True
    assert val4 == date(2025, 1, 6)


@pytest.mark.skipif(not _sales_out_schema_available(), reason="Migration 014 (sales_out) not applied")
def test_unknown_aah_code_rejected() -> None:
    """Rows with AAH_Product_Code not in products.aah_code are rejected with reason unknown_aah_code."""
    db = SessionLocal()
    run_id = uuid4()
    try:
        if not db.query(Warehouse).filter(Warehouse.code == "AAH").first():
            db.add(Warehouse(code="AAH", name="AAH", timezone="Europe/London"))
            db.commit()
        run = IngestionRun(
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.SALES_OUT,
            file_name="test.csv",
            file_sha256="x",
            status=IngestionStatus.PENDING,
            row_count=1,
        )
        db.add(run)
        db.flush()
        run_id = run.id
        db.add(
            SalesOutStage(
                ingestion_run_id=run_id,
                aah_product_code="UNKNOWN_AAH",
                processed_date=date(2025, 1, 7),
            )
        )
        db.commit()

        build_demand_from_sales_out(db, cast(UUID, run_id))
        db.commit()

        run_after = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
        assert run_after is not None
        assert getattr(run_after, "rejected_count", 0) == 1
        rej = db.query(IngestionRejection).filter(IngestionRejection.ingestion_run_id == run_id).first()
        assert rej is not None
        assert "unknown_aah_code" in (getattr(rej, "reason", None) or "")
    finally:
        db.query(IngestionRejection).filter(IngestionRejection.ingestion_run_id == run_id).delete(synchronize_session=False)
        db.query(SalesOutStage).filter(SalesOutStage.ingestion_run_id == run_id).delete(synchronize_session=False)
        db.query(IngestionRun).filter(IngestionRun.id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.skipif(not _sales_out_schema_available(), reason="Migration 014 (sales_out) not applied")
def test_weekly_aggregation_sums_invoiced_qty() -> None:
    """Aggregation: same week + same sku -> demand_actuals has SUM(invoiced_qty)."""
    db = SessionLocal()
    run_id = uuid4()
    try:
        if not db.query(Warehouse).filter(Warehouse.code == "AAH").first():
            db.add(Warehouse(code="AAH", name="AAH", timezone="Europe/London"))
            db.commit()
        prod = db.query(Product).filter(Product.aah_code == "AAH-TEST-SKU").first()
        if not prod:
            prod = Product(sku="SKU-SALES-OUT", name="Test", aah_code="AAH-TEST-SKU")
            db.add(prod)
            db.commit()
        sku = prod.sku
        run = IngestionRun(
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.SALES_OUT,
            file_name="test.csv",
            file_sha256="y",
            status=IngestionStatus.PENDING,
            row_count=2,
        )
        db.add(run)
        db.flush()
        run_id = run.id
        week = date(2025, 1, 7)  # Tuesday
        for i, qty in [(1, 10), (2, 20)]:
            db.add(
                SalesOutStage(
                    ingestion_run_id=run_id,
                    aah_product_code="AAH-TEST-SKU",
                    processed_date=week,
                    invoiced_qty=Decimal(str(qty)),
                )
            )
        db.commit()

        build_demand_from_sales_out(db, cast(UUID, run_id))
        db.commit()

        row = (
            db.query(DemandActual)
            .filter(
                DemandActual.week_start == week,
                DemandActual.sku == sku,
                DemandActual.warehouse_code == "AAH",
                DemandActual.demand_type == DemandType.CUSTOMER,
            )
            .first()
        )
        assert row is not None
        assert float(cast(Decimal, row.qty)) == 30.0
    finally:
        db.query(DemandActual).filter(DemandActual.warehouse_code == "AAH", DemandActual.sku == sku).delete(synchronize_session=False)
        db.query(SalesOutStage).filter(SalesOutStage.ingestion_run_id == run_id).delete(synchronize_session=False)
        db.query(IngestionRun).filter(IngestionRun.id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.skipif(not _sales_out_schema_available(), reason="Migration 014 (sales_out) not applied")
def test_idempotent_rerun_does_not_double_count() -> None:
    """Re-running build_demand_from_sales_out for same run_id does not double demand rows or qty."""
    db = SessionLocal()
    run_id = uuid4()
    try:
        if not db.query(Warehouse).filter(Warehouse.code == "AAH").first():
            db.add(Warehouse(code="AAH", name="AAH", timezone="Europe/London"))
            db.commit()
        prod = db.query(Product).filter(Product.aah_code == "AAH-IDEM").first()
        if not prod:
            prod = Product(sku="SKU-IDEM", name="Idem", aah_code="AAH-IDEM")
            db.add(prod)
            db.commit()
        sku = prod.sku
        run = IngestionRun(
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.SALES_OUT,
            file_name="test.csv",
            file_sha256="z",
            status=IngestionStatus.PENDING,
            row_count=1,
        )
        db.add(run)
        db.flush()
        run_id = run.id
        week = date(2025, 2, 4)
        db.add(
            SalesOutStage(
                ingestion_run_id=run_id,
                aah_product_code="AAH-IDEM",
                processed_date=week,
                invoiced_qty=Decimal("100"),
            )
        )
        db.commit()

        build_demand_from_sales_out(db, cast(UUID, run_id))
        db.commit()

        row1 = (
            db.query(DemandActual)
            .filter(
                DemandActual.week_start == week,
                DemandActual.sku == sku,
                DemandActual.warehouse_code == "AAH",
                DemandActual.demand_type == DemandType.CUSTOMER,
            )
            .first()
        )
        assert row1 is not None
        assert float(cast(Decimal, row1.qty)) == 100.0

        # Rerun transform for same run_id
        run.status = IngestionStatus.PENDING
        db.commit()
        build_demand_from_sales_out(db, cast(UUID, run_id))
        db.commit()

        rows_after = (
            db.query(DemandActual)
            .filter(
                DemandActual.week_start == week,
                DemandActual.sku == sku,
                DemandActual.warehouse_code == "AAH",
                DemandActual.demand_type == DemandType.CUSTOMER,
            )
            .all()
        )
        assert len(rows_after) == 1
        assert float(cast(Decimal, rows_after[0].qty)) == 100.0
    finally:
        db.query(DemandActual).filter(DemandActual.warehouse_code == "AAH", DemandActual.sku == sku).delete(synchronize_session=False)
        db.query(SalesOutStage).filter(SalesOutStage.ingestion_run_id == run_id).delete(synchronize_session=False)
        db.query(IngestionRun).filter(IngestionRun.id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()
