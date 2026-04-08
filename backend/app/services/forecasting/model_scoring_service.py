"""
Model scoring service.

Scores all four Vertex-parity model variants and selects the best model
per (sku, warehouse_code) based on MAPE over a hold-out window.

Tie-break priority (lower index = preferred when MAPE is equal or both NaN):
    1. Prophet_without_outliers
    2. XGBoost_without_outliers
    3. Prophet_with_outliers
    4. XGBoost_with_outliers

The score() method is a pure function: it accepts DataFrames, runs
ProphetForecaster and XGBoostForecaster, and returns a ModelScoreSet
that the engine can persist to forecast_run_models.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.services.forecasting.models.prophet_model import (
    MODEL_CODE_WITH_OUTLIERS as PROPHET_WITH,
    MODEL_CODE_WITHOUT_OUTLIERS as PROPHET_WITHOUT,
    ModelFitError as ProphetFitError,
    ProphetForecaster,
)
from app.services.forecasting.models.xgboost_model import (
    MODEL_CODE_WITH_OUTLIERS as XGB_WITH,
    MODEL_CODE_WITHOUT_OUTLIERS as XGB_WITHOUT,
    ModelFitError as XGBFitError,
    XGBoostForecaster,
)

logger = logging.getLogger(__name__)

# Tie-break order: index 0 = most preferred
TIEBREAK_ORDER: list[str] = [
    PROPHET_WITHOUT,
    XGB_WITHOUT,
    PROPHET_WITH,
    XGB_WITH,
]


@dataclass
class ModelScore:
    model_code: str
    mape: float          # NaN if scoring failed
    mae: float           # NaN if scoring failed
    train_weeks: int
    fit_meta: dict[str, Any] = field(default_factory=dict)
    fit_error: str | None = None
    forecast_df: pd.DataFrame = field(default_factory=pd.DataFrame)  # [ds, yhat, yhat_lower, yhat_upper]


@dataclass
class ModelScoreSet:
    sku: str
    warehouse_code: str
    scores: list[ModelScore]
    best_model_code: str

    def best(self) -> ModelScore:
        return next(s for s in self.scores if s.model_code == self.best_model_code)


class ModelScoringService:
    """
    Runs all four model variants on a (sku, warehouse) training series,
    scores them by MAPE on a hold-out window, and selects the best.
    """

    def __init__(self, holdout_weeks: int = 12, horizon_weeks: int = 52) -> None:
        self.holdout_weeks = holdout_weeks
        self.horizon_weeks = horizon_weeks

    def score(
        self,
        sku: str,
        warehouse_code: str,
        raw_series: pd.DataFrame,
        adjusted_series: pd.DataFrame,
        allowed_models: set[str] | None = None,
    ) -> ModelScoreSet:
        """
        Score all four variants (or a subset if allowed_models is set).
        Each series has columns [ds, y] sorted ascending.

        Parameters
        ----------
        raw_series      : with-outliers input (qty)
        adjusted_series : without-outliers input (adjusted_qty / stock_adjusted_qty)
        allowed_models  : if set, only these model_codes are evaluated
                          (e.g. sparse history path passes only Prophet variants)
        """
        # Series inputs per variant
        series_map: dict[str, pd.DataFrame] = {
            PROPHET_WITH: raw_series,
            PROPHET_WITHOUT: adjusted_series,
            XGB_WITH: raw_series,
            XGB_WITHOUT: adjusted_series,
        }

        target_models = (
            [m for m in TIEBREAK_ORDER if m in allowed_models]
            if allowed_models
            else TIEBREAK_ORDER
        )

        scores: list[ModelScore] = []
        for model_code in target_models:
            series = series_map[model_code].copy()
            score = self._fit_and_score(model_code, series)
            scores.append(score)
            logger.debug(
                "%s / %s / %s: mape=%.2f mae=%.2f",
                sku, warehouse_code, model_code,
                score.mape if not math.isnan(score.mape) else -1,
                score.mae if not math.isnan(score.mae) else -1,
            )

        best_code = self._select_best(scores)
        return ModelScoreSet(
            sku=sku,
            warehouse_code=warehouse_code,
            scores=scores,
            best_model_code=best_code,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fit_and_score(self, model_code: str, series: pd.DataFrame) -> ModelScore:
        """Fit, score hold-out, then refit on full data and generate forecast."""
        train_weeks = len(series)
        last_ds = series["ds"].iloc[-1] if not series.empty else None

        if model_code in (PROPHET_WITH, PROPHET_WITHOUT):
            forecaster: ProphetForecaster | XGBoostForecaster = ProphetForecaster()
            FitErrorClass = ProphetFitError
        else:
            forecaster = XGBoostForecaster()
            FitErrorClass = XGBFitError

        # 1. Hold-out scoring pass
        try:
            mape, mae = forecaster.score_holdout(series, self.holdout_weeks)
        except Exception as exc:
            logger.debug("Hold-out scoring error (%s): %s", model_code, exc)
            mape, mae = float("nan"), float("nan")

        # 2. Full refit on all data + forecast
        forecast_df = pd.DataFrame()
        fit_error: str | None = None
        try:
            forecaster.fit(series)
            if isinstance(forecaster, XGBoostForecaster):
                forecast_df = forecaster.predict(
                    horizon_weeks=self.horizon_weeks, last_date=last_ds
                )
            else:
                forecast_df = forecaster.predict(horizon_weeks=self.horizon_weeks)
        except (ProphetFitError, XGBFitError, Exception) as exc:
            fit_error = str(exc)
            logger.warning("Model fit error (%s): %s", model_code, exc)

        return ModelScore(
            model_code=model_code,
            mape=mape,
            mae=mae,
            train_weeks=train_weeks,
            fit_error=fit_error,
            forecast_df=forecast_df,
        )

    @staticmethod
    def _select_best(scores: list[ModelScore]) -> str:
        """
        Select the model with the lowest MAPE.
        Among equal MAPEs (including all-NaN), prefer by TIEBREAK_ORDER.
        Models with fit errors are deprioritised (treated as MAPE=inf).
        """
        def sort_key(s: ModelScore) -> tuple[float, int]:
            mape_val = float("inf") if (math.isnan(s.mape) or s.fit_error) else s.mape
            priority = TIEBREAK_ORDER.index(s.model_code) if s.model_code in TIEBREAK_ORDER else 99
            return (mape_val, priority)

        best = min(scores, key=sort_key)
        return best.model_code
