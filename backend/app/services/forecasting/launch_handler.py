"""
Launch handler — MySQL-backed forecasting for NPI / launch-stage products.

Two modes, selected automatically:

  Analogue mode (profile.analogue_product_code is set)
      Load the analogue product's sales history from forecast_sales_weekly.
      Fit a Prophet model on the analogue series.
      Scale the forecast by launch_scale_factor (from profile.notes JSON).

  Seeded sparse mode (no analogue, product has some history)
      Run Prophet on the product's own sparse series (even < 12 weeks).

  Zero-seeded mode (no analogue, no history)
      Flat forecast at zero (no category avg — category field removed from schema).

All launch forecasts carry result_meta.strategy = "launch" and
is_best_model = False.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.forecast_mysql_models import ForecastProductProfile, ForecastSalesWeekly

logger = logging.getLogger(__name__)

_LAUNCH_MODEL_CODE = "launch_analogue"
_SPARSE_MODEL_CODE = "launch_sparse_prophet"
_SEEDED_MODEL_CODE = "launch_seeded_zero"


class LaunchHandler:
    """Produces forecasts for launch/NPI products. Uses MySQL forecast_db."""

    def __init__(self, horizon_weeks: int = 52) -> None:
        self.horizon_weeks = horizon_weeks

    def forecast(
        self,
        forecast_db: Session,
        product_code: str,
        warehouse_code: str,
        train_end: date,
        profile: ForecastProductProfile | None,
    ) -> tuple[pd.DataFrame, str]:
        """
        Returns (forecast_df, model_code).
        forecast_df has columns [ds (date), yhat, yhat_lower, yhat_upper].
        """
        analogue_code = (
            str(profile.analogue_product_code)
            if profile and profile.analogue_product_code is not None
            else None
        )
        scale = self._read_scale_factor(profile)

        if analogue_code:
            fc = self._forecast_via_analogue(forecast_db, analogue_code, warehouse_code, train_end, scale)
            if fc is not None:
                return fc, _LAUNCH_MODEL_CODE

        own_series = self._load_own_series(forecast_db, product_code, warehouse_code, train_end)
        if len(own_series) >= 4:
            fc = self._forecast_sparse_prophet(own_series)
            if fc is not None:
                return fc, _SPARSE_MODEL_CODE

        fc = self._forecast_zero_seeded(train_end)
        return fc, _SEEDED_MODEL_CODE

    # ------------------------------------------------------------------
    # Analogue mode
    # ------------------------------------------------------------------

    def _forecast_via_analogue(
        self,
        forecast_db: Session,
        analogue_code: str,
        warehouse_code: str,
        train_end: date,
        scale: float,
    ) -> pd.DataFrame | None:
        series = self._load_own_series(forecast_db, analogue_code, warehouse_code, train_end)
        if len(series) < 4:
            logger.debug("Analogue %s/%s has insufficient data; falling back.", analogue_code, warehouse_code)
            return None
        fc = self._forecast_sparse_prophet(series)
        if fc is None:
            return None
        fc["yhat"] = (fc["yhat"] * scale).clip(lower=0)
        fc["yhat_lower"] = (fc["yhat_lower"] * scale).clip(lower=0)
        fc["yhat_upper"] = (fc["yhat_upper"] * scale).clip(lower=0)
        return fc

    # ------------------------------------------------------------------
    # Sparse-Prophet mode
    # ------------------------------------------------------------------

    def _forecast_sparse_prophet(self, series: pd.DataFrame) -> pd.DataFrame | None:
        try:
            from prophet import Prophet  # type: ignore[import-untyped]
        except ImportError:
            logger.error("prophet not installed; cannot run sparse Prophet for launch product.")
            return None

        train = series[["ds", "y"]].copy()
        train["ds"] = pd.to_datetime(train["ds"])
        train["y"] = train["y"].astype(float).clip(lower=0)
        try:
            model = Prophet(
                yearly_seasonality=(len(train) >= 52),
                weekly_seasonality=False,
                daily_seasonality=False,
                changepoint_prior_scale=0.3,
                seasonality_prior_scale=5.0,
            )
            model.fit(train, iter=300)
        except Exception as exc:
            logger.warning("Sparse Prophet fit failed: %s", exc)
            return None

        last_ds = train["ds"].max()
        future_dates = [last_ds + pd.Timedelta(days=7 * h) for h in range(1, self.horizon_weeks + 1)]
        future_df = pd.DataFrame({"ds": future_dates})
        fc = model.predict(future_df)[["ds", "yhat", "yhat_lower", "yhat_upper"]]
        fc["yhat"] = fc["yhat"].clip(lower=0)
        fc["yhat_lower"] = fc["yhat_lower"].clip(lower=0)
        fc["ds"] = fc["ds"].dt.date
        return fc.reset_index(drop=True)

    # ------------------------------------------------------------------
    # Zero-seeded mode
    # ------------------------------------------------------------------

    def _forecast_zero_seeded(self, train_end: date) -> pd.DataFrame:
        rows = []
        for h in range(1, self.horizon_weeks + 1):
            ds = train_end + timedelta(days=7 * h)
            rows.append({"ds": ds, "yhat": 0.0, "yhat_lower": 0.0, "yhat_upper": 0.0})
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _load_own_series(
        self,
        forecast_db: Session,
        product_code: str,
        warehouse_code: str,
        train_end: date,
    ) -> pd.DataFrame:
        rows = (
            forecast_db.query(ForecastSalesWeekly)
            .filter(
                ForecastSalesWeekly.product_code == product_code,
                ForecastSalesWeekly.warehouse_code == warehouse_code,
                ForecastSalesWeekly.week_start <= train_end,
            )
            .order_by(ForecastSalesWeekly.week_start)
            .all()
        )
        if not rows:
            return pd.DataFrame(columns=["ds", "y"])
        return pd.DataFrame([
            {"ds": r.week_start, "y": float(str(r.units_sold if r.units_sold is not None else 0))}
            for r in rows
        ])

    @staticmethod
    def _read_scale_factor(profile: ForecastProductProfile | None) -> float:
        if profile is None or profile.notes is None:
            return 1.0
        try:
            parsed = json.loads(str(profile.notes))
            return float(parsed.get("launch_scale_factor", 1.0))
        except (json.JSONDecodeError, TypeError, ValueError):
            return 1.0
