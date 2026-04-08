"""
Prophet model wrapper matching the Vertex pipeline variants.

Model codes (exact legacy names):
    Prophet_with_outliers    — trained on raw series
    Prophet_without_outliers — trained on outlier-adjusted series

Prophet is imported lazily so the app starts without the library installed;
a clear ImportError is raised at fit-time if it is absent.

Weekly W-TUE series are passed with ds = week_start (date → datetime).
Prophet is configured for yearly seasonality only — we are already working
at weekly granularity so weekly_seasonality is redundant.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

MODEL_CODE_WITH_OUTLIERS = "Prophet_with_outliers"
MODEL_CODE_WITHOUT_OUTLIERS = "Prophet_without_outliers"


class ModelFitError(RuntimeError):
    """Raised when a model cannot be fitted on the given series."""


class ProphetForecaster:
    """
    Thin wrapper around Facebook Prophet for weekly demand forecasting.

    Parameters
    ----------
    changepoint_prior_scale : float
        Controls flexibility of the trend.
    seasonality_prior_scale : float
        Controls flexibility of the seasonality component.
    """

    def __init__(
        self,
        changepoint_prior_scale: float = 0.05,
        seasonality_prior_scale: float = 10.0,
    ) -> None:
        self.changepoint_prior_scale = changepoint_prior_scale
        self.seasonality_prior_scale = seasonality_prior_scale
        self._model: Any = None
        self._train_df: pd.DataFrame | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(self, df: pd.DataFrame) -> None:
        """
        Fit Prophet on a weekly series.

        Parameters
        ----------
        df : DataFrame with columns [ds (date or datetime), y (float)].
             Rows are sorted ascending; ds must be W-TUE dates.
        """
        try:
            from prophet import Prophet  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "prophet is required for ProphetForecaster. "
                "Run: pip install prophet"
            ) from exc

        if len(df) < 2:
            raise ModelFitError(f"ProphetForecaster requires at least 2 data points; got {len(df)}")

        train = df[["ds", "y"]].copy()
        train["ds"] = pd.to_datetime(train["ds"])
        train["y"] = train["y"].astype(float).clip(lower=0)

        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=False,
            daily_seasonality=False,
            changepoint_prior_scale=self.changepoint_prior_scale,
            seasonality_prior_scale=self.seasonality_prior_scale,
        )
        try:
            model.fit(train, iter=1000)
        except Exception as exc:
            raise ModelFitError(f"Prophet fit failed: {exc}") from exc

        self._model = model
        self._train_df = train

    def predict(self, horizon_weeks: int = 52) -> pd.DataFrame:
        """
        Generate future weekly forecasts.

        Returns
        -------
        DataFrame with columns [ds (date), yhat, yhat_lower, yhat_upper],
        containing exactly horizon_weeks rows for weeks after train_end.
        """
        if self._model is None or self._train_df is None:
            raise RuntimeError("Call fit() before predict()")

        last_ds = pd.Timestamp(self._train_df["ds"].max())
        future_dates = [last_ds + pd.Timedelta(days=7 * h) for h in range(1, horizon_weeks + 1)]
        future_df = pd.DataFrame({"ds": future_dates})

        forecast = self._model.predict(future_df)
        result = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
        result["yhat"] = result["yhat"].clip(lower=0)
        result["yhat_lower"] = result["yhat_lower"].clip(lower=0)
        result["ds"] = result["ds"].dt.date
        return result

    def score_holdout(self, df: pd.DataFrame, holdout_weeks: int = 12) -> tuple[float, float]:
        """
        Evaluate on a hold-out: train on df[:-holdout_weeks], score on df[-holdout_weeks:].

        Returns
        -------
        (mape, mae) as plain floats; (nan, nan) if scoring is not possible.
        """
        try:
            from prophet import Prophet  # type: ignore[import-untyped]
        except ImportError:
            return float("nan"), float("nan")

        if len(df) <= holdout_weeks + 2:
            return float("nan"), float("nan")

        train_df = df.iloc[:-holdout_weeks].copy()
        test_df = df.iloc[-holdout_weeks:].copy()

        train = train_df[["ds", "y"]].copy()
        train["ds"] = pd.to_datetime(train["ds"])
        train["y"] = train["y"].astype(float).clip(lower=0)

        scorer = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=False,
            daily_seasonality=False,
            changepoint_prior_scale=self.changepoint_prior_scale,
            seasonality_prior_scale=self.seasonality_prior_scale,
        )
        try:
            scorer.fit(train, iter=300)
        except Exception:
            return float("nan"), float("nan")

        future = pd.DataFrame({"ds": pd.to_datetime(test_df["ds"])})
        fc = scorer.predict(future)
        actuals = test_df["y"].astype(float).values
        preds = np.maximum(fc["yhat"].values, 0)

        return _mape_mae(actuals, preds)


def _mape_mae(actuals: Any, preds: Any) -> tuple[float, float]:
    """Compute MAPE and MAE; skip weeks where actual=0 for MAPE denominator."""
    act = np.asarray(actuals, dtype=float)
    pred = np.asarray(preds, dtype=float)
    mae = float(np.mean(np.abs(act - pred)))
    mask = act > 0
    if mask.sum() == 0:
        return float("nan"), mae
    mape = float(np.mean(np.abs((act[mask] - pred[mask]) / act[mask])) * 100)
    return mape, mae
