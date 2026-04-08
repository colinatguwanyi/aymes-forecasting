"""
Python query methods that mirror the old Postgres SQL views — now MySQL-backed.

These functions operate against the MySQL forecast database (forecast_db session)
and use the MySQL ORM models from app.forecast_mysql_models.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.forecast_mysql_models import (
    ForecastRun,
    ForecastSalesWeekly,
    ForecastTrainingSeriesWeekly,
)

logger = logging.getLogger(__name__)


def query_forecast_sales_source_weekly(
    forecast_db: Session,
    *,
    product_code: str | None = None,
    warehouse_code: str | None = None,
    from_week: date | None = None,
    to_week: date | None = None,
    limit: int = 10_000,
) -> list[dict[str, Any]]:
    """Return weekly sales rows from forecast_sales_weekly (MySQL)."""
    q = (
        forecast_db.query(ForecastSalesWeekly)
        .order_by(
            ForecastSalesWeekly.product_code,
            ForecastSalesWeekly.warehouse_code,
            ForecastSalesWeekly.week_start,
        )
    )
    if product_code is not None:
        q = q.filter(ForecastSalesWeekly.product_code == product_code)
    if warehouse_code is not None:
        q = q.filter(
            func.upper(ForecastSalesWeekly.warehouse_code) == warehouse_code.upper()
        )
    if from_week is not None:
        q = q.filter(ForecastSalesWeekly.week_start >= from_week)
    if to_week is not None:
        q = q.filter(ForecastSalesWeekly.week_start <= to_week)

    rows = q.limit(limit).all()
    return [
        {
            "id": r.id,
            "product_code": r.product_code,
            "warehouse_code": r.warehouse_code,
            "week_start": r.week_start,
            "units_sold": float(Decimal(str(r.units_sold))) if r.units_sold is not None else 0.0,
            "product_name": r.product_name,
            "pip_code": r.pip_code,
            "item_size": float(Decimal(str(r.item_size))) if r.item_size is not None else None,
            "source_system": r.source_system,
        }
        for r in rows
    ]


def query_forecast_training_base(
    forecast_db: Session,
    *,
    run_id: int | None = None,
    product_code: str | None = None,
    warehouse_code: str | None = None,
    from_week: date | None = None,
    to_week: date | None = None,
    limit: int = 50_000,
) -> list[dict[str, Any]]:
    """Return non-excluded training series rows, joined with run metadata."""
    q = (
        forecast_db.query(
            ForecastTrainingSeriesWeekly,
            ForecastRun.inference_date,
            ForecastRun.run_status,
        )
        .join(ForecastRun, ForecastRun.id == ForecastTrainingSeriesWeekly.run_id)
        .filter(ForecastTrainingSeriesWeekly.is_excluded == False)  # noqa: E712
        .order_by(
            ForecastTrainingSeriesWeekly.product_code,
            ForecastTrainingSeriesWeekly.warehouse_code,
            ForecastTrainingSeriesWeekly.week_start,
        )
    )
    if run_id is not None:
        q = q.filter(ForecastTrainingSeriesWeekly.run_id == run_id)
    if product_code is not None:
        q = q.filter(ForecastTrainingSeriesWeekly.product_code == product_code)
    if warehouse_code is not None:
        q = q.filter(
            func.upper(ForecastTrainingSeriesWeekly.warehouse_code) == warehouse_code.upper()
        )
    if from_week is not None:
        q = q.filter(ForecastTrainingSeriesWeekly.week_start >= from_week)
    if to_week is not None:
        q = q.filter(ForecastTrainingSeriesWeekly.week_start <= to_week)

    rows = q.limit(limit).all()
    return [
        {
            "id": ts.id,
            "run_id": ts.run_id,
            "inference_date": inference_date.isoformat() if inference_date else None,
            "run_status": run_status,
            "product_code": ts.product_code,
            "warehouse_code": ts.warehouse_code,
            "week_start": ts.week_start,
            "qty": float(Decimal(str(ts.qty))) if ts.qty is not None else 0.0,
            "adjusted_qty": float(Decimal(str(ts.adjusted_qty))) if ts.adjusted_qty is not None else None,
            "stock_adjusted_qty": float(Decimal(str(ts.stock_adjusted_qty))) if ts.stock_adjusted_qty is not None else None,
            "is_outlier_flagged": ts.is_outlier_flagged,
            "is_stock_constrained": ts.is_stock_constrained,
            "week_classification": ts.week_classification,
            "series_variant": ts.series_variant,
        }
        for ts, inference_date, run_status in rows
    ]
