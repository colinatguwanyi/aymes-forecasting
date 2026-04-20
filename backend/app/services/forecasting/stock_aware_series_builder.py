"""
Stock-aware training series builder — MySQL-backed.

Applies constrained-week handling after StockClassifier has populated
week_classification and is_stock_constrained on forecast_training_series_weekly.

Three handling modes (set via runtime_config.constrained_weeks_handling):

    flag_only            Default. Marks is_stock_constrained=True; models see
                         raw demand unchanged.

    flag_and_exclude     Sets is_excluded=True on constrained rows; emits a
                         diagnostic per excluded week.

    impute_unconstrained Writes estimated unconstrained demand to stock_adjusted_qty.
                         Models consuming *_without_outliers use this value in
                         preference to adjusted_qty.
"""
from __future__ import annotations

import logging
from datetime import date
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.forecast_mysql_models import (
    ForecastRun,
    ForecastRunDiagnostic,
    ForecastTrainingSeriesWeekly,
)
from app.services.forecasting.stock_classifier import CONSTRAINED_CLASSIFICATIONS, WeekClassification

logger = logging.getLogger(__name__)


class ConstrainedWeeksHandling(str, Enum):
    FLAG_ONLY = "flag_only"
    FLAG_AND_EXCLUDE = "flag_and_exclude"
    IMPUTE_UNCONSTRAINED = "impute_unconstrained"


class StockAwareSeriesBuilder:
    """
    Applies stock-aware adjustments to forecast_training_series_weekly.
    All DB operations target the MySQL forecast database via forecast_db.
    """

    def build_stock_adjusted(
        self,
        forecast_db: Session,
        run: ForecastRun,
        handling: ConstrainedWeeksHandling | str = ConstrainedWeeksHandling.FLAG_ONLY,
        low_cover_threshold: float = 2.0,
    ) -> dict[str, Any]:
        handling = ConstrainedWeeksHandling(handling)
        run_id = int(str(run.id))

        rows = (
            forecast_db.query(ForecastTrainingSeriesWeekly)
            .filter(ForecastTrainingSeriesWeekly.run_id == run_id)
            .order_by(
                ForecastTrainingSeriesWeekly.product_code,
                ForecastTrainingSeriesWeekly.warehouse_code,
                ForecastTrainingSeriesWeekly.week_start,
            )
            .all()
        )
        if not rows:
            return {"weeks_flagged": 0, "weeks_excluded": 0, "weeks_imputed": 0, "outlier_conflict_count": 0}

        from collections import defaultdict
        groups: dict[tuple[str, str], list[ForecastTrainingSeriesWeekly]] = defaultdict(list)
        for r in rows:
            groups[(str(r.product_code), str(r.warehouse_code))].append(r)

        weeks_flagged = 0
        weeks_excluded = 0
        weeks_imputed = 0
        outlier_conflicts = 0

        for (sku, wh), group_rows in groups.items():
            group_rows = sorted(
                group_rows,
                key=lambda r: r.week_start if isinstance(r.week_start, date) else date.fromisoformat(str(r.week_start)),  # type: ignore[arg-type]
            )
            result = self._process_group(
                sku, wh, group_rows, handling, low_cover_threshold, run_id, forecast_db
            )
            weeks_flagged += result["flagged"]
            weeks_excluded += result["excluded"]
            weeks_imputed += result["imputed"]
            outlier_conflicts += result["outlier_conflicts"]

        forecast_db.flush()
        logger.info(
            "StockAwareSeriesBuilder run_id=%d mode=%s: flagged=%d excluded=%d imputed=%d conflicts=%d",
            run_id, handling.value, weeks_flagged, weeks_excluded, weeks_imputed, outlier_conflicts,
        )
        return {
            "weeks_flagged": weeks_flagged,
            "weeks_excluded": weeks_excluded,
            "weeks_imputed": weeks_imputed,
            "outlier_conflict_count": outlier_conflicts,
        }

    # ------------------------------------------------------------------
    # Per-group processing
    # ------------------------------------------------------------------

    def _process_group(
        self,
        sku: str,
        wh: str,
        rows: list[ForecastTrainingSeriesWeekly],
        handling: ConstrainedWeeksHandling,
        low_cover_threshold: float,
        run_id: int,
        forecast_db: Session,
    ) -> dict[str, int]:
        flagged = excluded = imputed = conflicts = 0

        qty_arr = np.array(
            [float(str(r.qty)) if r.qty is not None else 0.0 for r in rows],
            dtype=float,
        )
        cls_arr = [
            str(r.week_classification) if r.week_classification is not None else WeekClassification.NORMAL.value
            for r in rows
        ]

        unconstrained_qty = qty_arr.copy()
        for i, c in enumerate(cls_arr):
            if c in (WeekClassification.ZERO_STOCKOUT.value, WeekClassification.CONSTRAINED_LOW_STOCK.value):
                unconstrained_qty[i] = np.nan
        unconstrained_series = pd.Series(unconstrained_qty)
        rolling_mean_unc = unconstrained_series.rolling(12, min_periods=1).mean()
        valid_vals = unconstrained_series.dropna()
        global_mean = float(valid_vals.mean()) if len(valid_vals) > 0 else 0.0

        for i, row in enumerate(rows):
            is_constrained: bool = bool(row.is_stock_constrained)
            if not is_constrained:
                continue

            flagged += 1
            is_outlier: bool = bool(row.is_outlier_flagged)
            cls_val = str(row.week_classification) if row.week_classification is not None else WeekClassification.NORMAL.value

            if is_outlier:
                conflicts += 1
                forecast_db.add(ForecastRunDiagnostic(
                    run_id=run_id,
                    product_code=sku,
                    warehouse_code=wh,
                    diagnostic_level="warning",
                    diagnostic_type="outlier_replaced_constrained_week",
                    message=(
                        f"Week {row.week_start} is both outlier-flagged and stock-constrained "
                        f"({cls_val}). Outlier adjusted_qty may understate true demand."
                    ),
                    payload_json={
                        "week_start": str(row.week_start),
                        "qty": float(str(row.qty)) if row.qty is not None else None,
                        "adjusted_qty": float(str(row.adjusted_qty)) if row.adjusted_qty is not None else None,
                        "classification": cls_val,
                    },
                ))

            if handling == ConstrainedWeeksHandling.FLAG_ONLY:
                pass  # is_stock_constrained already set by classifier

            elif handling == ConstrainedWeeksHandling.FLAG_AND_EXCLUDE:
                if not bool(row.is_excluded):
                    row.is_excluded = True  # type: ignore[assignment]
                    excluded += 1
                    forecast_db.add(ForecastRunDiagnostic(
                        run_id=run_id,
                        product_code=sku,
                        warehouse_code=wh,
                        diagnostic_level="info",
                        diagnostic_type="week_excluded_stock_constrained",
                        message=f"Week {row.week_start} excluded: {cls_val}",
                        payload_json={"week_start": str(row.week_start), "classification": cls_val},
                    ))

            elif handling == ConstrainedWeeksHandling.IMPUTE_UNCONSTRAINED:
                roll_val = rolling_mean_unc.iloc[i]
                imputed_val = self._impute(
                    row=row,
                    cls_val=cls_val,
                    rolling_mean=float(roll_val) if not np.isnan(roll_val) else global_mean,
                    global_mean=global_mean,
                    low_cover_threshold=low_cover_threshold,
                )
                row.stock_adjusted_qty = imputed_val  # type: ignore[assignment]
                imputed += 1

        return {"flagged": flagged, "excluded": excluded, "imputed": imputed, "outlier_conflicts": conflicts}

    @staticmethod
    def _impute(
        row: ForecastTrainingSeriesWeekly,
        cls_val: str,
        rolling_mean: float,
        global_mean: float,
        low_cover_threshold: float,
    ) -> float:
        qty = float(str(row.qty)) if row.qty is not None else 0.0
        soh = float(str(row.soh_units)) if row.soh_units is not None else None
        ref_mean = rolling_mean if rolling_mean > 0 else global_mean

        if cls_val == WeekClassification.ZERO_STOCKOUT.value:
            return max(0.0, ref_mean)

        if cls_val == WeekClassification.CONSTRAINED_LOW_STOCK.value:
            if soh is not None and ref_mean > 0:
                stock_cover = soh / ref_mean
                if stock_cover <= 0:
                    return max(0.0, ref_mean)
                scale = min(4.0, max(1.0, low_cover_threshold / stock_cover))
                return max(0.0, qty * scale)
            return max(0.0, ref_mean)

        return max(0.0, ref_mean)
