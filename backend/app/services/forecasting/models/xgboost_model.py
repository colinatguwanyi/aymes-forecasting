"""
XGBoost time-series forecaster matching the Vertex pipeline variants.

Model codes (exact legacy names):
    XGBoost_with_outliers    — trained on raw series
    XGBoost_without_outliers — trained on outlier-adjusted series

Features used (same as Vertex feature engineering):
    Lag features : lag_1 … lag_8, lag_13, lag_26  (weeks)
    Rolling stats: roll_4_mean, roll_12_mean
    Calendar     : week_of_year, month, year

Future values are generated via recursive (autoregressive) prediction:
each forecast week's lag values are populated from previously predicted
values and trailing actuals.

XGBoost is imported lazily so the app starts without it installed.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MODEL_CODE_WITH_OUTLIERS = "XGBoost_with_outliers"
MODEL_CODE_WITHOUT_OUTLIERS = "XGBoost_without_outliers"

_LAG_FEATURES = [1, 2, 3, 4, 8, 13, 26]
_ROLL_WINDOWS = [4, 12]
_MAX_LAG = max(_LAG_FEATURES)


class ModelFitError(RuntimeError):
    """Raised when a model cannot be fitted on the given series."""


class XGBoostForecaster:
    """
    XGBoost demand forecaster with lag + rolling + calendar features.

    Parameters
    ----------
    n_estimators : int
    max_depth    : int
    learning_rate: float
    """

    def __init__(
        self,
        n_estimators: int = 200,
        max_depth: int = 4,
        learning_rate: float = 0.05,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
    ) -> None:
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.subsample = subsample
        self.colsample_bytree = colsample_bytree
        self._model: Any = None
        self._feature_cols: list[str] = []
        self._train_tail: list[float] = []   # last _MAX_LAG actuals for recursive pred

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------

    @staticmethod
    def _calendar_features(ds_series: pd.Series) -> pd.DataFrame:
        ds = pd.to_datetime(ds_series)
        return pd.DataFrame(
            {
                "week_of_year": ds.dt.isocalendar().week.astype(int).values,
                "month": ds.dt.month.values,
                "year": ds.dt.year.values,
            },
            index=ds_series.index,
        )

    @staticmethod
    def _lag_and_roll_features(y: pd.Series) -> pd.DataFrame:
        feat: dict[str, Any] = {}
        for lag in _LAG_FEATURES:
            feat[f"lag_{lag}"] = y.shift(lag)
        for w in _ROLL_WINDOWS:
            feat[f"roll_{w}_mean"] = y.rolling(w, min_periods=1).mean()
        return pd.DataFrame(feat, index=y.index)

    def _build_feature_matrix(self, df: pd.DataFrame) -> pd.DataFrame:
        """df must have columns [ds, y] sorted ascending."""
        cal = self._calendar_features(df["ds"])
        lag_roll = self._lag_and_roll_features(df["y"])
        combined = pd.concat([cal, lag_roll], axis=1)
        return combined

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(self, df: pd.DataFrame) -> None:
        """
        Fit XGBoost on a weekly series.

        Parameters
        ----------
        df : DataFrame with [ds, y] sorted ascending.
        """
        try:
            import xgboost as xgb  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "xgboost is required for XGBoostForecaster. "
                "Run: pip install xgboost"
            ) from exc

        df = df.sort_values("ds").reset_index(drop=True).copy()
        df["y"] = df["y"].astype(float).clip(lower=0)

        if len(df) < _MAX_LAG + 4:
            raise ModelFitError(
                f"XGBoostForecaster needs at least {_MAX_LAG + 4} rows; got {len(df)}"
            )

        feat_df = self._build_feature_matrix(df)
        valid_idx = feat_df.dropna().index

        if len(valid_idx) < 10:
            raise ModelFitError("Too many NaN lag features; series is too short for XGBoost.")

        X = feat_df.loc[valid_idx]
        y_train = df.loc[valid_idx, "y"]
        self._feature_cols = list(X.columns)

        model = xgb.XGBRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            subsample=self.subsample,
            colsample_bytree=self.colsample_bytree,
            objective="reg:squarederror",
            random_state=42,
            verbosity=0,
        )
        model.fit(X, y_train)
        self._model = model
        self._train_tail = list(df["y"].values[-_MAX_LAG:].astype(float))

    def predict(self, horizon_weeks: int = 52, last_date: Any = None) -> pd.DataFrame:
        """
        Generate future forecasts via recursive prediction.

        Returns DataFrame with [ds (date), yhat, yhat_lower, yhat_upper].
        yhat_lower/upper are set to yhat ± 1 std of recent training residuals
        (approximate; Prophet provides tighter intervals).
        """
        if self._model is None:
            raise RuntimeError("Call fit() before predict()")

        import xgboost as xgb  # type: ignore[import-untyped]

        history = list(self._train_tail)   # rolling buffer of recent values
        predictions: list[float] = []
        future_ds: list[Any] = []

        if last_date is None:
            raise RuntimeError("last_date must be provided (the last training week_start)")

        for h in range(1, horizon_weeks + 1):
            next_date = pd.Timestamp(last_date) + pd.Timedelta(days=7 * h)
            feat = self._make_future_feature_row(next_date, history)
            row_df = pd.DataFrame([feat], columns=self._feature_cols)
            y_hat = max(0.0, float(self._model.predict(row_df)[0]))
            predictions.append(y_hat)
            future_ds.append(next_date.date())
            history.append(y_hat)
            if len(history) > _MAX_LAG:
                history = history[-_MAX_LAG:]

        preds_arr = np.array(predictions)
        std = float(np.std(preds_arr)) if len(preds_arr) > 1 else 0.0
        return pd.DataFrame(
            {
                "ds": future_ds,
                "yhat": preds_arr,
                "yhat_lower": np.maximum(preds_arr - std, 0),
                "yhat_upper": preds_arr + std,
            }
        )

    def score_holdout(self, df: pd.DataFrame, holdout_weeks: int = 12) -> tuple[float, float]:
        """
        Evaluate on a hold-out using a fresh XGBoost trained on df[:-holdout_weeks].

        Returns (mape, mae).
        """
        if len(df) <= holdout_weeks + _MAX_LAG + 4:
            return float("nan"), float("nan")

        scorer = XGBoostForecaster(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
        )
        try:
            train_df = df.iloc[:-holdout_weeks].copy()
            test_df = df.iloc[-holdout_weeks:].copy()
            scorer.fit(train_df)
            last_date = train_df["ds"].iloc[-1]
            fc = scorer.predict(horizon_weeks=holdout_weeks, last_date=last_date)
        except Exception as exc:
            logger.debug("XGBoost holdout scoring failed: %s", exc)
            return float("nan"), float("nan")

        actuals = test_df["y"].astype(float).values
        preds = fc["yhat"].values
        return _mape_mae(actuals, preds)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_future_feature_row(
        self, next_date: pd.Timestamp, history: list[float]
    ) -> dict[str, float]:
        """Build a single feature dict for a future date using buffered history."""
        feat: dict[str, float] = {
            "week_of_year": float(next_date.isocalendar()[1]),
            "month": float(next_date.month),
            "year": float(next_date.year),
        }
        buf = history  # most recent values last
        n = len(buf)
        for lag in _LAG_FEATURES:
            idx = n - lag
            feat[f"lag_{lag}"] = float(buf[idx]) if idx >= 0 else 0.0
        for w in _ROLL_WINDOWS:
            window = buf[-w:] if len(buf) >= w else buf
            feat[f"roll_{w}_mean"] = float(np.mean(window)) if window else 0.0
        return feat


def _mape_mae(actuals: Any, preds: Any) -> tuple[float, float]:
    act = np.asarray(actuals, dtype=float)
    pred = np.asarray(preds, dtype=float)
    mae = float(np.mean(np.abs(act - pred)))
    mask = act > 0
    if mask.sum() == 0:
        return float("nan"), mae
    mape = float(np.mean(np.abs((act[mask] - pred[mask]) / act[mask])) * 100)
    return mape, mae
