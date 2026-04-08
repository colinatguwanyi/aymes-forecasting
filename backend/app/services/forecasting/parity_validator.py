"""
ParityValidator — compares rebuilt forecast output against the legacy Vertex
MySQL table to validate cutover readiness.

Source of truth for comparison:
    aymes_reports.aymes_demand_planning_forecast_by_model  (legacy Vertex output)

Rebuilt output source:
    aymes_forecasting.forecast_results_weekly  (new normalized table)

Validation steps
----------------
1.  Row count by inference_date
2.  Row count by model_details (4 variants)
3.  Distinct SKU counts
4.  Min/max forecast_week
5.  Null rates in key columns
6.  Duplicate key check on (AAH_Product_Code, Inference_Date, Forecast_Week, Model_Details)
7.  Sample value comparison — Forecast, Actual, Interpolated_Values, Is_Best_Model, Outlier

Parity result dict keys
-----------------------
    parity_checked          : bool
    compared_against_inference_date : str
    legacy_row_count        : int
    rebuilt_row_count       : int
    sample_rows_compared    : int
    mismatch_count          : int
    mismatch_types          : list[str]
    parity_status           : "pass" | "warn" | "fail"
    counts_summary          : dict
    null_rates              : dict
    duplicate_keys          : dict
    sample_mismatches       : list[dict]

Configuration (via .env / config.py):
    LEGACY_PARITY_VALIDATION_ENABLED  — master switch
    LEGACY_PARITY_SAMPLE_SIZE         — number of SKUs to sample for value comparison
    LEGACY_PARITY_FAIL_ON_MISMATCH    — whether mismatches should fail the run
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.forecast_mysql_models import ForecastResultWeekly

logger = logging.getLogger(__name__)

# Tolerance for floating-point value comparison (absolute difference).
# Vertex used Decimal(18,4); we tolerate rounding to 4 decimal places.
_FLOAT_TOL = 0.0001

# Legacy table column → rebuilt column
_LEGACY_COL_MAP = {
    "AAH_Product_Code":               "product_code",
    "Product_Name":                   "product_name",
    "Inference_Date":                 "inference_date",
    "Forecast_Week":                  "forecast_week",
    "Actual":                         "actual_units",
    "Interpolated_Values":            "interpolated_units",
    "Forecast":                       "forecast_units",
    "Model":                          "model_name",
    "Model_Details":                  "model_details",
    "Mean_Absolute_Percentage_Error": "mape",
    "Mean_Absolute_Error":            "mae",
    "Is_Best_Model":                  "is_best_model",
    "Outlier":                        "outlier_flag",
    "Predicted_Best_Model_Bool":      "predicted_best_model_bool",
}

# Numeric value columns to compare sample rows on
_VALUE_COLS = ["Forecast", "Actual", "Interpolated_Values",
               "Mean_Absolute_Percentage_Error", "Mean_Absolute_Error"]
_FLAG_COLS  = ["Is_Best_Model", "Outlier", "Predicted_Best_Model_Bool"]


class ParityValidator:
    """
    Validates that the rebuilt forecast output for a given run/inference_date
    matches the legacy Vertex output table closely enough for cutover.
    """

    def __init__(self, legacy_table: str | None = None) -> None:
        from app.config import settings
        self.legacy_table = legacy_table or getattr(
            settings, "legacy_output_live_table",
            "aymes_demand_planning_forecast_by_model",
        )
        self._sample_size: int = int(getattr(settings, "legacy_parity_sample_size", 50))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_run(
        self,
        forecast_db: Session,
        run_id: int,
        inference_date: date,
        sample_size: int | None = None,
    ) -> dict[str, Any]:
        """
        Full parity validation for run_id against the legacy table.

        Parameters
        ----------
        forecast_db    : MySQL session for aymes_forecasting.
        run_id         : The completed run to validate.
        inference_date : Used to filter the legacy table (Inference_Date).
        sample_size    : Override LEGACY_PARITY_SAMPLE_SIZE for this call.

        Returns the parity result dict.
        """
        n_sample = sample_size if sample_size is not None else self._sample_size

        # Load both sides into pandas DataFrames
        rebuilt_df = self._load_rebuilt(forecast_db, run_id)
        legacy_df  = self._load_legacy(inference_date)

        if rebuilt_df.empty and legacy_df.empty:
            return self._empty_result(inference_date, "no data on either side")

        mismatch_types: list[str] = []

        # ---- 1. Row counts -------------------------------------------
        counts = self._compare_counts(rebuilt_df, legacy_df, mismatch_types)

        # ---- 2. Null rates (rebuilt side only) -----------------------
        null_rates = self._null_rates(rebuilt_df)

        # ---- 3. Duplicate key check ----------------------------------
        dup_info = self._check_duplicates(rebuilt_df, legacy_df, mismatch_types)

        # ---- 4. Sample value comparison ------------------------------
        sample_mismatches, n_compared, n_mismatches = self._sample_compare(
            rebuilt_df, legacy_df, n_sample, mismatch_types
        )

        # ---- 5. Determine overall status -----------------------------
        if not mismatch_types:
            parity_status = "pass"
        elif any(t.startswith("row_count") or t.startswith("dup_key") for t in mismatch_types):
            parity_status = "fail"
        else:
            parity_status = "warn"

        return {
            "parity_checked":                    True,
            "compared_against_inference_date":   str(inference_date),
            "legacy_row_count":                  len(legacy_df),
            "rebuilt_row_count":                 len(rebuilt_df),
            "sample_rows_compared":              n_compared,
            "mismatch_count":                    n_mismatches,
            "mismatch_types":                    mismatch_types,
            "parity_status":                     parity_status,
            "counts_summary":                    counts,
            "null_rates":                        null_rates,
            "duplicate_keys":                    dup_info,
            "sample_mismatches":                 sample_mismatches,
        }

    # ------------------------------------------------------------------
    # Data loaders
    # ------------------------------------------------------------------

    @staticmethod
    def _load_rebuilt(forecast_db: Session, run_id: int) -> pd.DataFrame:
        rows = (
            forecast_db.query(ForecastResultWeekly)
            .filter(ForecastResultWeekly.run_id == run_id)
            .all()
        )
        if not rows:
            return pd.DataFrame()

        records = []
        for r in rows:
            records.append({
                "product_code":              str(r.product_code),
                "product_name":              str(r.product_name) if r.product_name is not None else None,
                "inference_date":            r.inference_date,
                "forecast_week":             r.forecast_week,
                "actual_units":              float(str(r.actual_units)) if r.actual_units is not None else None,
                "interpolated_units":        float(str(r.interpolated_units)) if r.interpolated_units is not None else None,
                "forecast_units":            float(str(r.forecast_units)) if r.forecast_units is not None else None,
                "model_name":                str(r.model_name),
                "model_details":             str(r.model_details),
                "mape":                      float(str(r.mape)) if r.mape is not None else None,
                "mae":                       float(str(r.mae)) if r.mae is not None else None,
                "is_best_model":             bool(r.is_best_model) if r.is_best_model is not None else None,
                "outlier_flag":              bool(r.outlier_flag) if r.outlier_flag is not None else None,
                "predicted_best_model_bool": bool(r.predicted_best_model_bool) if r.predicted_best_model_bool is not None else None,
                "warehouse_code":            str(r.warehouse_code) if r.warehouse_code is not None else None,
            })
        return pd.DataFrame.from_records(records)

    def _load_legacy(self, inference_date: date) -> pd.DataFrame:
        """Load the legacy table for the given inference_date using the repository."""
        try:
            from app.services.forecasting.legacy_output_repository import LegacyOutputRepository
            repo = LegacyOutputRepository()
            rows = repo.get_live_rows_for_inference_date(inference_date, limit=500_000)
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame(rows)
        except Exception as exc:
            logger.warning("ParityValidator: could not load legacy table: %s", exc)
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # Comparison helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compare_counts(
        rebuilt: pd.DataFrame,
        legacy: pd.DataFrame,
        mismatch_types: list[str],
    ) -> dict[str, Any]:
        counts: dict[str, Any] = {
            "total": {"legacy": len(legacy), "rebuilt": len(rebuilt)},
        }

        # Row count parity (allow ≤1% tolerance)
        if legacy.empty or rebuilt.empty:
            mismatch_types.append("row_count_one_side_empty")
        else:
            diff_pct = abs(len(legacy) - len(rebuilt)) / max(len(legacy), 1) * 100
            if diff_pct > 1.0:
                mismatch_types.append(f"row_count_diff_{diff_pct:.1f}pct")

        # Per-model_details counts
        if "Model_Details" in legacy.columns and not legacy.empty:
            legacy_model_counts = legacy.groupby("Model_Details").size().to_dict()
            counts["by_model_details_legacy"] = legacy_model_counts

        if "model_details" in rebuilt.columns and not rebuilt.empty:
            rebuilt_model_counts = rebuilt.groupby("model_details").size().to_dict()
            counts["by_model_details_rebuilt"] = rebuilt_model_counts

        # Distinct SKU counts
        if "AAH_Product_Code" in legacy.columns and not legacy.empty:
            counts["distinct_skus_legacy"] = int(legacy["AAH_Product_Code"].nunique())
        if "product_code" in rebuilt.columns and not rebuilt.empty:
            counts["distinct_skus_rebuilt"] = int(rebuilt["product_code"].nunique())

        if "distinct_skus_legacy" in counts and "distinct_skus_rebuilt" in counts:
            if counts["distinct_skus_legacy"] != counts["distinct_skus_rebuilt"]:
                mismatch_types.append("distinct_sku_count_diff")

        # Min/max forecast_week
        if "Forecast_Week" in legacy.columns and not legacy.empty:
            counts["legacy_forecast_week_range"] = {
                "min": str(legacy["Forecast_Week"].min()),
                "max": str(legacy["Forecast_Week"].max()),
            }
        if "forecast_week" in rebuilt.columns and not rebuilt.empty:
            counts["rebuilt_forecast_week_range"] = {
                "min": str(rebuilt["forecast_week"].min()),
                "max": str(rebuilt["forecast_week"].max()),
            }

        return counts

    @staticmethod
    def _null_rates(rebuilt: pd.DataFrame) -> dict[str, float]:
        if rebuilt.empty:
            return {}
        key_cols = [
            "forecast_units", "actual_units", "interpolated_units",
            "is_best_model", "mape", "mae",
        ]
        return {
            col: round(float(rebuilt[col].isna().mean()), 4)
            for col in key_cols
            if col in rebuilt.columns
        }

    @staticmethod
    def _check_duplicates(
        rebuilt: pd.DataFrame,
        legacy: pd.DataFrame,
        mismatch_types: list[str],
    ) -> dict[str, Any]:
        info: dict[str, Any] = {}

        rebuilt_key = ["product_code", "inference_date", "forecast_week", "model_details"]
        if all(c in rebuilt.columns for c in rebuilt_key) and not rebuilt.empty:
            dup_count = int(rebuilt.duplicated(rebuilt_key).sum())
            info["rebuilt_duplicate_keys"] = dup_count
            if dup_count > 0:
                mismatch_types.append(f"rebuilt_duplicate_keys_{dup_count}")

        legacy_key = ["AAH_Product_Code", "Inference_Date", "Forecast_Week", "Model_Details"]
        if all(c in legacy.columns for c in legacy_key) and not legacy.empty:
            dup_count = int(legacy.duplicated(legacy_key).sum())
            info["legacy_duplicate_keys"] = dup_count
            if dup_count > 0:
                mismatch_types.append(f"legacy_duplicate_keys_{dup_count}")

        return info

    def _sample_compare(
        self,
        rebuilt: pd.DataFrame,
        legacy: pd.DataFrame,
        n_sample: int,
        mismatch_types: list[str],
    ) -> tuple[list[dict[str, Any]], int, int]:
        """Compare values for a random sample of SKUs."""
        if rebuilt.empty or legacy.empty:
            return [], 0, 0

        # Identify common SKUs
        rebuilt_skus = set(rebuilt["product_code"].dropna().unique())
        legacy_skus  = set(legacy["AAH_Product_Code"].dropna().unique()) if "AAH_Product_Code" in legacy.columns else set()
        common_skus  = list(rebuilt_skus & legacy_skus)

        if not common_skus:
            mismatch_types.append("no_common_skus")
            return [], 0, 0

        # Sample up to n_sample SKUs
        import random
        random.seed(42)
        sample_skus = random.sample(common_skus, min(n_sample, len(common_skus)))

        # Subset both sides to sample SKUs
        reb_sample = rebuilt[rebuilt["product_code"].isin(sample_skus)].copy()
        leg_sample = legacy[legacy["AAH_Product_Code"].isin(sample_skus)].copy() if "AAH_Product_Code" in legacy.columns else pd.DataFrame()

        if leg_sample.empty:
            return [], len(reb_sample), 0

        # Rename legacy columns to rebuilt names for alignment
        leg_sample = leg_sample.rename(columns={
            "AAH_Product_Code": "product_code",
            "Forecast_Week":    "forecast_week",
            "Model_Details":    "model_details",
            "Forecast":         "forecast_units_leg",
            "Actual":           "actual_units_leg",
            "Interpolated_Values": "interpolated_units_leg",
            "Is_Best_Model":    "is_best_model_leg",
            "Outlier":          "outlier_flag_leg",
            "Mean_Absolute_Percentage_Error": "mape_leg",
        })

        # Merge on composite key
        merge_key = ["product_code", "forecast_week", "model_details"]
        merge_cols = merge_key + [c for c in leg_sample.columns if c.endswith("_leg")]
        leg_merge = leg_sample[[c for c in merge_cols if c in leg_sample.columns]]

        merged = reb_sample.merge(leg_merge, on=merge_key, how="inner")

        mismatches: list[dict[str, Any]] = []

        for _, row in merged.iterrows():
            row_issues: list[str] = []

            # Numeric comparisons
            for reb_col, leg_col in [
                ("forecast_units",    "forecast_units_leg"),
                ("actual_units",      "actual_units_leg"),
                ("interpolated_units","interpolated_units_leg"),
                ("mape",              "mape_leg"),
            ]:
                if reb_col not in row or leg_col not in row:
                    continue
                v_reb = row[reb_col]
                v_leg = row[leg_col]
                if pd.isna(v_reb) and pd.isna(v_leg):
                    continue
                if pd.isna(v_reb) or pd.isna(v_leg):
                    row_issues.append(f"{reb_col}_null_mismatch")
                    continue
                try:
                    if abs(float(v_reb) - float(v_leg)) > _FLOAT_TOL:
                        row_issues.append(f"{reb_col}_value_diff({float(v_reb):.4f} vs {float(v_leg):.4f})")
                except (TypeError, ValueError):
                    pass

            # Flag comparisons
            for reb_col, leg_col in [
                ("is_best_model", "is_best_model_leg"),
                ("outlier_flag",  "outlier_flag_leg"),
            ]:
                if reb_col not in row or leg_col not in row:
                    continue
                v_reb = row[reb_col]
                v_leg = row[leg_col]
                if pd.isna(v_reb) and pd.isna(v_leg):
                    continue
                try:
                    if bool(v_reb) != bool(v_leg):
                        row_issues.append(f"{reb_col}_flag_mismatch({v_reb} vs {v_leg})")
                except (TypeError, ValueError):
                    pass

            if row_issues:
                mismatches.append({
                    "product_code":  str(row["product_code"]),
                    "forecast_week": str(row.get("forecast_week", "")),
                    "model_details": str(row.get("model_details", "")),
                    "issues":        row_issues,
                })

        n_mismatches = len(mismatches)
        if n_mismatches > 0:
            mismatch_types.append(f"value_mismatches_{n_mismatches}")

        return mismatches, len(merged), n_mismatches

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_result(inference_date: date, reason: str) -> dict[str, Any]:
        return {
            "parity_checked":                    False,
            "compared_against_inference_date":   str(inference_date),
            "legacy_row_count":                  0,
            "rebuilt_row_count":                 0,
            "sample_rows_compared":              0,
            "mismatch_count":                    0,
            "mismatch_types":                    [reason],
            "parity_status":                     "warn",
            "counts_summary":                    {},
            "null_rates":                        {},
            "duplicate_keys":                    {},
            "sample_mismatches":                 [],
        }
