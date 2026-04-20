"""
Training series builder — MySQL-backed.

Reads forecast_sales_weekly (MySQL), applies product-code merge rules from
forecast_sku_history_rules, enforces the min_history_weeks filter, and
writes the raw series to forecast_training_series_weekly (MySQL).

The outlier_service runs afterwards and populates adjusted_qty +
is_outlier_flagged on the same rows.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.forecast_mysql_models import (
    ForecastRun,
    ForecastSalesWeekly,
    ForecastSkuHistoryRule,
    ForecastTrainingSeriesWeekly,
)

logger = logging.getLogger(__name__)

MIN_HISTORY_WEEKS_GLOBAL = 60


def _int(v: Any) -> int:
    return int(str(v))


class TrainingSeriesBuilder:
    """
    Builds forecast_training_series_weekly rows from forecast_sales_weekly.
    All DB operations target the MySQL forecast database.
    """

    def build(
        self,
        forecast_db: Session,
        run: ForecastRun,
        train_end_week: date,
        min_history_weeks: int = MIN_HISTORY_WEEKS_GLOBAL,
    ) -> dict[str, Any]:
        """
        Load all sales up to train_end_week, apply merge rules, filter by
        minimum history, write to forecast_training_series_weekly.

        Returns: skus_included, skus_excluded, rows_written, exclusions.
        """
        merge_rules = self._load_merge_rules(forecast_db)

        sales_df = self._load_sales(forecast_db, train_end_week)
        if sales_df.empty:
            logger.warning("No forecast_sales_weekly rows found up to %s", train_end_week)
            return {"skus_included": 0, "skus_excluded": 0, "rows_written": 0, "exclusions": []}

        if merge_rules:
            sales_df["product_code"] = sales_df["product_code"].map(
                lambda s: merge_rules.get(s, s)
            )

        sales_df = (
            sales_df.groupby(["product_code", "warehouse_code", "week_start"])
            .agg(units_sold=("units_sold", "sum"))
            .reset_index()
        )

        skus_included = 0
        skus_excluded = 0
        rows_written = 0
        exclusions: list[dict[str, str]] = []

        for (sku, wh), group_df in sales_df.groupby(["product_code", "warehouse_code"]):
            sku_str, wh_str = str(sku), str(wh)
            group_df = group_df.sort_values("week_start").reset_index(drop=True)

            active_count = len(group_df)
            if active_count < min_history_weeks:
                reason = f"insufficient_history ({active_count} < {min_history_weeks} weeks)"
                exclusions.append({"sku": sku_str, "warehouse_code": wh_str, "reason": reason})
                skus_excluded += 1
                continue

            n = self._write_series(forecast_db, run, sku_str, wh_str, group_df)
            rows_written += n
            skus_included += 1

        forecast_db.flush()
        logger.info(
            "TrainingSeriesBuilder: run_id=%d included=%d excluded=%d rows=%d",
            _int(run.id), skus_included, skus_excluded, rows_written,
        )
        return {
            "skus_included": skus_included,
            "skus_excluded": skus_excluded,
            "rows_written": rows_written,
            "exclusions": exclusions,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_sales(self, forecast_db: Session, train_end_week: date) -> pd.DataFrame:
        rows = (
            forecast_db.query(
                ForecastSalesWeekly.product_code,
                ForecastSalesWeekly.warehouse_code,
                ForecastSalesWeekly.week_start,
                ForecastSalesWeekly.units_sold,
            )
            .filter(ForecastSalesWeekly.week_start <= train_end_week)
            .all()
        )
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(
            [
                (
                    str(r.product_code),
                    str(r.warehouse_code) if r.warehouse_code else "AAH",
                    r.week_start,
                    float(str(r.units_sold or 0)),
                )
                for r in rows
            ],
            columns=["product_code", "warehouse_code", "week_start", "units_sold"],
        )

    def _load_merge_rules(self, forecast_db: Session) -> dict[str, str]:
        """Returns {old_product_code: new_product_code} for active merge rules."""
        rules = (
            forecast_db.query(ForecastSkuHistoryRule)
            .filter(ForecastSkuHistoryRule.is_active == True)  # noqa: E712
            .all()
        )
        return {
            str(r.old_product_code): str(r.new_product_code)
            for r in rules
            if r.old_product_code is not None and r.new_product_code is not None
        }

    def _write_series(
        self,
        forecast_db: Session,
        run: ForecastRun,
        product_code: str,
        warehouse_code: str,
        df: pd.DataFrame,
    ) -> int:
        """Upsert raw training series rows for a single (product_code, warehouse)."""
        run_id = _int(run.id)
        count = 0
        for _, row in df.iterrows():
            stmt = mysql_insert(ForecastTrainingSeriesWeekly).values(
                run_id=run_id,
                product_code=product_code,
                warehouse_code=warehouse_code,
                week_start=row["week_start"],
                qty=float(row["units_sold"]),
                is_excluded=False,
                series_variant="raw",
            ).on_duplicate_key_update(
                qty=float(row["units_sold"]),
                is_excluded=False,
            )
            forecast_db.execute(stmt)
            count += 1
        return count
