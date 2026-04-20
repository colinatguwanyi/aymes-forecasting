"""
Stock-aware demand week classifier — MySQL-backed.

Classifies each (product_code, warehouse_code, week_start) in the training
series as one of:

    normal              — no supply constraint
    zero_true_demand    — zero sales + ample SOH (genuine no-demand week)
    zero_stockout       — zero sales + SOH at or below threshold (missed demand)
    constrained_low_stock — positive sales but stock cover below threshold
    launch_gap          — week is before the product's launch_date

Classification rules (evaluated in order):
  1. If launch stage and week < launch_date → launch_gap
  2. actual_units == 0:
       SOH <= zero_stock_units_threshold  → zero_stockout
       SOH >  zero_stock_units_threshold  → zero_true_demand
       SOH missing                        → zero_true_demand
  3. stock_cover_weeks < low_stock_cover_weeks_threshold → constrained_low_stock
  4. Otherwise → normal

SOH source:
  - Primary:  MySQL forecast_stock_weekly (forecast_db)
  - Fallback: Postgres inventory_snapshots_weekly (pg_db) when staging is empty
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.forecast_mysql_models import (
    ForecastProductProfile,
    ForecastRun,
    ForecastStockWeekly,
    ForecastTrainingSeriesWeekly,
)
from app.models import InventorySnapshotWeekly

logger = logging.getLogger(__name__)


class WeekClassification(str, Enum):
    NORMAL = "normal"
    ZERO_TRUE_DEMAND = "zero_true_demand"
    ZERO_STOCKOUT = "zero_stockout"
    CONSTRAINED_LOW_STOCK = "constrained_low_stock"
    LAUNCH_GAP = "launch_gap"


CONSTRAINED_CLASSIFICATIONS = {
    WeekClassification.ZERO_STOCKOUT,
    WeekClassification.CONSTRAINED_LOW_STOCK,
}

_DEFAULT_ZERO_STOCK_THRESHOLD = 5.0
_DEFAULT_LOW_COVER_THRESHOLD = 2.0


@dataclass
class ClassifiedWeek:
    week_start: date
    classification: WeekClassification
    soh_units: float | None
    stock_cover_weeks: float | None
    is_stock_constrained: bool


class StockClassifier:
    """
    Classifies each training week based on SOH availability.

    classify_run() takes:
      forecast_db — MySQL session for training series + staging SOH reads/writes.
      pg_db       — Postgres session for fallback SOH read from inventory_snapshots_weekly.
    """

    def __init__(
        self,
        zero_stock_units_threshold: float = _DEFAULT_ZERO_STOCK_THRESHOLD,
        low_stock_cover_weeks_threshold: float = _DEFAULT_LOW_COVER_THRESHOLD,
    ) -> None:
        self.zero_stock_threshold = zero_stock_units_threshold
        self.low_cover_threshold = low_stock_cover_weeks_threshold

    # ------------------------------------------------------------------
    # Pure-function API
    # ------------------------------------------------------------------

    def classify_series(
        self,
        demand_df: pd.DataFrame,
        soh_df: pd.DataFrame,
        launch_date: date | None = None,
    ) -> list[ClassifiedWeek]:
        """
        Classify every week in demand_df.

        demand_df: [week_start (date), qty (float)] sorted ascending
        soh_df:    [week_start (date), soh_units (float)]
        """
        merged = demand_df.merge(
            soh_df[["week_start", "soh_units"]],
            on="week_start",
            how="left",
        ).sort_values("week_start").reset_index(drop=True)

        qty_arr = np.asarray(merged["qty"].astype(float))
        trailing_nonzero = pd.Series(qty_arr).replace(0, np.nan).rolling(4, min_periods=1).mean()

        results: list[ClassifiedWeek] = []
        for idx, row in enumerate(merged.itertuples()):
            w_raw = getattr(row, "week_start", None)
            w: date = w_raw if isinstance(w_raw, date) else date.fromisoformat(str(w_raw))
            actual = float(str(getattr(row, "qty", 0)))
            soh_raw = getattr(row, "soh_units", None)
            soh: float | None = float(soh_raw) if soh_raw is not None and not pd.isna(soh_raw) else None

            if launch_date is not None and w < launch_date:
                results.append(ClassifiedWeek(
                    week_start=w, classification=WeekClassification.LAUNCH_GAP,
                    soh_units=soh, stock_cover_weeks=None, is_stock_constrained=False,
                ))
                continue

            if actual == 0:
                if soh is not None and soh <= self.zero_stock_threshold:
                    cls = WeekClassification.ZERO_STOCKOUT
                else:
                    cls = WeekClassification.ZERO_TRUE_DEMAND
                results.append(ClassifiedWeek(
                    week_start=w, classification=cls,
                    soh_units=soh, stock_cover_weeks=None,
                    is_stock_constrained=(cls == WeekClassification.ZERO_STOCKOUT),
                ))
                continue

            trailing_avg: float | None = None
            cover_weeks: float | None = None
            try:
                t_val = float(trailing_nonzero.iloc[idx])
                if not np.isnan(t_val) and t_val > 0 and soh is not None:
                    trailing_avg = t_val
                    cover_weeks = soh / trailing_avg
            except Exception:
                pass

            if cover_weeks is not None and cover_weeks < self.low_cover_threshold:
                cls = WeekClassification.CONSTRAINED_LOW_STOCK
            else:
                cls = WeekClassification.NORMAL

            results.append(ClassifiedWeek(
                week_start=w, classification=cls,
                soh_units=soh, stock_cover_weeks=cover_weeks,
                is_stock_constrained=(cls == WeekClassification.CONSTRAINED_LOW_STOCK),
            ))

        return results

    # ------------------------------------------------------------------
    # DB-backed run-level classification
    # ------------------------------------------------------------------

    def classify_run(
        self,
        forecast_db: Session,
        pg_db: Session,
        run: ForecastRun,
        from_week: date,
        to_week: date,
    ) -> dict[str, Any]:
        """
        Classify every week for this run's training series.

        Reads training series and SOH from MySQL forecast_db.
        Falls back to Postgres pg_db for SOH if the MySQL staging table is empty.
        Writes week_classification, soh_units, is_stock_constrained back to MySQL.
        """
        run_id = int(str(run.id))

        ts_rows = (
            forecast_db.query(ForecastTrainingSeriesWeekly)
            .filter(ForecastTrainingSeriesWeekly.run_id == run_id)
            .order_by(
                ForecastTrainingSeriesWeekly.product_code,
                ForecastTrainingSeriesWeekly.warehouse_code,
                ForecastTrainingSeriesWeekly.week_start,
            )
            .all()
        )
        if not ts_rows:
            return {"weeks_classified": 0, "stockouts_found": 0, "constrained_found": 0, "launch_gaps": 0}

        # Build SOH index from MySQL staging first
        soh_rows = (
            forecast_db.query(ForecastStockWeekly)
            .filter(
                ForecastStockWeekly.week_start >= from_week,
                ForecastStockWeekly.week_start <= to_week,
            )
            .all()
        )
        soh_index: dict[tuple[str, date], float] = {}
        if soh_rows:
            for r in soh_rows:
                ws = r.week_start if isinstance(r.week_start, date) else date.fromisoformat(str(r.week_start))
                soh_index[(str(r.product_code), ws)] = float(str(r.soh_units)) if r.soh_units is not None else 0.0
        else:
            # Fallback: read Postgres inventory_snapshots_weekly
            pg_rows = (
                pg_db.query(InventorySnapshotWeekly)
                .filter(
                    InventorySnapshotWeekly.week_start >= from_week,
                    InventorySnapshotWeekly.week_start <= to_week,
                )
                .all()
            )
            for r in pg_rows:
                ws = r.week_start if isinstance(r.week_start, date) else date.fromisoformat(str(r.week_start))
                k: tuple[str, date] = (str(r.sku), ws)
                v = float(str(r.on_hand_qty)) if r.on_hand_qty is not None else 0.0
                if k not in soh_index or str(r.source_type) == "soh":
                    soh_index[k] = v

        # Load product profiles for launch_date
        profiles = {
            str(p.product_code): p
            for p in forecast_db.query(ForecastProductProfile).all()
        }

        groups: dict[tuple[str, str], list[ForecastTrainingSeriesWeekly]] = defaultdict(list)
        for r in ts_rows:
            groups[(str(r.product_code), str(r.warehouse_code))].append(r)

        weeks_classified = 0
        stockouts_found = 0
        constrained_found = 0
        launch_gaps = 0

        for (sku, wh), rows in groups.items():
            profile = profiles.get(sku)
            launch_date: date | None = None
            if profile and profile.launch_date is not None:
                try:
                    launch_date = date.fromisoformat(str(profile.launch_date))
                except ValueError:
                    pass

            demand_df = pd.DataFrame([
                {"week_start": r.week_start, "qty": float(str(r.qty)) if r.qty is not None else 0.0}
                for r in rows
            ])
            soh_data = [
                {"week_start": ws, "soh_units": soh_index[(sku, ws)]}
                for (s, ws) in list(soh_index.keys())
                if s == sku and any(r.week_start == ws for r in rows)
            ]
            soh_df = (
                pd.DataFrame(soh_data)
                if soh_data
                else pd.DataFrame(columns=["week_start", "soh_units"])
            )

            classifications = self.classify_series(demand_df, soh_df, launch_date=launch_date)
            cls_by_week: dict[date, ClassifiedWeek] = {c.week_start: c for c in classifications}

            for row in rows:
                ws_date: date = row.week_start if isinstance(row.week_start, date) else date.fromisoformat(str(row.week_start))  # type: ignore[assignment]
                classified = cls_by_week.get(ws_date)
                if classified is None:
                    continue
                row.week_classification = classified.classification.value  # type: ignore[assignment]
                row.soh_units = classified.soh_units  # type: ignore[assignment]
                row.is_stock_constrained = classified.is_stock_constrained  # type: ignore[assignment]
                weeks_classified += 1
                if classified.classification == WeekClassification.ZERO_STOCKOUT:
                    stockouts_found += 1
                elif classified.classification == WeekClassification.CONSTRAINED_LOW_STOCK:
                    constrained_found += 1
                elif classified.classification == WeekClassification.LAUNCH_GAP:
                    launch_gaps += 1

        forecast_db.flush()
        logger.info(
            "StockClassifier run_id=%d: classified=%d stockouts=%d constrained=%d launch_gaps=%d",
            run_id, weeks_classified, stockouts_found, constrained_found, launch_gaps,
        )
        return {
            "weeks_classified": weeks_classified,
            "stockouts_found": stockouts_found,
            "constrained_found": constrained_found,
            "launch_gaps": launch_gaps,
        }
