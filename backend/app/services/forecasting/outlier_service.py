"""
Outlier detection and series adjustment — MySQL-backed.

Matches the Vertex pipeline behavior:
  - Compute rolling 4-week mean (r4) and 12-week mean (r12) on the raw series.
  - A point is an outlier if  qty > sigma * max(r4, r12)  and max(r4, r12) > 0.
  - Outlier values are replaced with  perc * max(r4, r12).
  - Default: sigma=3.5, perc=0.5.

The adjusted value is stored in adjusted_qty; qty is never overwritten.
is_outlier_flagged is set to True for detected outliers.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.forecast_mysql_models import ForecastRun, ForecastTrainingSeriesWeekly

logger = logging.getLogger(__name__)

_DEFAULT_SIGMA = 3.5
_DEFAULT_PERC = 0.5
_ROLLING_SHORT = 4
_ROLLING_LONG = 12


class OutlierService:
    """
    Detects and adjusts outliers in weekly demand series.

    All DB operations target the MySQL forecast database via forecast_db.
    """

    def __init__(
        self,
        sigma: float = _DEFAULT_SIGMA,
        perc: float = _DEFAULT_PERC,
    ) -> None:
        self.sigma = sigma
        self.perc = perc

    # ------------------------------------------------------------------
    # Pure-function API (testable without DB)
    # ------------------------------------------------------------------

    def detect_and_adjust(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect outliers and compute adjusted values for a single time series.

        Input: DataFrame with [week_start, qty], sorted ascending.
        Returns: DataFrame with added columns: rolling_4w, rolling_12w,
                 is_outlier, adjusted_qty.
        """
        df = df.sort_values("week_start").reset_index(drop=True).copy()
        qty = df["qty"].astype(float)

        roll4_arr = np.asarray(qty.rolling(_ROLLING_SHORT, min_periods=1).mean(), dtype=float)
        roll12_arr = np.asarray(qty.rolling(_ROLLING_LONG, min_periods=1).mean(), dtype=float)

        ref = np.maximum(roll4_arr, roll12_arr)
        threshold = self.sigma * ref
        qty_arr = np.asarray(qty, dtype=float)
        outlier_mask: np.ndarray = (qty_arr > threshold) & (ref > 0)
        adjusted = qty_arr.copy()
        adjusted[outlier_mask] = self.perc * ref[outlier_mask]

        df["rolling_4w"] = roll4_arr
        df["rolling_12w"] = roll12_arr
        df["is_outlier"] = outlier_mask
        df["adjusted_qty"] = np.maximum(adjusted, 0.0)
        return df

    # ------------------------------------------------------------------
    # DB-backed API
    # ------------------------------------------------------------------

    def process_run(self, forecast_db: Session, run: ForecastRun) -> dict[str, Any]:
        """
        Load training series for the run, detect outliers, and persist
        adjusted_qty + is_outlier_flagged back to forecast_training_series_weekly.

        Returns { outliers_flagged, skus_processed, rows_processed }.
        """
        run_id = int(str(run.id))

        rows = (
            forecast_db.query(ForecastTrainingSeriesWeekly)
            .filter(
                ForecastTrainingSeriesWeekly.run_id == run_id,
                ForecastTrainingSeriesWeekly.is_excluded == False,  # noqa: E712
            )
            .order_by(
                ForecastTrainingSeriesWeekly.product_code,
                ForecastTrainingSeriesWeekly.warehouse_code,
                ForecastTrainingSeriesWeekly.week_start,
            )
            .all()
        )

        if not rows:
            return {"outliers_flagged": 0, "skus_processed": 0, "rows_processed": 0}

        records = [
            {
                "orm_obj": r,
                "product_code": str(r.product_code),
                "warehouse_code": str(r.warehouse_code),
                "week_start": r.week_start,
                "qty": float(str(r.qty)) if r.qty is not None else 0.0,
            }
            for r in rows
        ]
        df = pd.DataFrame(records)

        outliers_flagged = 0
        skus_processed = 0

        for (sku, wh), group in df.groupby(["product_code", "warehouse_code"]):
            group = group.sort_values("week_start").reset_index(drop=True)
            result = self.detect_and_adjust(group[["week_start", "qty"]])

            for i, adj_row in result.iterrows():
                orm_obj = group.iloc[int(str(i))]["orm_obj"]
                is_outlier: bool = bool(adj_row["is_outlier"])
                adj_qty: float = float(adj_row["adjusted_qty"])
                orm_obj.is_outlier_flagged = is_outlier
                orm_obj.adjusted_qty = adj_qty
                if is_outlier:
                    outliers_flagged += 1

            skus_processed += 1

        forecast_db.flush()
        logger.info(
            "OutlierService run_id=%d: %d skus, %d outliers flagged",
            run_id, skus_processed, outliers_flagged,
        )
        return {
            "outliers_flagged": outliers_flagged,
            "skus_processed": skus_processed,
            "rows_processed": len(rows),
        }

    @staticmethod
    def split_raw_adjusted(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Given a DataFrame with [week_start, qty, adjusted_qty],
        return (raw_series, adjusted_series) each with columns [ds, y].
        """
        raw = df[["week_start", "qty"]].rename(columns={"week_start": "ds", "qty": "y"})
        adj = df[["week_start", "adjusted_qty"]].rename(
            columns={"week_start": "ds", "adjusted_qty": "y"}
        )
        return raw.copy(), adj.copy()
