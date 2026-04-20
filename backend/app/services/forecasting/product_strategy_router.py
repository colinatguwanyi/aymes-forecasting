"""
Product strategy router — MySQL-backed.

Routes each (product_code, warehouse_code) in a run to one of:

    mature_history  — full 4-model pipeline (>= min_mature_weeks history)
    sparse_history  — Prophet-only (>= min_sparse_weeks but < min_mature_weeks)
    launch          — analogue/seeded forecast for NPI or insufficient history
    exclude         — skipped (force_strategy=exclude or past discontinue_date)

Decision order:
  1. force_strategy in ForecastProductProfile          (explicit override)
  2. discontinue_date < inference_date                 → exclude
  3. lifecycle_stage in ('npi', 'launch')              → launch
  4. usable_weeks >= min_mature_weeks                  → mature_history
  5. usable_weeks >= min_sparse_weeks                  → sparse_history
  6. otherwise                                         → launch
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.forecast_mysql_models import (
    ForecastProductProfile,
    ForecastRun,
    ForecastRunDiagnostic,
    ForecastTrainingSeriesWeekly,
)

logger = logging.getLogger(__name__)


class ForecastStrategy(str, Enum):
    MATURE_HISTORY = "mature_history"
    SPARSE_HISTORY = "sparse_history"
    LAUNCH = "launch"
    EXCLUDE = "exclude"


_LAUNCH_LIFECYCLE_STAGES = {"npi", "launch"}


class ProductStrategyRouter:
    """
    Determines the forecasting strategy for each (product_code, warehouse_code).
    All DB operations target the MySQL forecast database via forecast_db.
    """

    def route_all(
        self,
        forecast_db: Session,
        run: ForecastRun,
        min_mature_weeks: int = 60,
        min_sparse_weeks: int = 12,
    ) -> dict[tuple[str, str], ForecastStrategy]:
        """Route all products in the run. Returns {(product_code, wh): strategy}."""
        run_id = int(str(run.id))
        train_end: date = (
            run.inference_date
            if isinstance(run.inference_date, date)
            else date.fromisoformat(str(run.inference_date))
        )

        usable_counts = self._usable_week_counts(forecast_db, run_id)

        profiles: dict[str, ForecastProductProfile] = {
            str(p.product_code): p
            for p in forecast_db.query(ForecastProductProfile).all()
        }

        strategies: dict[tuple[str, str], ForecastStrategy] = {}

        for (sku, wh), usable_weeks in usable_counts.items():
            profile = profiles.get(sku)
            strategy = self._decide(
                sku=sku,
                warehouse_code=wh,
                usable_weeks=usable_weeks,
                profile=profile,
                train_end=train_end,
                min_mature_weeks=min_mature_weeks,
                min_sparse_weeks=min_sparse_weeks,
            )
            strategies[(sku, wh)] = strategy

            if strategy == ForecastStrategy.LAUNCH:
                analogue = (
                    str(profile.analogue_product_code)
                    if profile and profile.analogue_product_code is not None
                    else None
                )
                _emit(
                    forecast_db, run_id, sku, wh, "info", "product_routed_launch",
                    f"Routed to launch strategy ({usable_weeks} usable weeks). "
                    + (f"Analogue: {analogue}" if analogue else "No analogue set."),
                    payload={"usable_weeks": usable_weeks, "analogue": analogue},
                )
            elif strategy == ForecastStrategy.EXCLUDE:
                _emit(
                    forecast_db, run_id, sku, wh, "info", "product_excluded",
                    "Product excluded from forecast run (force_strategy=exclude or past discontinue_date).",
                    payload={"usable_weeks": usable_weeks},
                )
            elif strategy == ForecastStrategy.SPARSE_HISTORY:
                _emit(
                    forecast_db, run_id, sku, wh, "warning", "sparse_history",
                    f"Using sparse-history (Prophet-only) path: {usable_weeks} usable weeks "
                    f"(min mature: {min_mature_weeks}).",
                    payload={"usable_weeks": usable_weeks, "min_mature": min_mature_weeks},
                )

        forecast_db.flush()
        counts: dict[str, int] = defaultdict(int)
        for s in strategies.values():
            counts[s.value] += 1
        logger.info("ProductStrategyRouter run_id=%d: %s", run_id, dict(counts))
        return strategies

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _decide(
        sku: str,
        warehouse_code: str,
        usable_weeks: int,
        profile: ForecastProductProfile | None,
        train_end: date,
        min_mature_weeks: int,
        min_sparse_weeks: int,
    ) -> ForecastStrategy:
        if profile and profile.force_strategy is not None:
            try:
                return ForecastStrategy(str(profile.force_strategy))
            except ValueError:
                logger.warning(
                    "Unknown force_strategy '%s' for product_code=%s; ignoring.",
                    profile.force_strategy, sku,
                )

        if profile and profile.discontinue_date is not None:
            disc_raw = profile.discontinue_date
            disc: date = disc_raw if isinstance(disc_raw, date) else date.fromisoformat(str(disc_raw))
            if disc < train_end:  # type: ignore[operator]
                return ForecastStrategy.EXCLUDE

        if (
            profile
            and profile.lifecycle_stage is not None
            and str(profile.lifecycle_stage).lower() in _LAUNCH_LIFECYCLE_STAGES
        ):
            return ForecastStrategy.LAUNCH

        if usable_weeks >= min_mature_weeks:
            return ForecastStrategy.MATURE_HISTORY
        if usable_weeks >= min_sparse_weeks:
            return ForecastStrategy.SPARSE_HISTORY
        return ForecastStrategy.LAUNCH

    @staticmethod
    def _usable_week_counts(forecast_db: Session, run_id: int) -> dict[tuple[str, str], int]:
        rows = (
            forecast_db.query(ForecastTrainingSeriesWeekly)
            .filter(
                ForecastTrainingSeriesWeekly.run_id == run_id,
                ForecastTrainingSeriesWeekly.is_excluded == False,  # noqa: E712
            )
            .all()
        )
        counts: dict[tuple[str, str], int] = defaultdict(int)
        for r in rows:
            cls_str = str(r.week_classification) if r.week_classification is not None else ""
            if cls_str == "launch_gap":
                continue
            counts[(str(r.product_code), str(r.warehouse_code))] += 1
        return dict(counts)


def _emit(
    forecast_db: Session,
    run_id: int,
    product_code: str,
    warehouse_code: str,
    level: str,
    diag_type: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> None:
    forecast_db.add(ForecastRunDiagnostic(
        run_id=run_id,
        product_code=product_code,
        warehouse_code=warehouse_code,
        diagnostic_level=level,
        diagnostic_type=diag_type,
        message=message,
        payload_json=payload,
    ))
