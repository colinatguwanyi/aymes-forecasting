"""
supply_adjustment_service.py
Post-processing layer: applies SOH + inbound supply to best-model forecast rows.

This module is deliberately isolated from the forecasting engine — it reads
forecast_results_weekly and forecast_stock_weekly, computes the supply-adjusted
figures, and writes to forecast_supply_adjusted.  Nothing in the base forecast
pipeline (Prophet, XGBoost, model selection, legacy export) is touched.

Stock data source priority
--------------------------
1. forecast_stock_weekly WHERE run_id = this run  (run-scoped, best)
2. forecast_stock_weekly with any recent run for matching product+warehouse
3. Mock data  (seeded from base_forecast * 1.2 + random variation)

The caller controls mock via use_mock_data=True, or the service falls back to
mock automatically when no stock rows are found for the run.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from app.forecast_mysql_models import (
    ForecastResultWeekly,
    ForecastStockWeekly,
    ForecastSupplyAdjusted,
)

logger = logging.getLogger(__name__)

_QUANT = Decimal("0.0001")


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SupplyAdjustmentSummary:
    run_id: int
    rows_written: int = 0
    stock_source: str = "forecast_stock_weekly"
    stockout_count: int = 0
    excess_count: int = 0
    products_processed: int = 0
    weeks_processed: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "rows_written": self.rows_written,
            "stock_source": self.stock_source,
            "stockout_count": self.stockout_count,
            "excess_count": self.excess_count,
            "products_processed": self.products_processed,
            "weeks_processed": self.weeks_processed,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Pure computation helpers
# ---------------------------------------------------------------------------

def _to_dec(v: Any) -> Decimal:
    """Safely coerce any numeric-ish value to Decimal, defaulting to 0."""
    if v is None:
        return Decimal("0")
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


def compute_supply_row(
    base_forecast: Decimal,
    stock_on_hand: Decimal | None,
    inbound_orders: Decimal | None,
) -> dict[str, Any]:
    """
    Pure function: derive supply-adjusted fields from three inputs.

    Returns a dict ready to pass into ForecastSupplyAdjusted(**row).
    """
    soh = _to_dec(stock_on_hand)
    inbound = _to_dec(inbound_orders)
    base = _to_dec(base_forecast)

    available = (soh + inbound).quantize(_QUANT, rounding=ROUND_HALF_UP)
    adjusted = min(base, available).quantize(_QUANT, rounding=ROUND_HALF_UP)

    stockout = available < base
    excess = base > Decimal("0") and available > (base * Decimal("2"))

    return {
        "stock_on_hand": soh,
        "inbound_orders": inbound,
        "available_stock": available,
        "adjusted_forecast": adjusted,
        "stockout_flag": stockout,
        "excess_stock_flag": excess,
    }


def generate_mock_stock(
    base_forecast: Decimal,
    product_code: str,
    forecast_week: date,
    *,
    seed_factor: float = 1.2,
) -> tuple[Decimal, Decimal]:
    """
    Generate deterministic-but-varied mock SOH and inbound values for testing.

    The seed is derived from product_code + week so results are stable across
    repeated calls for the same inputs.
    """
    seed = hash((product_code, str(forecast_week))) & 0xFFFF_FFFF
    rng = random.Random(seed)

    base = float(_to_dec(base_forecast))
    soh = Decimal(str(round(base * seed_factor * (0.5 + rng.random()), 4)))
    inbound = Decimal(str(round(base * 0.3 * rng.random(), 4)))
    return soh, inbound


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

class SupplyAdjustmentService:
    """
    Computes and persists the supply-adjusted forecast for one forecast run.

    Usage:
        svc = SupplyAdjustmentService()
        summary = svc.compute(run_id, forecast_db)
        forecast_db.commit()
    """

    def compute(
        self,
        run_id: int,
        forecast_db: Session,
        *,
        use_mock_data: bool = False,
    ) -> SupplyAdjustmentSummary:
        """
        Main entry point.  Idempotent — deletes any existing rows for this run
        before inserting fresh ones.
        """
        summary = SupplyAdjustmentSummary(run_id=run_id)

        # 1. Load best-model forecast rows for this run
        best_rows = (
            forecast_db.query(ForecastResultWeekly)
            .filter(
                ForecastResultWeekly.run_id == run_id,
                ForecastResultWeekly.is_best_model == True,  # noqa: E712
            )
            .order_by(
                ForecastResultWeekly.product_code,
                ForecastResultWeekly.warehouse_code,
                ForecastResultWeekly.forecast_week,
            )
            .all()
        )

        if not best_rows:
            summary.errors.append(
                f"No best-model forecast rows found for run_id={run_id}. "
                "Execute the forecast run first."
            )
            return summary

        # 2. Build a stock lookup dict: (product_code, warehouse_code, week) → row
        stock_lookup: dict[tuple[str, str | None, date], ForecastStockWeekly] = {}
        actual_source = "forecast_stock_weekly"

        if not use_mock_data:
            stock_lookup, actual_source = self._load_stock_lookup(run_id, forecast_db)
            if not stock_lookup:
                logger.info(
                    "run_id=%d: no stock data found in forecast_stock_weekly, falling back to mock",
                    run_id,
                )
                actual_source = "mock"

        summary.stock_source = actual_source

        # 3. Delete existing rows for this run (idempotent)
        forecast_db.execute(
            delete(ForecastSupplyAdjusted).where(
                ForecastSupplyAdjusted.run_id == run_id
            )
        )

        # 4. Compute and collect rows to insert
        new_rows: list[ForecastSupplyAdjusted] = []
        seen_products: set[str] = set()
        seen_weeks: set[date] = set()

        for r in best_rows:
            pcode = str(r.product_code)
            wcode = str(r.warehouse_code) if r.warehouse_code is not None else None
            fweek: date = r.forecast_week  # type: ignore[assignment]
            base = _to_dec(r.forecast_units)

            seen_products.add(pcode)
            seen_weeks.add(fweek)

            if actual_source == "mock":
                soh, inbound = generate_mock_stock(base, pcode, fweek)
            else:
                stock_row = stock_lookup.get((pcode, wcode, fweek))
                if stock_row is None:
                    # Partial stock data: fall back to mock for this row
                    soh, inbound = generate_mock_stock(base, pcode, fweek)
                else:
                    soh = _to_dec(stock_row.soh_units)
                    inbound = (
                        _to_dec(stock_row.in_transit_units)
                        + _to_dec(stock_row.open_po_units)
                    )

            computed = compute_supply_row(base, soh, inbound)
            if computed["stockout_flag"]:
                summary.stockout_count += 1
            if computed["excess_stock_flag"]:
                summary.excess_count += 1

            new_rows.append(
                ForecastSupplyAdjusted(
                    run_id=run_id,
                    product_code=pcode,
                    warehouse_code=wcode,
                    forecast_week=fweek,
                    base_forecast=base,
                    stock_source=actual_source,
                    **computed,
                )
            )

        forecast_db.bulk_save_objects(new_rows)

        summary.rows_written = len(new_rows)
        summary.products_processed = len(seen_products)
        summary.weeks_processed = len(seen_weeks)

        logger.info(
            "run_id=%d supply-adjusted: %d rows, %d products, source=%s, "
            "stockouts=%d, excess=%d",
            run_id,
            summary.rows_written,
            summary.products_processed,
            actual_source,
            summary.stockout_count,
            summary.excess_count,
        )
        return summary

    # -------------------------------------------------------------------------

    def _load_stock_lookup(
        self,
        run_id: int,
        forecast_db: Session,
    ) -> tuple[dict[tuple[str, str | None, date], ForecastStockWeekly], str]:
        """
        Try to load stock data for this run first, then fall back to any
        available stock rows for matching product+warehouse.

        Returns (lookup_dict, source_label).
        """
        # Attempt 1: run-scoped stock rows
        run_stock = (
            forecast_db.query(ForecastStockWeekly)
            .filter(ForecastStockWeekly.run_id == run_id)
            .all()
        )
        if run_stock:
            return (
                {
                    (str(s.product_code), str(s.warehouse_code), s.week_start): s  # type: ignore[misc]
                    for s in run_stock
                },
                "forecast_stock_weekly",
            )

        # Attempt 2: most-recent available stock for matching product+warehouse
        # (useful when stock_weekly was populated in a different run)
        recent_stock = (
            forecast_db.query(ForecastStockWeekly)
            .order_by(ForecastStockWeekly.week_start.desc())
            .limit(50_000)
            .all()
        )
        if recent_stock:
            lookup: dict[tuple[str, str | None, date], ForecastStockWeekly] = {}
            for s in recent_stock:
                key: tuple[str, str | None, date] = (str(s.product_code), str(s.warehouse_code), s.week_start)  # type: ignore[assignment]
                if key not in lookup:
                    lookup[key] = s
            return lookup, "forecast_stock_weekly_any_run"

        return {}, "mock"


# ---------------------------------------------------------------------------
# Read-side helper (used by GET endpoint)
# ---------------------------------------------------------------------------

def get_supply_adjusted_rows(
    run_id: int,
    forecast_db: Session,
    *,
    product_code: str | None = None,
    warehouse_code: str | None = None,
    stockout_only: bool = False,
    excess_only: bool = False,
    limit: int = 5000,
) -> list[ForecastSupplyAdjusted]:
    """Query supply-adjusted rows for a given run with optional filters."""
    q = (
        forecast_db.query(ForecastSupplyAdjusted)
        .filter(ForecastSupplyAdjusted.run_id == run_id)
        .order_by(
            ForecastSupplyAdjusted.product_code,
            ForecastSupplyAdjusted.warehouse_code,
            ForecastSupplyAdjusted.forecast_week,
        )
    )
    if product_code:
        q = q.filter(ForecastSupplyAdjusted.product_code == product_code)
    if warehouse_code:
        q = q.filter(ForecastSupplyAdjusted.warehouse_code == warehouse_code)
    if stockout_only:
        q = q.filter(ForecastSupplyAdjusted.stockout_flag == True)  # noqa: E712
    if excess_only:
        q = q.filter(ForecastSupplyAdjusted.excess_stock_flag == True)  # noqa: E712
    return q.limit(limit).all()
