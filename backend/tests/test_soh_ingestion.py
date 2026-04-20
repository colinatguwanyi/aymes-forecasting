"""Tests: SOH ingestion — unknown branch rejected, daily canonical count, weekly rollup (latest in week), idempotency.

Requires migration 015 (warehouse_branch_mapping, stock_on_hand_stage, inventory_snapshots_daily, inventory_snapshots_weekly source_type).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest  # type: ignore[reportMissingImports]

from app.database import SessionLocal
from app.models import (
    IngestionEntity,
    IngestionRejection,
    IngestionRun,
    IngestionSourceType,
    IngestionStatus,
    InventorySnapshotDaily,
    InventorySnapshotWeekly,
    Product,
    StockOnHandStage,
    Warehouse,
    WarehouseBranchMapping,
)
from app.services.soh_ingestion import (
    build_daily_from_stage,
    build_weekly_from_daily,
    stage_blp_soh,
    validate_and_stage_soh_row,
)
from app.services.time_bucketing import week_start_for_date


def _soh_schema_available() -> bool:
    """True if migration 015 objects exist (SOH stage + branch mapping). Works for Postgres, MySQL, SQLite."""
    try:
        from sqlalchemy import inspect

        from app.database import engine

        insp = inspect(engine)
        names = set(insp.get_table_names())
        return "stock_on_hand_stage" in names and "warehouse_branch_mapping" in names
    except Exception:
        return False


@pytest.mark.skipif(not _soh_schema_available(), reason="Migration 015 (SOH) not applied")
def test_aah_format_rolls_all_branches_to_aah() -> None:
    """AAH format: branch column read but not used; all rows roll up to warehouse AAH."""
    db = SessionLocal()
    run_id = uuid4()
    try:
        run = IngestionRun(
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.STOCK_ON_HAND,
            file_name="test.csv",
            file_sha256="x",
            status=IngestionStatus.PENDING,
            row_count=0,
        )
        db.add(run)
        db.flush()
        run_id = cast(UUID, run.id)
        branch_to_wh = {}
        row = {"Branch Name": "UNMAPPED_BRANCH", "AAH Code": "SKU1", "Stock at": "01/02/2025", "STOCK": "10", "ON ORDER": "0"}
        ok, reason = validate_and_stage_soh_row(db, run_id, row, 2, branch_to_wh)
        db.commit()
        assert ok is True
        staged = db.query(StockOnHandStage).filter(StockOnHandStage.ingestion_run_id == run_id).all()
        assert len(staged) == 1
        assert getattr(staged[0], "branch_name_raw", None) == "AAH"
    finally:
        db.query(StockOnHandStage).filter(StockOnHandStage.ingestion_run_id == run_id).delete(synchronize_session=False)
        db.query(IngestionRun).filter(IngestionRun.id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.skipif(not _soh_schema_available(), reason="Migration 015 (SOH) not applied")
def test_daily_canonical_row_count() -> None:
    """Valid staged rows → build_daily_from_stage → daily canonical row count matches (one per wh, sku, date; sum aggregation)."""
    db = SessionLocal()
    run_id = uuid4()
    try:
        # AAH format rolls all to warehouse AAH (migration 014 ensures AAH exists)
        run = IngestionRun(
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.STOCK_ON_HAND,
            file_name="test.csv",
            file_sha256="x",
            status=IngestionStatus.PENDING,
            row_count=0,
        )
        db.add(run)
        db.flush()
        run_id = cast(UUID, run.id)
        assert db.query(Warehouse).filter(Warehouse.code == "AAH").first(), "AAH warehouse required"
        for i, (d, qty) in enumerate([("05/02/2025", 100), ("06/02/2025", 200)]):
            ok, _ = validate_and_stage_soh_row(
                db, run_id,
                {"Branch Name": "SOH-TEST-BRANCH", "AAH Code": "SKU-A", "Stock at": d, "STOCK": str(qty), "ON ORDER": "0"},
                i + 2, {},
            )
            assert ok is True
        db.commit()
        build_daily_from_stage(db, run_id)
        db.commit()
        daily_count = db.query(InventorySnapshotDaily).filter(
            InventorySnapshotDaily.source_type == "soh",
            InventorySnapshotDaily.source_run_id == run_id,
        ).count()
        assert daily_count == 2
        daily = db.query(InventorySnapshotDaily).filter(
            InventorySnapshotDaily.source_type == "soh",
            InventorySnapshotDaily.source_run_id == run_id,
        ).first()
        assert daily and daily.warehouse_code == "AAH"
    finally:
        db.query(InventorySnapshotDaily).filter(InventorySnapshotDaily.source_run_id == run_id).delete(synchronize_session=False)
        db.query(InventorySnapshotWeekly).filter(InventorySnapshotWeekly.source_run_id == run_id).delete(synchronize_session=False)
        db.query(StockOnHandStage).filter(StockOnHandStage.ingestion_run_id == run_id).delete(synchronize_session=False)
        db.query(IngestionRun).filter(IngestionRun.id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.skipif(not _soh_schema_available(), reason="Migration 015 (SOH) not applied")
def test_soh_warehouse_override_and_rollup() -> None:
    """Warehouse override: branch column ignored; quantities rolled up (summed) per (product, warehouse, date)."""
    db = SessionLocal()
    run_id = uuid4()
    try:
        wh = db.query(Warehouse).filter(Warehouse.code == "SOH-ROLLUP-WH").first()
        if not wh:
            wh = Warehouse(code="SOH-ROLLUP-WH", name="Rollup WH", timezone="Europe/London")
            db.add(wh)
            db.commit()
        run = IngestionRun(
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.STOCK_ON_HAND,
            file_name="test.csv",
            file_sha256="x",
            status=IngestionStatus.PENDING,
            row_count=0,
        )
        db.add(run)
        db.flush()
        run_id = cast(UUID, run.id)
        branch_to_wh: dict[str, str] = {}
        # No branch in rows; use warehouse override
        for i, qty in enumerate([10, 20, 15]):  # 3 rows, same date/sku → sum = 45
            ok, _ = validate_and_stage_soh_row(
                db, run_id,
                {"AAH Code": "SKU-ROLLUP", "Stock at": "05/02/2025", "STOCK": str(qty), "ON ORDER": "0"},
                i + 2, branch_to_wh, warehouse_code_override="SOH-ROLLUP-WH",
            )
            assert ok is True
        db.commit()
        build_daily_from_stage(db, run_id)
        db.commit()
        daily = db.query(InventorySnapshotDaily).filter(
            InventorySnapshotDaily.source_type == "soh",
            InventorySnapshotDaily.source_run_id == run_id,
        ).first()
        assert daily is not None
        assert daily.on_hand_units == Decimal("45")  # 10 + 20 + 15 rolled up
        assert daily.sku == "SKU-ROLLUP"
        assert daily.warehouse_code == "SOH-ROLLUP-WH"
    finally:
        db.query(InventorySnapshotDaily).filter(InventorySnapshotDaily.source_run_id == run_id).delete(synchronize_session=False)
        db.query(StockOnHandStage).filter(StockOnHandStage.ingestion_run_id == run_id).delete(synchronize_session=False)
        db.query(IngestionRun).filter(IngestionRun.id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.skipif(not _soh_schema_available(), reason="Migration 015 (SOH) not applied")
def test_weekly_rollup_latest_in_week() -> None:
    """Weekly rollup uses latest as_of_date within each week for on_hand_qty."""
    db = SessionLocal()
    run_id = uuid4()
    try:
        wh = db.query(Warehouse).filter(Warehouse.code == "SOH-WK-WH").first()
        if not wh:
            wh = Warehouse(code="SOH-WK-WH", name="WK WH", timezone="Europe/London")
            db.add(wh)
            db.commit()
        if not db.query(WarehouseBranchMapping).filter(WarehouseBranchMapping.branch_name == "SOH-WK-BRANCH").first():
            db.add(WarehouseBranchMapping(branch_name="SOH-WK-BRANCH", warehouse_code="SOH-WK-WH"))
            db.commit()
        run = IngestionRun(
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.STOCK_ON_HAND,
            file_name="test.csv",
            file_sha256="x",
            status=IngestionStatus.PENDING,
            row_count=0,
        )
        db.add(run)
        db.flush()
        run_id = cast(UUID, run.id)
        # Same week (W-TUE): 04/02/2025 = Tue, 07/02/2025 = Fri. Latest in week = 07/02 → qty 50.
        for i, (d, qty) in enumerate([("04/02/2025", 30), ("07/02/2025", 50)]):
            ok, _ = validate_and_stage_soh_row(
                db, run_id,
                {"Branch Name": "SOH-WK-BRANCH", "AAH Code": "SKU-B", "Stock at": d, "STOCK": str(qty), "ON ORDER": "0"},
                i + 2, {}, warehouse_code_override="SOH-WK-WH",
            )
            assert ok is True
        db.commit()
        build_daily_from_stage(db, run_id)
        db.commit()
        weeks_written = build_weekly_from_daily(db, run_id)
        db.commit()
        assert weeks_written == 1
        week_start = week_start_for_date(date(2025, 2, 4))
        row = db.query(InventorySnapshotWeekly).filter(
            InventorySnapshotWeekly.week_start == week_start,
            InventorySnapshotWeekly.sku == "SKU-B",
            InventorySnapshotWeekly.warehouse_code == "SOH-WK-WH",
            InventorySnapshotWeekly.source_type == "soh",
        ).first()
        assert row is not None
        _qty = getattr(row, "on_hand_qty", None)
        assert _qty == Decimal("50")
    finally:
        db.query(InventorySnapshotDaily).filter(InventorySnapshotDaily.source_run_id == run_id).delete(synchronize_session=False)
        db.query(InventorySnapshotWeekly).filter(InventorySnapshotWeekly.source_run_id == run_id).delete(synchronize_session=False)
        db.query(StockOnHandStage).filter(StockOnHandStage.ingestion_run_id == run_id).delete(synchronize_session=False)
        db.query(IngestionRun).filter(IngestionRun.id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.skipif(not _soh_schema_available(), reason="Migration 015 (SOH) not applied")
def test_idempotency_re_run_no_duplicate_weekly() -> None:
    """Re-running build_daily_from_stage and build_weekly_from_daily for same run_id does not duplicate weekly rows."""
    db = SessionLocal()
    run_id = uuid4()
    try:
        if not db.query(Warehouse).filter(Warehouse.code == "SOH-IDEM-WH").first():
            db.add(Warehouse(code="SOH-IDEM-WH", name="Idem WH", timezone="Europe/London"))
            db.commit()
        if not db.query(WarehouseBranchMapping).filter(WarehouseBranchMapping.branch_name == "SOH-IDEM-BRANCH").first():
            db.add(WarehouseBranchMapping(branch_name="SOH-IDEM-BRANCH", warehouse_code="SOH-IDEM-WH"))
            db.commit()
        run = IngestionRun(
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.STOCK_ON_HAND,
            file_name="test.csv",
            file_sha256="x",
            status=IngestionStatus.PENDING,
            row_count=0,
        )
        db.add(run)
        db.flush()
        run_id = cast(UUID, run.id)
        ok, _ = validate_and_stage_soh_row(
            db, run_id,
            {"Branch Name": "SOH-IDEM-BRANCH", "AAH Code": "SKU-C", "Stock at": "10/02/2025", "STOCK": "25", "ON ORDER": "0"},
            2, {}, warehouse_code_override="SOH-IDEM-WH",
        )
        assert ok is True
        db.commit()
        build_daily_from_stage(db, run_id)
        db.commit()
        build_weekly_from_daily(db, run_id)
        db.commit()
        count1 = db.query(InventorySnapshotWeekly).filter(
            InventorySnapshotWeekly.source_type == "soh",
            InventorySnapshotWeekly.source_run_id == run_id,
        ).count()
        build_daily_from_stage(db, run_id)
        db.commit()
        build_weekly_from_daily(db, run_id)
        db.commit()
        count2 = db.query(InventorySnapshotWeekly).filter(
            InventorySnapshotWeekly.source_type == "soh",
            InventorySnapshotWeekly.source_run_id == run_id,
        ).count()
        assert count1 == count2
        assert count1 == 1
    finally:
        db.query(InventorySnapshotDaily).filter(InventorySnapshotDaily.source_run_id == run_id).delete(synchronize_session=False)
        db.query(InventorySnapshotWeekly).filter(InventorySnapshotWeekly.source_run_id == run_id).delete(synchronize_session=False)
        db.query(StockOnHandStage).filter(StockOnHandStage.ingestion_run_id == run_id).delete(synchronize_session=False)
        db.query(IngestionRun).filter(IngestionRun.id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.skipif(not _soh_schema_available(), reason="Migration 015 (SOH) not applied")
def test_blp_stage_and_build_daily() -> None:
    """BLP format: stage_blp_soh -> build_daily_from_stage (product resolution, Code -> sku)."""
    db = SessionLocal()
    run_id = uuid4()
    try:
        if not db.query(Warehouse).filter(Warehouse.code == "BLP").first():
            db.add(Warehouse(code="BLP", name="BLP WH", timezone="Europe/London"))
            db.commit()
        if not db.query(Product).filter(Product.sku == "AC1.5-CH").first():
            db.add(Product(sku="AC1.5-CH", name="AC1.5", uom="units", active=True))
            db.commit()
        run = IngestionRun(
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.STOCK_ON_HAND,
            file_name="blp.csv",
            file_sha256="x",
            status=IngestionStatus.PENDING,
            row_count=0,
        )
        db.add(run)
        db.flush()
        run_id = cast(UUID, run.id)
        rows = [
            {"Code": "AC1.5-CH", "Balance": "71"},
            {"Code": "AC1.5-CH", "Balance": "312"},
            {"Code": "AC1.5-CH", "Balance": "1416"},
        ]
        staged, rejected, summary = stage_blp_soh(db, run_id, rows, "BLP", date(2025, 2, 24))
        db.commit()
        assert staged == 1
        assert rejected == 0
        assert summary["distinct_skus"] == 1
        assert summary["total_qty"] == 71 + 312 + 1416
        assert "coverage" in summary
        cov = summary["coverage"]
        assert cov["total_unique_codes"] == 1
        assert cov["mapped_codes"] == 1
        assert cov["missing_codes"] == 0
        assert cov["pct_coverage_codes"] == 100.0
        assert cov["units_total"] == 71 + 312 + 1416
        assert cov["units_missing"] == 0
        build_daily_from_stage(db, run_id)
        db.commit()
        daily = db.query(InventorySnapshotDaily).filter(
            InventorySnapshotDaily.source_run_id == run_id,
            InventorySnapshotDaily.sku == "AC1.5-CH",
        ).first()
        assert daily is not None
        _units = getattr(daily, "on_hand_units", None)
        assert _units == Decimal("1799")
    finally:
        db.query(InventorySnapshotDaily).filter(InventorySnapshotDaily.source_run_id == run_id).delete(synchronize_session=False)
        db.query(StockOnHandStage).filter(StockOnHandStage.ingestion_run_id == run_id).delete(synchronize_session=False)
        db.query(IngestionRun).filter(IngestionRun.id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.skipif(not _soh_schema_available(), reason="Migration 015 (SOH) not applied")
def test_blp_coverage_with_missing_codes() -> None:
    """BLP stage reports coverage when some codes are unmapped."""
    db = SessionLocal()
    run_id = uuid4()
    try:
        if not db.query(Warehouse).filter(Warehouse.code == "BLP-COV").first():
            db.add(Warehouse(code="BLP-COV", name="BLP Cov", timezone="Europe/London"))
            db.commit()
        if not db.query(Product).filter(Product.sku == "COV-SKU").first():
            db.add(Product(sku="COV-SKU", name="Cov", uom="units", active=True))
            db.commit()
        run = IngestionRun(
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.STOCK_ON_HAND,
            file_name="blp.csv",
            file_sha256="x",
            status=IngestionStatus.PENDING,
            row_count=0,
        )
        db.add(run)
        db.flush()
        run_id = cast(UUID, run.id)
        rows = [
            {"Code": "COV-SKU", "Balance": "100"},
            {"Code": "UNMAPPED-X", "Balance": "50"},
            {"Code": "UNMAPPED-X", "Balance": "30"},
        ]
        staged, rejected, summary = stage_blp_soh(db, run_id, rows, "BLP-COV", date(2025, 2, 24))
        db.commit()
        assert staged == 1
        assert rejected == 2
        cov = summary.get("coverage", {})
        assert cov["total_unique_codes"] == 2
        assert cov["mapped_codes"] == 1
        assert cov["missing_codes"] == 1
        assert cov["pct_coverage_codes"] == 50.0
        assert cov["units_total"] == 180
        assert cov["units_missing"] == 80
    finally:
        db.query(IngestionRejection).filter(IngestionRejection.ingestion_run_id == run_id).delete(synchronize_session=False)
        db.query(StockOnHandStage).filter(StockOnHandStage.ingestion_run_id == run_id).delete(synchronize_session=False)
        db.query(IngestionRun).filter(IngestionRun.id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.skipif(not _soh_schema_available(), reason="Migration 015 (SOH) not applied")
def test_blp_idempotency_re_execute_no_duplicate() -> None:
    """Re-execute same BLP run: build_daily + build_weekly twice does not duplicate."""
    db = SessionLocal()
    run_id = uuid4()
    try:
        if not db.query(Warehouse).filter(Warehouse.code == "BLP-IDEM").first():
            db.add(Warehouse(code="BLP-IDEM", name="BLP Idem", timezone="Europe/London"))
            db.commit()
        if not db.query(Product).filter(Product.sku == "SKU-Z").first():
            db.add(Product(sku="SKU-Z", name="Z", uom="units", active=True))
            db.commit()
        run = IngestionRun(
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.STOCK_ON_HAND,
            file_name="blp.csv",
            file_sha256="x",
            status=IngestionStatus.PENDING,
            row_count=0,
        )
        db.add(run)
        db.flush()
        run_id = cast(UUID, run.id)
        rows = [{"Code": "SKU-Z", "Balance": "100"}]
        stage_blp_soh(db, run_id, rows, "BLP-IDEM", date(2025, 2, 24))
        db.commit()
        build_daily_from_stage(db, run_id)
        db.commit()
        build_weekly_from_daily(db, run_id)
        db.commit()
        count1 = db.query(InventorySnapshotWeekly).filter(
            InventorySnapshotWeekly.source_run_id == run_id,
        ).count()
        build_daily_from_stage(db, run_id)
        db.commit()
        build_weekly_from_daily(db, run_id)
        db.commit()
        count2 = db.query(InventorySnapshotWeekly).filter(
            InventorySnapshotWeekly.source_run_id == run_id,
        ).count()
        assert count1 == count2 == 1
    finally:
        db.query(InventorySnapshotDaily).filter(InventorySnapshotDaily.source_run_id == run_id).delete(synchronize_session=False)
        db.query(InventorySnapshotWeekly).filter(InventorySnapshotWeekly.source_run_id == run_id).delete(synchronize_session=False)
        db.query(StockOnHandStage).filter(StockOnHandStage.ingestion_run_id == run_id).delete(synchronize_session=False)
        db.query(IngestionRun).filter(IngestionRun.id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()
