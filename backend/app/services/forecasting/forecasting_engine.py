"""
ForecastingEngine — Vertex-parity pipeline orchestrator (MySQL-first).

Full execution order:
  1.  Load ForecastRun from MySQL (status → running)
  2.  MySQLSalesIngestService  → extract from MySQL source + upsert forecast_sales_weekly (MySQL)
  3.  TrainingSeriesBuilder    → apply merge rules, min_history filter
                                → write forecast_training_series_weekly (MySQL)
  4.  OutlierService           → flag + adjust → update adjusted_qty (MySQL)

  [Extension layer — stock-aware]
  4.5 StockClassifier          → join SOH (MySQL staging / Postgres fallback),
                                   classify weeks, write week_classification (MySQL)
  4.6 StockAwareSeriesBuilder  → handle constrained weeks (flag/exclude/impute) (MySQL)
  4.7 ProductStrategyRouter    → route each (product_code, wh) to a strategy (MySQL)

  5.  Per (product_code, warehouse) — dispatched by strategy:
      MATURE_HISTORY:
          Run all 4 model variants.  Persist forecast_results_weekly (MySQL).
      SPARSE_HISTORY:
          Prophet-only (2 variants).
      LAUNCH:
          LaunchHandler → analogue/seeded.  is_best_model=False.
      EXCLUDE:
          Diagnostic emitted; skip.

  6.  Aggregate forecast_run_models counts + mape/mae (MySQL).
  7.  ForecastRun status → success / failed / partial (MySQL).

Sessions:
  pg_db       — Postgres session for platform reads (products, SOH fallback)
  forecast_db — MySQL session for all forecast table reads and writes

adj_series preference for *_without_outliers: stock_adjusted_qty > adjusted_qty > qty.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.forecast_mysql_models import (
    ForecastProductProfile,
    ForecastRun,
    ForecastRunDiagnostic,
    ForecastRunModel,
    ForecastResultWeekly,
    ForecastTrainingSeriesWeekly,
)
from app.models import Product
from app.services.forecasting.launch_handler import LaunchHandler
from app.services.forecasting.model_scoring_service import ModelScoringService, ModelScoreSet
from app.services.forecasting.mysql_sales_ingest import MySQLSalesIngestService
from app.services.forecasting.outlier_service import OutlierService
from app.services.forecasting.product_strategy_router import ForecastStrategy, ProductStrategyRouter
from app.services.forecasting.stock_aware_series_builder import (
    ConstrainedWeeksHandling,
    StockAwareSeriesBuilder,
)
from app.services.forecasting.stock_classifier import StockClassifier
from app.services.forecasting.training_series_builder import TrainingSeriesBuilder

logger = logging.getLogger(__name__)

_SPARSE_HISTORY_MODELS = {"Prophet_with_outliers", "Prophet_without_outliers"}

# Per-model-code metadata for forecast_run_models initialisation
_MODEL_META: list[tuple[str, str, str]] = [
    ("Prophet_with_outliers",    "prophet",  "raw"),
    ("Prophet_without_outliers", "prophet",  "adjusted"),
    ("XGBoost_with_outliers",    "xgboost",  "raw"),
    ("XGBoost_without_outliers", "xgboost",  "adjusted"),
]


def _int(v: Any) -> int:
    return int(str(v))


def _date(v: Any) -> date:
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


def _model_family(model_code: str) -> str:
    lc = model_code.lower()
    if "prophet" in lc:
        return "prophet"
    if "xgboost" in lc:
        return "xgboost"
    return "launch"


@dataclass
class EngineRunSummary:
    run_id: int
    status: str
    rows_ingest: int
    skus_included: int
    skus_excluded: int
    outliers_flagged: int
    skus_forecast: int
    rows_results: int
    errors: list[str]
    strategy_counts: dict[str, int] = field(default_factory=dict)


class ForecastingEngine:
    """
    Orchestrates the full Vertex-parity + stock-aware forecasting pipeline.
    Writes all forecast data to MySQL; reads platform data from Postgres.
    """

    def __init__(
        self,
        sales_ingest: MySQLSalesIngestService | None = None,
        series_builder: TrainingSeriesBuilder | None = None,
        outlier_svc: OutlierService | None = None,
        stock_classifier: StockClassifier | None = None,
        stock_series_builder: StockAwareSeriesBuilder | None = None,
        strategy_router: ProductStrategyRouter | None = None,
        launch_handler: LaunchHandler | None = None,
        scoring_svc: ModelScoringService | None = None,
        holdout_weeks: int = 12,
        horizon_weeks: int = 52,
    ) -> None:
        self.sales_ingest = sales_ingest or MySQLSalesIngestService()
        self.series_builder = series_builder or TrainingSeriesBuilder()
        self.outlier_svc = outlier_svc or OutlierService()
        self.stock_classifier = stock_classifier
        self.stock_series_builder = stock_series_builder or StockAwareSeriesBuilder()
        self.strategy_router = strategy_router or ProductStrategyRouter()
        self.launch_handler_svc = launch_handler or LaunchHandler(horizon_weeks=horizon_weeks)
        self.scoring_svc = scoring_svc or ModelScoringService(
            holdout_weeks=holdout_weeks, horizon_weeks=horizon_weeks
        )
        self.holdout_weeks = holdout_weeks
        self.horizon_weeks = horizon_weeks

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(
        self,
        pg_db: Session,
        forecast_db: Session,
        run: ForecastRun,
        source_config: Any,      # ForecastSourceConfig (MySQL)
        from_date: date,
        to_date: date,
    ) -> EngineRunSummary:
        """Execute the full pipeline. Commits are left to the caller."""
        from app.services.forecasting.forecast_services import ForecastRuntimeConfigService

        run_id = _int(run.id)
        errors: list[str] = []

        _set_status(forecast_db, run, "running")

        # Load stock params from runtime config
        rc_svc = ForecastRuntimeConfigService(forecast_db)
        rc_id = run.runtime_config_id
        stock_params = rc_svc.load_stock_params(int(str(rc_id)) if rc_id is not None else None)
        min_history = int(stock_params.get("min_history_weeks", 60))

        # ---- Step 2: MySQL ingest -------------------------------------------
        logger.info("Engine run_id=%d: starting MySQL ingest", run_id)
        try:
            ingest_counts = self.sales_ingest.ingest(
                pg_db, forecast_db, source_config, from_date, to_date
            )
            rows_ingest = ingest_counts["rows_upserted"]
            _emit(forecast_db, run_id, "info", "ingest_complete",
                  f"Ingested {rows_ingest} weekly rows from MySQL",
                  payload=ingest_counts)
        except Exception as exc:
            msg = f"MySQL ingest failed: {exc}"
            logger.exception(msg)
            errors.append(msg)
            _emit(forecast_db, run_id, "error", "ingest_failed", msg)
            _set_status(forecast_db, run, "failed", error_message=msg)
            return EngineRunSummary(run_id, "failed", 0, 0, 0, 0, 0, 0, errors)

        # ---- Step 3: Build training series ---------------------------------
        logger.info("Engine run_id=%d: building training series", run_id)
        train_end = _date(run.inference_date)
        build_result = self.series_builder.build(
            forecast_db, run, train_end, min_history_weeks=min_history
        )
        skus_included = build_result["skus_included"]
        skus_excluded = build_result["skus_excluded"]

        for exc_info in build_result["exclusions"]:
            _emit(forecast_db, run_id, "info", "insufficient_history",
                  exc_info["reason"],
                  product_code=exc_info["sku"],
                  warehouse_code=exc_info["warehouse_code"])

        if skus_included == 0:
            msg = "No SKUs passed the minimum history filter."
            _emit(forecast_db, run_id, "warning", "no_skus", msg)
            _set_status(forecast_db, run, "failed", error_message=msg)
            return EngineRunSummary(run_id, "failed", rows_ingest, 0, skus_excluded, 0, 0, 0, errors)

        # ---- Step 4: Outlier detection -------------------------------------
        logger.info("Engine run_id=%d: running outlier detection", run_id)
        outlier_result = self.outlier_svc.process_run(forecast_db, run)
        outliers_flagged = outlier_result["outliers_flagged"]

        # ---- Steps 4.5–4.7: Stock-aware extension layer -------------------
        strategies: dict[tuple[str, str], ForecastStrategy] = {}

        if stock_params.get("enable_stock_classification", True):
            logger.info("Engine run_id=%d: stock classification (step 4.5)", run_id)
            classifier = self.stock_classifier or StockClassifier(
                zero_stock_units_threshold=float(stock_params.get("zero_stock_units_threshold", 5.0)),
                low_stock_cover_weeks_threshold=float(stock_params.get("low_stock_cover_weeks_threshold", 2.0)),
            )
            try:
                sc_result = classifier.classify_run(forecast_db, pg_db, run, from_date, train_end)
                _emit(forecast_db, run_id, "info", "stock_classification_complete",
                      f"Classified {sc_result.get('weeks_classified', 0)} weeks; "
                      f"stockouts={sc_result.get('stockouts_found', 0)} "
                      f"constrained={sc_result.get('constrained_found', 0)}",
                      payload=sc_result)
            except Exception as exc:
                logger.warning("Stock classification failed (non-fatal): %s", exc)
                _emit(forecast_db, run_id, "warning", "stock_classification_error",
                      f"Stock classification skipped: {exc}")

            logger.info("Engine run_id=%d: stock-adjusted series (step 4.6)", run_id)
            handling_mode = str(stock_params.get("constrained_weeks_handling", "flag_only"))
            try:
                ss_result = self.stock_series_builder.build_stock_adjusted(
                    forecast_db, run,
                    handling=ConstrainedWeeksHandling(handling_mode),
                    low_cover_threshold=float(stock_params.get("low_stock_cover_weeks_threshold", 2.0)),
                )
                _emit(forecast_db, run_id, "info", "stock_series_complete",
                      f"Stock series mode={handling_mode}: "
                      f"flagged={ss_result.get('weeks_flagged', 0)} "
                      f"excluded={ss_result.get('weeks_excluded', 0)}",
                      payload=ss_result)
            except Exception as exc:
                logger.warning("Stock series builder failed (non-fatal): %s", exc)
                _emit(forecast_db, run_id, "warning", "stock_series_error",
                      f"Stock series adjustment skipped: {exc}")

        if stock_params.get("enable_launch_routing", True):
            logger.info("Engine run_id=%d: routing product strategies (step 4.7)", run_id)
            strategies = self.strategy_router.route_all(
                forecast_db, run,
                min_mature_weeks=int(stock_params.get("min_history_weeks", 60)),
                min_sparse_weeks=int(stock_params.get("min_sparse_history_weeks", 12)),
            )

        # ---- Step 5: Initialise run_model records --------------------------
        _init_run_models(forecast_db, run_id)

        # ---- Step 6: Per-SKU forecasting -----------------------------------
        product_names = _load_product_names(pg_db)
        product_profiles = _load_product_profiles(forecast_db)
        training_rows = self._load_training_rows(forecast_db, run_id)

        skus_forecast = 0
        rows_results = 0
        strategy_counts: dict[str, int] = {}
        # Aggregate mape tracker: {model_code: [mape values]}
        model_mapes: dict[str, list[float]] = {code: [] for code, _, _ in _MODEL_META}

        for (pc, wh), group_df in training_rows.groupby(["product_code", "warehouse_code"]):
            sku_str, wh_str = str(pc), str(wh)
            strategy = strategies.get((sku_str, wh_str), ForecastStrategy.MATURE_HISTORY)
            strategy_counts[strategy.value] = strategy_counts.get(strategy.value, 0) + 1

            if strategy == ForecastStrategy.EXCLUDE:
                skus_excluded += 1
                _emit(forecast_db, run_id, "info", "no_usable_history",
                      "Excluded — no usable history after stock filtering.",
                      product_code=sku_str, warehouse_code=wh_str)
                continue

            try:
                if strategy == ForecastStrategy.LAUNCH:
                    n = self._forecast_launch(
                        forecast_db, run_id, sku_str, wh_str, train_end,
                        profile=product_profiles.get(sku_str),
                        product_name=product_names.get(sku_str),
                    )
                elif strategy == ForecastStrategy.SPARSE_HISTORY:
                    n, score_map = self._forecast_sku(
                        forecast_db, run_id, sku_str, wh_str, group_df, train_end,
                        product_name=product_names.get(sku_str),
                        strategy=strategy,
                        allowed_models=_SPARSE_HISTORY_MODELS,
                    )
                    for code, mape_val in score_map.items():
                        if not math.isnan(mape_val):
                            model_mapes.setdefault(code, []).append(mape_val)
                else:
                    n, score_map = self._forecast_sku(
                        forecast_db, run_id, sku_str, wh_str, group_df, train_end,
                        product_name=product_names.get(sku_str),
                        strategy=strategy,
                    )
                    for code, mape_val in score_map.items():
                        if not math.isnan(mape_val):
                            model_mapes.setdefault(code, []).append(mape_val)
                rows_results += n
                skus_forecast += 1
            except Exception as exc:
                msg = f"Forecast error for {sku_str}/{wh_str}: {exc}"
                logger.exception(msg)
                errors.append(msg)
                _emit(forecast_db, run_id, "error", "forecast_error", msg,
                      product_code=sku_str, warehouse_code=wh_str)

        # ---- Step 7: Finalise run_models aggregate --------------------------
        _finalise_run_models(forecast_db, run_id, skus_forecast, len(errors), model_mapes)

        # ---- Step 8: Finalise run ------------------------------------------
        final_status = "success" if not errors else "partial"
        _set_status(forecast_db, run, final_status)

        # ---- Step 9: Legacy compatibility export (if enabled) ---------------
        legacy_export: dict[str, Any] = {}
        try:
            from app.config import settings
            if bool(getattr(settings, "legacy_output_enabled", False)) and final_status in ("success", "partial"):
                logger.info("Engine run_id=%d: exporting legacy output (step 9)", run_id)
                from app.services.forecasting.legacy_output_exporter import LegacyOutputExporter
                exporter = LegacyOutputExporter()
                legacy_export = exporter.export_run(forecast_db, run_id)
                if legacy_export.get("errors"):
                    for e in legacy_export["errors"]:
                        _emit(forecast_db, run_id, "warning", "legacy_export_error", e)
                else:
                    _emit(
                        forecast_db, run_id, "info", "legacy_export_complete",
                        f"Legacy export: {legacy_export.get('rows_written', 0)} rows written "
                        f"(valid={legacy_export.get('valid')}, swapped={legacy_export.get('swapped')})",
                        payload=legacy_export,
                    )
        except Exception as exc:
            logger.warning("Legacy export failed (non-fatal): %s", exc)
            _emit(forecast_db, run_id, "warning", "legacy_export_error",
                  f"Legacy export skipped: {exc}")

        # ---- Step 10: Parity validation (if enabled) --------------------
        parity_summary: dict[str, Any] = {"parity_checked": False}
        try:
            from app.config import settings
            if bool(getattr(settings, "legacy_parity_validation_enabled", False)) and final_status in ("success", "partial"):
                logger.info("Engine run_id=%d: running parity validation (step 10)", run_id)
                from app.services.forecasting.parity_validator import ParityValidator
                validator = ParityValidator()
                parity_summary = validator.validate_run(
                    forecast_db, run_id, inference_date=run.inference_date  # type: ignore[arg-type]
                )
                level = "info" if parity_summary.get("parity_status") == "pass" else "warning"
                _emit(
                    forecast_db, run_id, level, "parity_validation",
                    f"Parity: {parity_summary.get('parity_status')} "
                    f"(rebuilt={parity_summary.get('rebuilt_row_count')}, "
                    f"legacy={parity_summary.get('legacy_row_count')}, "
                    f"mismatches={parity_summary.get('mismatch_count')})",
                    payload=parity_summary,
                )
                if (
                    parity_summary.get("parity_status") == "fail"
                    and bool(getattr(settings, "legacy_parity_fail_on_mismatch", False))
                ):
                    final_status = "partial"
                    _set_status(forecast_db, run, final_status,
                                error_message="Parity validation failed")
        except Exception as exc:
            logger.warning("Parity validation failed (non-fatal): %s", exc)
            _emit(forecast_db, run_id, "warning", "parity_validation_error",
                  f"Parity validation skipped: {exc}")

        # ---- Step 11: File export (if enabled) --------------------------
        try:
            from app.config import settings
            if bool(getattr(settings, "legacy_file_export_enabled", False)) and final_status in ("success", "partial"):
                logger.info("Engine run_id=%d: exporting legacy files (step 11)", run_id)
                from app.services.forecasting.legacy_file_exporter import LegacyFileExporter
                file_exporter = LegacyFileExporter()
                file_result = file_exporter.export_run(
                    forecast_db, run,
                    parity_summary=parity_summary if parity_summary.get("parity_checked") else None,
                )
                file_errors = file_result.get("errors", [])
                if file_errors:
                    for fe in file_errors:
                        _emit(forecast_db, run_id, "warning", "file_export_error", fe)
                else:
                    _emit(
                        forecast_db, run_id, "info", "file_export_complete",
                        f"File export: {len(file_result.get('files_generated', []))} files written "
                        f"→ {file_result.get('output_path')}",
                        payload={k: v for k, v in file_result.items() if k != "files_generated"},
                    )
        except Exception as exc:
            logger.warning("File export failed (non-fatal): %s", exc)
            _emit(forecast_db, run_id, "warning", "file_export_error",
                  f"File export skipped: {exc}")

        logger.info(
            "Engine run_id=%d done: status=%s skus_forecast=%d rows=%d errors=%d strategies=%s",
            run_id, final_status, skus_forecast, rows_results, len(errors), strategy_counts,
        )
        return EngineRunSummary(
            run_id=run_id,
            status=final_status,
            rows_ingest=rows_ingest,
            skus_included=skus_included,
            skus_excluded=skus_excluded,
            outliers_flagged=outliers_flagged,
            skus_forecast=skus_forecast,
            rows_results=rows_results,
            errors=errors,
            strategy_counts=strategy_counts,
        )

    # ------------------------------------------------------------------
    # Per-SKU forecasting dispatch
    # ------------------------------------------------------------------

    def _forecast_sku(
        self,
        forecast_db: Session,
        run_id: int,
        product_code: str,
        warehouse_code: str,
        group_df: pd.DataFrame,
        train_end: date,
        product_name: str | None,
        strategy: ForecastStrategy = ForecastStrategy.MATURE_HISTORY,
        allowed_models: set[str] | None = None,
    ) -> tuple[int, dict[str, float]]:
        """
        Run model variants, score, select best, persist to MySQL.
        Returns (rows_written, {model_code: mape}).
        """
        group_df = group_df.sort_values("week_start").reset_index(drop=True)

        raw_series = group_df[["week_start", "qty"]].rename(
            columns={"week_start": "ds", "qty": "y"}
        )
        adj_y = (
            group_df["stock_adjusted_qty"]
            .fillna(group_df["adjusted_qty"])
            .fillna(group_df["qty"])
        )
        adj_series = pd.DataFrame({"ds": group_df["week_start"], "y": adj_y})

        score_set: ModelScoreSet = self.scoring_svc.score(
            product_code, warehouse_code, raw_series, adj_series,
            allowed_models=allowed_models,
        )

        actual_by_week: dict[date, float] = {
            row["week_start"]: float(row["qty"])
            for _, row in group_df.iterrows()
        }
        interpolated_by_week: dict[date, float] = {
            row["week_start"]: float(
                row["stock_adjusted_qty"]
                if pd.notna(row.get("stock_adjusted_qty"))
                else (row["adjusted_qty"] if pd.notna(row.get("adjusted_qty")) else row["qty"])
            )
            for _, row in group_df.iterrows()
        }
        classification_by_week: dict[date, str] = {
            row["week_start"]: str(row.get("week_classification") or "normal")
            for _, row in group_df.iterrows()
        }
        outlier_by_week: dict[date, bool] = {
            row["week_start"]: bool(row.get("is_outlier_flagged", False))
            for _, row in group_df.iterrows()
        }

        rows_written = 0
        mape_by_code: dict[str, float] = {}
        for ms in score_set.scores:
            is_best = ms.model_code == score_set.best_model_code
            mape_val = ms.mape if not math.isnan(ms.mape) else float("nan")
            mape_by_code[ms.model_code] = mape_val
            rows_written += _persist_forecast_rows(
                forecast_db, run_id, product_code, warehouse_code, ms, train_end,
                is_best=is_best, product_name=product_name,
                actual_by_week=actual_by_week,
                interpolated_by_week=interpolated_by_week,
                outlier_by_week=outlier_by_week,
                classification_by_week=classification_by_week,
                strategy=strategy.value,
            )
        forecast_db.flush()
        return rows_written, mape_by_code

    def _forecast_launch(
        self,
        forecast_db: Session,
        run_id: int,
        product_code: str,
        warehouse_code: str,
        train_end: date,
        profile: ForecastProductProfile | None,
        product_name: str | None,
    ) -> int:
        try:
            forecast_df, model_code = self.launch_handler_svc.forecast(
                forecast_db, product_code, warehouse_code, train_end, profile
            )
        except Exception as exc:
            logger.warning("LaunchHandler failed for %s/%s: %s", product_code, warehouse_code, exc)
            _emit(forecast_db, run_id, "warning", "launch_forecast_error",
                  f"Launch forecast failed: {exc}",
                  product_code=product_code, warehouse_code=warehouse_code)
            return 0

        if forecast_df.empty:
            return 0

        model_name = "Launch"
        rows_written = 0
        for fc_row in forecast_df.itertuples():
            raw_ds = getattr(fc_row, "ds", None)
            if isinstance(raw_ds, date) and not isinstance(raw_ds, type(pd.Timestamp(0))):
                fc_date: date = raw_ds
            elif hasattr(raw_ds, "date"):
                fc_date = raw_ds.date()  # type: ignore[union-attr]
            else:
                fc_date = date.fromisoformat(str(raw_ds))
            yhat = max(0.0, float(str(getattr(fc_row, "yhat", 0))))
            analogue = (
                str(profile.analogue_product_code)
                if profile and profile.analogue_product_code is not None
                else None
            )
            stmt = mysql_insert(ForecastResultWeekly).values(
                run_id=run_id,
                product_code=product_code,
                warehouse_code=warehouse_code,
                product_name=product_name,
                inference_date=train_end,
                forecast_week=fc_date,
                forecast_units=yhat,
                model_name=model_name,
                model_details=model_code,
                is_best_model=False,
                predicted_best_model_bool=False,
                result_meta={"strategy": "launch", "analogue": analogue},
            ).on_duplicate_key_update(
                forecast_units=yhat,
                model_name=model_name,
            )
            forecast_db.execute(stmt)
            rows_written += 1

        forecast_db.flush()
        return rows_written

    # ------------------------------------------------------------------
    # Data loading helpers
    # ------------------------------------------------------------------

    def _load_training_rows(self, forecast_db: Session, run_id: int) -> pd.DataFrame:
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
            return pd.DataFrame()
        return pd.DataFrame([
            {
                "product_code": str(r.product_code),
                "warehouse_code": str(r.warehouse_code),
                "week_start": r.week_start,
                "qty": float(str(r.qty)) if r.qty is not None else 0.0,
                "adjusted_qty": float(str(r.adjusted_qty)) if r.adjusted_qty is not None else None,
                "stock_adjusted_qty": float(str(r.stock_adjusted_qty)) if r.stock_adjusted_qty is not None else None,
                "soh_units": float(str(r.soh_units)) if r.soh_units is not None else None,
                "week_classification": str(r.week_classification) if r.week_classification is not None else "normal",
                "is_outlier_flagged": bool(r.is_outlier_flagged),
                "is_stock_constrained": bool(r.is_stock_constrained),
            }
            for r in rows
        ])


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _load_product_names(pg_db: Session) -> dict[str, str]:
    rows = pg_db.query(Product.sku, Product.name).all()
    return {str(r.sku): str(r.name) for r in rows if r.name}


def _load_product_profiles(forecast_db: Session) -> dict[str, ForecastProductProfile]:
    return {str(p.product_code): p for p in forecast_db.query(ForecastProductProfile).all()}


def _set_status(
    forecast_db: Session,
    run: ForecastRun,
    status: str,
    error_message: str | None = None,
) -> None:
    run.run_status = status  # type: ignore[assignment]
    if error_message is not None:
        run.error_message = error_message  # type: ignore[assignment]
    if status == "running" and run.started_at is None:
        run.started_at = datetime.utcnow()  # type: ignore[assignment]
    if status in ("success", "failed", "partial"):
        run.completed_at = datetime.utcnow()  # type: ignore[assignment]
    forecast_db.flush()


def _emit(
    forecast_db: Session,
    run_id: int,
    level: str,
    diag_type: str,
    message: str,
    product_code: str | None = None,
    warehouse_code: str | None = None,
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
    forecast_db.flush()


def _init_run_models(forecast_db: Session, run_id: int) -> None:
    """Create placeholder forecast_run_models rows at the start of a run."""
    now = datetime.utcnow()
    for model_code, model_family, series_variant in _MODEL_META:
        stmt = mysql_insert(ForecastRunModel).values(
            run_id=run_id,
            model_code=model_code,
            model_family=model_family,
            series_variant=series_variant,
            run_status="running",
            started_at=now,
        ).on_duplicate_key_update(run_status="running", started_at=now)
        forecast_db.execute(stmt)
    forecast_db.flush()


def _finalise_run_models(
    forecast_db: Session,
    run_id: int,
    skus_succeeded: int,
    skus_failed: int,
    model_mapes: dict[str, list[float]],
) -> None:
    """Update forecast_run_models with aggregate counts and mean mape/mae."""
    now = datetime.utcnow()
    for model_code, model_family, series_variant in _MODEL_META:
        mapes = model_mapes.get(model_code, [])
        avg_mape = sum(mapes) / len(mapes) if mapes else None
        stmt = mysql_insert(ForecastRunModel).values(
            run_id=run_id,
            model_code=model_code,
            model_family=model_family,
            series_variant=series_variant,
            run_status="complete",
            products_attempted=skus_succeeded + skus_failed,
            products_succeeded=skus_succeeded,
            products_failed=skus_failed,
            mape=avg_mape,
            completed_at=now,
        ).on_duplicate_key_update(
            run_status="complete",
            products_attempted=skus_succeeded + skus_failed,
            products_succeeded=skus_succeeded,
            products_failed=skus_failed,
            mape=avg_mape,
            completed_at=now,
        )
        forecast_db.execute(stmt)
    forecast_db.flush()


def _persist_forecast_rows(
    forecast_db: Session,
    run_id: int,
    product_code: str,
    warehouse_code: str,
    ms: Any,
    train_end: date,
    is_best: bool,
    product_name: str | None,
    actual_by_week: dict[date, float],
    interpolated_by_week: dict[date, float],
    outlier_by_week: dict[date, bool],
    classification_by_week: dict[date, str],
    strategy: str = "mature_history",
) -> int:
    if ms.forecast_df.empty:
        return 0

    mape_val = None if math.isnan(ms.mape) else round(ms.mape, 6)
    mae_val = None if math.isnan(ms.mae) else round(ms.mae, 6)
    model_name = "Prophet" if "prophet" in ms.model_code.lower() else "XGBoost"
    rows_written = 0

    for fc_row in ms.forecast_df.itertuples():
        raw_ds = getattr(fc_row, "ds", None)
        if isinstance(raw_ds, date) and not isinstance(raw_ds, type(pd.Timestamp(0))):
            fc_date: date = raw_ds
        elif hasattr(raw_ds, "date"):
            fc_date = raw_ds.date()  # type: ignore[union-attr]
        else:
            fc_date = date.fromisoformat(str(raw_ds))

        yhat = max(0.0, float(str(getattr(fc_row, "yhat", 0))))
        cls = classification_by_week.get(fc_date, "normal")
        is_outlier = outlier_by_week.get(fc_date, False)

        stmt = mysql_insert(ForecastResultWeekly).values(
            run_id=run_id,
            product_code=product_code,
            warehouse_code=warehouse_code,
            product_name=product_name,
            inference_date=train_end,
            forecast_week=fc_date,
            actual_units=actual_by_week.get(fc_date),
            interpolated_units=interpolated_by_week.get(fc_date),
            forecast_units=yhat,
            model_name=model_name,
            model_details=ms.model_code,
            mape=mape_val,
            mae=mae_val,
            is_best_model=is_best,
            predicted_best_model_bool=is_best,
            outlier_flag=is_outlier,
            stockout_flag=(cls == "zero_stockout"),
            constrained_flag=(cls in ("zero_stockout", "constrained_low_stock")),
            result_meta={"strategy": strategy, "model_fit": ms.fit_meta},
        ).on_duplicate_key_update(
            forecast_units=yhat,
            mape=mape_val,
            mae=mae_val,
            is_best_model=is_best,
            predicted_best_model_bool=is_best,
            result_meta={"strategy": strategy, "model_fit": ms.fit_meta},
        )
        forecast_db.execute(stmt)
        rows_written += 1
    return rows_written
