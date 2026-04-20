"""
LegacyFileExporter — generates CSV and manifest files per forecast run.

Output folder layout:
    {FORECAST_OUTPUT_ROOT}/{run_uuid}/
        transformed_total.csv               — weekly sales snapshot (training base)
        prophet_predictions.csv             — all Prophet model variant rows
        xgboost_predictions.csv             — all XGBoost model variant rows
        final_output_w_history.csv          — all model rows including history actuals
        {inference_date}_final_output_backup.csv  — dated copy of final_output
        complete_time_series_dataset.csv    — all rows for all models + history
        run_manifest.json                   — metadata, row counts, parity summary

Column names in CSV files use the legacy Vertex output shape:
    AAH_Product_Code, Product_Name, Inference_Date, Forecast_Week,
    Actual, Interpolated_Values, Forecast, Model, Model_Details,
    Mean_Absolute_Percentage_Error, Mean_Absolute_Error,
    Is_Best_Model, Outlier, Predicted_Best_Model_Bool

Configuration (via .env / config.py):
    FORECAST_OUTPUT_ROOT          — root directory for output folders
    LEGACY_FILE_EXPORT_ENABLED    — master switch (default: false)

Usage:
    exporter = LegacyFileExporter()
    result = exporter.export_run(forecast_db, run)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.forecast_mysql_models import (
    ForecastResultWeekly,
    ForecastRun,
    ForecastSalesWeekly,
    ForecastTrainingSeriesWeekly,
)

logger = logging.getLogger(__name__)

# Mapping from internal column names to legacy CSV column names
_RESULT_RENAME: dict[str, str] = {
    "product_code":                    "AAH_Product_Code",
    "product_name":                    "Product_Name",
    "inference_date":                  "Inference_Date",
    "forecast_week":                   "Forecast_Week",
    "actual_units":                    "Actual",
    "interpolated_units":              "Interpolated_Values",
    "forecast_units":                  "Forecast",
    "model_name":                      "Model",
    "model_details":                   "Model_Details",
    "mape":                            "Mean_Absolute_Percentage_Error",
    "mae":                             "Mean_Absolute_Error",
    "is_best_model":                   "Is_Best_Model",
    "outlier_flag":                    "Outlier",
    "predicted_best_model_bool":       "Predicted_Best_Model_Bool",
}

_TRAINING_RENAME: dict[str, str] = {
    "product_code":    "AAH_Product_Code",
    "warehouse_code":  "Warehouse_Code",
    "week_start":      "Week_Start",
    "qty":             "Units_Sold",
    "adjusted_qty":    "Adjusted_Units",
    "interpolated_units": "Interpolated_Units",
    "is_outlier_flagged":  "Outlier_Flag",
    "series_variant":  "Series_Variant",
}

_LEGACY_COLS = list(_RESULT_RENAME.values())


class LegacyFileExporter:
    """
    Exports forecast results from MySQL to CSV files in a per-run folder.

    Steps:
      1. Read forecast_results_weekly for the run.
      2. Read forecast_training_series_weekly for context.
      3. Write all CSV files.
      4. Write run_manifest.json.
      5. Return an ExportFilesResult dict.
    """

    def __init__(self, output_root: str | None = None) -> None:
        from app.config import settings
        self.output_root = Path(
            output_root or getattr(settings, "forecast_output_root", "forecast_output")
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export_run(
        self,
        forecast_db: Session,
        run: ForecastRun,
        parity_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Generate all CSV files for a completed run.

        Parameters
        ----------
        forecast_db     : MySQL forecast session (source).
        run             : ForecastRun ORM row (must have id, run_uuid, inference_date).
        parity_summary  : Optional parity validation result to embed in the manifest.

        Returns a dict with:
            output_path, files_generated, row_counts, errors
        """
        run_id = int(str(run.id))
        run_uuid = str(run.run_uuid)
        inference_date = run.inference_date  # date object

        run_dir = self.output_root / run_uuid
        run_dir.mkdir(parents=True, exist_ok=True)

        errors: list[str] = []
        files_generated: list[str] = []
        row_counts: dict[str, int] = {}

        # --- 1. Load all results for this run ----------------------------
        results_df = self._load_results(forecast_db, run_id)
        training_df = self._load_training(forecast_db, run_id)

        if results_df.empty:
            msg = f"No forecast_results_weekly rows found for run_id={run_id}"
            logger.warning(msg)
            errors.append(msg)

        # --- 2. Write CSV files -----------------------------------------
        files_spec: list[tuple[str, pd.DataFrame | None, bool]] = [
            # (filename, dataframe, is_results_shaped)
            ("transformed_total.csv",          training_df,               False),
            ("prophet_predictions.csv",         self._prophet_df(results_df),   True),
            ("xgboost_predictions.csv",         self._xgboost_df(results_df),   True),
            ("final_output_w_history.csv",      results_df,                True),
            (
                f"{inference_date}_final_output_backup.csv",
                results_df,
                True,
            ),
            ("complete_time_series_dataset.csv", results_df,               True),
        ]

        for fname, df, is_result in files_spec:
            if df is None or df.empty:
                errors.append(f"No data for {fname}")
                continue
            try:
                out_df = self._apply_result_rename(df) if is_result else self._apply_training_rename(df)
                out_path = run_dir / fname
                out_df.to_csv(out_path, index=False)
                files_generated.append(str(out_path))
                row_counts[fname] = len(out_df)
                logger.debug("Wrote %s (%d rows)", out_path, len(out_df))
            except Exception as exc:
                msg = f"Failed writing {fname}: {exc}"
                logger.exception(msg)
                errors.append(msg)

        # --- 3. Write run_manifest.json ---------------------------------
        manifest = self._build_manifest(
            run=run,
            row_counts=row_counts,
            files_generated=files_generated,
            parity_summary=parity_summary,
            errors=errors,
        )
        manifest_path = run_dir / "run_manifest.json"
        try:
            manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
            files_generated.append(str(manifest_path))
            logger.info("LegacyFileExporter: manifest written → %s", manifest_path)
        except Exception as exc:
            errors.append(f"Failed writing run_manifest.json: {exc}")

        logger.info(
            "LegacyFileExporter: run_id=%d files=%d errors=%d output=%s",
            run_id, len(files_generated), len(errors), run_dir,
        )
        return {
            "output_path": str(run_dir),
            "files_generated": files_generated,
            "row_counts": row_counts,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Data loaders
    # ------------------------------------------------------------------

    @staticmethod
    def _load_results(forecast_db: Session, run_id: int) -> pd.DataFrame:
        """
        Load forecast results for this run and return a DataFrame using the
        canonical legacy column names produced by build_legacy_export_dataframe.
        This is the single source of truth for the column mapping.
        """
        from app.services.forecasting.legacy_output_exporter import build_legacy_export_dataframe

        rows = (
            forecast_db.query(ForecastResultWeekly)
            .filter(ForecastResultWeekly.run_id == run_id)
            .order_by(
                ForecastResultWeekly.product_code,
                ForecastResultWeekly.forecast_week,
                ForecastResultWeekly.model_details,
            )
            .all()
        )
        if not rows:
            return pd.DataFrame()

        df, _summary = build_legacy_export_dataframe(rows, run_id)
        return df

    @staticmethod
    def _load_training(forecast_db: Session, run_id: int) -> pd.DataFrame:
        rows = (
            forecast_db.query(ForecastTrainingSeriesWeekly)
            .filter(ForecastTrainingSeriesWeekly.run_id == run_id)
            .order_by(
                ForecastTrainingSeriesWeekly.product_code,
                ForecastTrainingSeriesWeekly.week_start,
                ForecastTrainingSeriesWeekly.series_variant,
            )
            .all()
        )
        if not rows:
            return pd.DataFrame()

        records = []
        for r in rows:
            records.append({
                "product_code":        str(r.product_code),
                "warehouse_code":      str(r.warehouse_code) if r.warehouse_code is not None else None,
                "week_start":          r.week_start,
                "qty":                 float(str(r.qty)) if r.qty is not None else None,
                "adjusted_qty":        float(str(r.adjusted_qty)) if r.adjusted_qty is not None else None,
                "interpolated_units":  float(str(r.interpolated_units)) if r.interpolated_units is not None else None,
                "is_outlier_flagged":  bool(r.is_outlier_flagged),
                "series_variant":      str(r.series_variant),
            })
        return pd.DataFrame.from_records(records)

    # ------------------------------------------------------------------
    # DataFrame filters for per-model files
    # ------------------------------------------------------------------

    @staticmethod
    def _prophet_df(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        col = "Model" if "Model" in df.columns else "model_name"
        mask = df[col].str.startswith("Prophet", na=False)
        return df[mask].copy()

    @staticmethod
    def _xgboost_df(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        col = "Model" if "Model" in df.columns else "model_name"
        mask = df[col].str.startswith("XGBoost", na=False)
        return df[mask].copy()

    # ------------------------------------------------------------------
    # Column rename helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_result_rename(df: pd.DataFrame) -> pd.DataFrame:
        """
        Ensure the DataFrame uses legacy column names and selects only the
        expected output columns.

        _load_results now returns a DataFrame already in legacy column names
        (via build_legacy_export_dataframe), so the rename dict is a no-op for
        normal usage but is retained as a safety net for any callers that still
        pass an internal-named DataFrame.
        """
        out = df.rename(columns=_RESULT_RENAME)
        keep = _LEGACY_COLS + (["warehouse_code"] if "warehouse_code" in out.columns else [])
        available = [c for c in keep if c in out.columns]
        return out[available]

    @staticmethod
    def _apply_training_rename(df: pd.DataFrame) -> pd.DataFrame:
        return df.rename(columns=_TRAINING_RENAME)

    # ------------------------------------------------------------------
    # Manifest builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_manifest(
        run: ForecastRun,
        row_counts: dict[str, int],
        files_generated: list[str],
        parity_summary: dict[str, Any] | None,
        errors: list[str],
    ) -> dict[str, Any]:
        return {
            "run_id":         int(str(run.id)),
            "run_uuid":       str(run.run_uuid),
            "run_status":     str(run.run_status),
            "inference_date": str(run.inference_date),
            "horizon_weeks":  int(str(run.horizon_weeks)),
            "generated_at":   datetime.utcnow().isoformat(),
            "files":          files_generated,
            "row_counts":     row_counts,
            "parity":         parity_summary or {"parity_checked": False},
            "errors":         errors,
        }
