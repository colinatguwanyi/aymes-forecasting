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
    IngestionRun,
    IngestionSourceType,
    IngestionStatus,
    InventorySnapshotDaily,
    InventorySnapshotWeekly,
    StockOnHandStage,
    Warehouse,
    WarehouseBranchMapping,
)
from app.services.soh_ingestion import (
    build_daily_from_stage,
    build_weekly_from_daily,
    validate_and_stage_soh_row,
)
from app.services.time_bucketing import week_start_for_date


def _soh_schema_available() -> bool:
    """True if migration 015 is applied (stock_on_hand enum, stock_on_hand_stage, warehouse_branch_mapping)."""
    from sqlalchemy import text
    try:
        db = SessionLocal()
        try:
            r = db.execute(text(
                "SELECT 1 FROM pg_enum e JOIN pg_type t ON e.enumtypid = t.oid WHERE t.typname = 'ingestion_entity_enum' AND e.enumlabel = 'stock_on_hand' LIMIT 1"
            ))
            if r.scalar() != 1:
                return False
            r2 = db.execute(text(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'stock_on_hand_stage' LIMIT 1"
            ))
            if r2.scalar() != 1:
                return False
            r3 = db.execute(text(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'warehouse_branch_mapping' LIMIT 1"
            ))
            return r3.scalar() == 1
        finally:
            db.close()
    except Exception:
        return False


@pytest.mark.skipif(not _soh_schema_available(), reason="Migration 015 (SOH) not applied")
def test_unknown_branch_rejected() -> None:
    """Row with Branch Name not in warehouse_branch_mapping is rejected with reason unknown branch mapping."""
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
        assert ok is False
        assert reason == "unknown branch mapping"
        staged = db.query(StockOnHandStage).filter(StockOnHandStage.ingestion_run_id == run_id).all()
        assert len(staged) == 1
        assert staged[0].reject_reason == "unknown branch mapping"
    finally:
        db.query(StockOnHandStage).filter(StockOnHandStage.ingestion_run_id == run_id).delete(synchronize_session=False)
        db.query(IngestionRun).filter(IngestionRun.id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.skipif(not _soh_schema_available(), reason="Migration 015 (SOH) not applied")
def test_daily_canonical_row_count() -> None:
    """Valid staged rows → build_daily_from_stage → daily canonical row count matches (one per wh, sku, date; max aggregation)."""
    db = SessionLocal()
    run_id = uuid4()
    try:
        wh = db.query(Warehouse).filter(Warehouse.code == "SOH-TEST-WH").first()
        if not wh:
            wh = Warehouse(code="SOH-TEST-WH", name="Test WH", timezone="Europe/London")
            db.add(wh)
            db.commit()
        mapping = db.query(WarehouseBranchMapping).filter(WarehouseBranchMapping.branch_name == "SOH-TEST-BRANCH").first()
        if not mapping:
            db.add(WarehouseBranchMapping(branch_name="SOH-TEST-BRANCH", warehouse_code="SOH-TEST-WH"))
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
        branch_to_wh = {"SOH-TEST-BRANCH": "SOH-TEST-WH"}
        for i, (d, qty) in enumerate([("05/02/2025", 100), ("06/02/2025", 200)]):
            ok, _ = validate_and_stage_soh_row(
                db, run_id,
                {"Branch Name": "SOH-TEST-BRANCH", "AAH Code": "SKU-A", "Stock at": d, "STOCK": str(qty), "ON ORDER": "0"},
                i + 2, branch_to_wh,
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
    finally:
        db.query(InventorySnapshotDaily).filter(InventorySnapshotDaily.source_run_id == run_id).delete(synchronize_session=False)
        db.query(InventorySnapshotWeekly).filter(InventorySnapshotWeekly.source_run_id == run_id).delete(synchronize_session=False)
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
        branch_to_wh = {"SOH-WK-BRANCH": "SOH-WK-WH"}
        # Same week (W-TUE): 04/02/2025 = Tue, 07/02/2025 = Fri. Latest in week = 07/02 → qty 50.
        for i, (d, qty) in enumerate([("04/02/2025", 30), ("07/02/2025", 50)]):
            ok, _ = validate_and_stage_soh_row(
                db, run_id,
                {"Branch Name": "SOH-WK-BRANCH", "AAH Code": "SKU-B", "Stock at": d, "STOCK": str(qty), "ON ORDER": "0"},
                i + 2, branch_to_wh,
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
        assert row.on_hand_qty == Decimal("50")
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
        branch_to_wh = {"SOH-IDEM-BRANCH": "SOH-IDEM-WH"}
        ok, _ = validate_and_stage_soh_row(
            db, run_id,
            {"Branch Name": "SOH-IDEM-BRANCH", "AAH Code": "SKU-C", "Stock at": "10/02/2025", "STOCK": "25", "ON ORDER": "0"},
            2, branch_to_wh,
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
