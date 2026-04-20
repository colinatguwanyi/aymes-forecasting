"""Tests: Weekly vs historical ingestion modes, requires_confirm, confirm endpoint."""
from __future__ import annotations

from datetime import date
import pytest  # type: ignore[reportMissingImports]

from app.models import IngestionMode
from app.services.ingestion_mode import (
    ROW_COUNT_THRESHOLD,
    SPAN_DAYS_THRESHOLD,
    compute_date_range_and_mode,
)


def test_mode_detection_weekly_small_file() -> None:
    """Small row count and short span -> weekly mode, no confirm."""
    from app.database import SessionLocal
    from app.models import DemandStageWeekly, DemandType, IngestionEntity, IngestionRun, IngestionSourceType, IngestionStatus
    from uuid import uuid4

    db = SessionLocal()
    run_id = uuid4()
    try:
        run = IngestionRun(
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.DEMAND,
            file_name="small.csv",
            file_sha256="a",
            status=IngestionStatus.PENDING,
            row_count=100,
        )
        db.add(run)
        db.flush()
        run_id = run.id
        # Add a few staged rows (same week)
        week = date(2025, 1, 7)
        for i in range(5):
            db.add(
                DemandStageWeekly(
                    ingestion_run_id=run_id,
                    week_start=week,
                    sku_raw="SKU1",
                    sku="SKU1",
                    warehouse_code="WH1",
                    demand_type=DemandType.CUSTOMER,
                    qty=10,
                )
            )
        db.commit()

        dmin, dmax, mode, requires = compute_date_range_and_mode(
            db, run_id, IngestionEntity.DEMAND, 100, 1000
        )
        assert mode == IngestionMode.WEEKLY
        assert requires is False
        assert dmin == week
        assert dmax == week
    finally:
        db.query(DemandStageWeekly).filter(DemandStageWeekly.ingestion_run_id == run_id).delete(synchronize_session=False)
        db.query(IngestionRun).filter(IngestionRun.id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_mode_detection_historical_by_row_count() -> None:
    """Row count > ROW_COUNT_THRESHOLD -> historical, requires_confirm."""
    from app.database import SessionLocal
    from app.models import IngestionEntity, IngestionRun, IngestionSourceType, IngestionStatus
    from uuid import uuid4

    db = SessionLocal()
    run_id = uuid4()
    try:
        run = IngestionRun(
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.DEMAND,
            file_name="big.csv",
            file_sha256="b",
            status=IngestionStatus.PENDING,
            row_count=ROW_COUNT_THRESHOLD + 1,
        )
        db.add(run)
        db.flush()
        run_id = run.id
        db.commit()

        dmin, dmax, mode, requires = compute_date_range_and_mode(
            db, run_id, IngestionEntity.DEMAND, ROW_COUNT_THRESHOLD + 1, 1000
        )
        assert mode == IngestionMode.HISTORICAL
        assert requires is True
    finally:
        db.query(IngestionRun).filter(IngestionRun.id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_mode_detection_historical_by_span_days() -> None:
    """Span > SPAN_DAYS_THRESHOLD -> historical, requires_confirm."""
    from datetime import timedelta
    from app.database import SessionLocal
    from app.models import DemandStageWeekly, DemandType, IngestionEntity, IngestionRun, IngestionSourceType, IngestionStatus
    from uuid import uuid4

    db = SessionLocal()
    run_id = uuid4()
    try:
        run = IngestionRun(
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.DEMAND,
            file_name="wide.csv",
            file_sha256="c",
            status=IngestionStatus.PENDING,
            row_count=50,
        )
        db.add(run)
        db.flush()
        run_id = run.id
        # Add rows spanning > SPAN_DAYS_THRESHOLD
        start = date(2024, 1, 2)
        for i in range(5):
            db.add(
                DemandStageWeekly(
                    ingestion_run_id=run_id,
                    week_start=start + timedelta(days=i * 35),
                    sku_raw="SKU1",
                    sku="SKU1",
                    warehouse_code="WH1",
                    demand_type=DemandType.CUSTOMER,
                    qty=10,
                )
            )
        db.commit()

        dmin, dmax, mode, requires = compute_date_range_and_mode(
            db, run_id, IngestionEntity.DEMAND, 50, 1000
        )
        # 4*35=140 days span > 120
        assert mode == IngestionMode.HISTORICAL
        assert requires is True
    finally:
        db.query(DemandStageWeekly).filter(DemandStageWeekly.ingestion_run_id == run_id).delete(synchronize_session=False)
        db.query(IngestionRun).filter(IngestionRun.id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()
