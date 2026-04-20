"""
Forecasting repository / service layer — MySQL-backed.

Four services exported:
  ForecastSourceConfigService  — CRUD for forecast_source_configs
  ForecastRuntimeConfigService — CRUD for forecast_runtime_configs
  ForecastRunService           — create, update status, query forecast_runs
  ForecastResultService        — query forecast_results_weekly
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.forecast_mysql_models import (
    ForecastResultWeekly,
    ForecastRun,
    ForecastRunDiagnostic,
    ForecastRunModel,
    ForecastRuntimeConfig,
    ForecastSourceConfig,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ForecastSourceConfigService
# ---------------------------------------------------------------------------

class ForecastSourceConfigService:
    """CRUD for forecast_source_configs (MySQL)."""

    def __init__(self, forecast_db: Session) -> None:
        self._db = forecast_db

    def get_all(self, active_only: bool = True) -> list[ForecastSourceConfig]:
        q = self._db.query(ForecastSourceConfig)
        if active_only:
            q = q.filter(ForecastSourceConfig.is_active == True)  # noqa: E712
        return q.order_by(ForecastSourceConfig.source_name).all()

    def get_by_name(self, source_name: str) -> ForecastSourceConfig | None:
        return (
            self._db.query(ForecastSourceConfig)
            .filter(ForecastSourceConfig.source_name == source_name)
            .first()
        )

    def get_by_id(self, config_id: int) -> ForecastSourceConfig | None:
        return self._db.get(ForecastSourceConfig, config_id)

    def create(
        self,
        *,
        source_name: str,
        mysql_database: str,
        mysql_host: str | None = None,
        mysql_port: int | None = None,
        mysql_schema_name: str = "aymes_reports",
        mysql_sales_table: str = "adhl_data_daily",
        soh_source_mode: str = "external_current_source",
        is_active: bool = True,
    ) -> ForecastSourceConfig:
        obj = ForecastSourceConfig(
            source_name=source_name,
            mysql_database=mysql_database,
            mysql_host=mysql_host,
            mysql_port=mysql_port,
            mysql_schema_name=mysql_schema_name,
            mysql_sales_table=mysql_sales_table,
            soh_source_mode=soh_source_mode,
            is_active=is_active,
        )
        self._db.add(obj)
        self._db.flush()
        logger.info("Created ForecastSourceConfig id=%d name=%s", obj.id, source_name)
        return obj

    def set_active(self, config_id: int, *, active: bool) -> ForecastSourceConfig | None:
        obj = self.get_by_id(config_id)
        if obj is None:
            return None
        obj.is_active = active  # type: ignore[assignment]
        self._db.flush()
        return obj

    def update(self, config_id: int, **kwargs: Any) -> ForecastSourceConfig | None:
        obj = self.get_by_id(config_id)
        if obj is None:
            return None
        allowed = {
            "mysql_host", "mysql_port", "mysql_database", "mysql_schema_name",
            "mysql_sales_table", "soh_source_mode", "is_active",
        }
        for k, v in kwargs.items():
            if k in allowed and v is not None:
                setattr(obj, k, v)
        self._db.flush()
        return obj


# ---------------------------------------------------------------------------
# ForecastRuntimeConfigService
# ---------------------------------------------------------------------------

class ForecastRuntimeConfigService:
    """CRUD for forecast_runtime_configs (MySQL)."""

    def __init__(self, forecast_db: Session) -> None:
        self._db = forecast_db

    def get_all(self, active_only: bool = True) -> list[ForecastRuntimeConfig]:
        q = self._db.query(ForecastRuntimeConfig)
        if active_only:
            q = q.filter(ForecastRuntimeConfig.is_active == True)  # noqa: E712
        return q.order_by(ForecastRuntimeConfig.config_name).all()

    def get_by_name(self, config_name: str) -> ForecastRuntimeConfig | None:
        return (
            self._db.query(ForecastRuntimeConfig)
            .filter(ForecastRuntimeConfig.config_name == config_name)
            .first()
        )

    def get_by_id(self, config_id: int) -> ForecastRuntimeConfig | None:
        return self._db.get(ForecastRuntimeConfig, config_id)

    def load_stock_params(self, config_id: int | None) -> dict[str, Any]:
        """Return stock classification parameters as a flat dict with defaults."""
        defaults: dict[str, Any] = {
            "zero_stock_units_threshold": 5.0,
            "low_stock_cover_weeks_threshold": 2.0,
            "constrained_weeks_handling": "flag_only",
            "min_sparse_history_weeks": 12,
            "min_history_weeks": 60,
            "forecast_horizon_weeks": 52,
            "enable_stock_classification": True,
            "enable_launch_routing": True,
        }
        if config_id is None:
            return defaults
        rc = self.get_by_id(config_id)
        if rc is None:
            return defaults
        return {
            "zero_stock_units_threshold": float(str(rc.zero_stock_units_threshold if rc.zero_stock_units_threshold is not None else 5.0)),
            "low_stock_cover_weeks_threshold": float(str(rc.low_stock_cover_weeks_threshold if rc.low_stock_cover_weeks_threshold is not None else 2.0)),
            "constrained_weeks_handling": str(rc.constrained_weeks_handling if rc.constrained_weeks_handling is not None else "flag_only"),
            "min_sparse_history_weeks": int(str(rc.min_sparse_history_weeks if rc.min_sparse_history_weeks is not None else 12)),
            "min_history_weeks": int(str(rc.min_history_weeks if rc.min_history_weeks is not None else 60)),
            "forecast_horizon_weeks": int(str(rc.forecast_horizon_weeks if rc.forecast_horizon_weeks is not None else 52)),
            "enable_stock_classification": bool(rc.enable_stock_classification),
            "enable_launch_routing": bool(rc.enable_launch_routing),
        }

    def create(
        self,
        *,
        config_name: str,
        is_active: bool = False,
        forecast_horizon_weeks: int = 52,
        min_history_weeks: int = 60,
        outlier_threshold: float = 0.5,
        zero_stock_units_threshold: float = 5.0,
        low_stock_cover_weeks_threshold: float = 2.0,
        constrained_weeks_handling: str = "flag_only",
        min_sparse_history_weeks: int = 12,
        enable_stock_classification: bool = True,
        enable_launch_routing: bool = True,
        best_model_tie_break_order: list | None = None,
    ) -> ForecastRuntimeConfig:
        default_tie_break = [
            "Prophet_without_outliers",
            "XGBoost_without_outliers",
            "Prophet_with_outliers",
            "XGBoost_with_outliers",
        ]
        obj = ForecastRuntimeConfig(
            config_name=config_name,
            is_active=is_active,
            forecast_horizon_weeks=forecast_horizon_weeks,
            min_history_weeks=min_history_weeks,
            outlier_threshold=Decimal(str(outlier_threshold)),
            zero_stock_units_threshold=Decimal(str(zero_stock_units_threshold)),
            low_stock_cover_weeks_threshold=Decimal(str(low_stock_cover_weeks_threshold)),
            constrained_weeks_handling=constrained_weeks_handling,
            min_sparse_history_weeks=min_sparse_history_weeks,
            enable_stock_classification=enable_stock_classification,
            enable_launch_routing=enable_launch_routing,
            best_model_tie_break_order=best_model_tie_break_order or default_tie_break,
        )
        self._db.add(obj)
        self._db.flush()
        logger.info("Created ForecastRuntimeConfig id=%d name=%s", obj.id, config_name)
        return obj

    def update(self, config_id: int, **kwargs: Any) -> ForecastRuntimeConfig | None:
        obj = self.get_by_id(config_id)
        if obj is None:
            return None
        numeric_decimal = {"outlier_threshold", "zero_stock_units_threshold", "low_stock_cover_weeks_threshold"}
        allowed = {
            "is_active", "forecast_horizon_weeks", "min_history_weeks",
            "outlier_threshold", "zero_stock_units_threshold", "low_stock_cover_weeks_threshold",
            "constrained_weeks_handling", "min_sparse_history_weeks",
            "enable_stock_classification", "enable_launch_routing",
        }
        for k, v in kwargs.items():
            if k in allowed and v is not None:
                setattr(obj, k, Decimal(str(v)) if k in numeric_decimal else v)
        self._db.flush()
        return obj


# ---------------------------------------------------------------------------
# ForecastRunService
# ---------------------------------------------------------------------------

class ForecastRunService:
    """Create, update, and query forecast_runs (MySQL)."""

    def __init__(self, forecast_db: Session) -> None:
        self._db = forecast_db

    def create(
        self,
        *,
        inference_date: date,
        horizon_weeks: int = 52,
        source_config_id: int | None = None,
        runtime_config_id: int | None = None,
        run_type: str = "manual",
        created_by: str | None = None,
    ) -> ForecastRun:
        run = ForecastRun(
            run_uuid=str(uuid.uuid4()),
            run_status="queued",
            run_type=run_type,
            inference_date=inference_date,
            horizon_weeks=horizon_weeks,
            source_config_id=source_config_id,
            runtime_config_id=runtime_config_id,
            created_by=created_by,
        )
        self._db.add(run)
        self._db.flush()
        logger.info(
            "Created ForecastRun id=%d uuid=%s inference_date=%s",
            run.id, run.run_uuid, inference_date,
        )
        return run

    def set_status(
        self,
        run_id: int,
        status: str,
        *,
        error_message: str | None = None,
    ) -> ForecastRun | None:
        run = self._db.get(ForecastRun, run_id)
        if run is None:
            logger.warning("ForecastRun id=%d not found", run_id)
            return None
        run.run_status = status  # type: ignore[assignment]
        if error_message is not None:
            run.error_message = error_message  # type: ignore[assignment]
        if status == "running" and run.started_at is None:
            run.started_at = datetime.utcnow()  # type: ignore[assignment]
        if status in ("success", "failed", "partial"):
            run.completed_at = datetime.utcnow()  # type: ignore[assignment]
        self._db.flush()
        return run

    def get_by_id(self, run_id: int) -> ForecastRun | None:
        return self._db.get(ForecastRun, run_id)

    def get_by_uuid(self, run_uuid: str) -> ForecastRun | None:
        return (
            self._db.query(ForecastRun)
            .filter(ForecastRun.run_uuid == run_uuid)
            .first()
        )

    def list_runs(
        self,
        *,
        limit: int = 50,
        status: str | None = None,
        inference_date: date | None = None,
    ) -> list[ForecastRun]:
        q = self._db.query(ForecastRun).order_by(desc(ForecastRun.created_at))
        if status is not None:
            q = q.filter(ForecastRun.run_status == status)
        if inference_date is not None:
            q = q.filter(ForecastRun.inference_date == inference_date)
        return q.limit(limit).all()

    def add_diagnostic(
        self,
        *,
        run_id: int,
        message: str,
        diagnostic_level: str = "info",
        diagnostic_type: str = "general",
        product_code: str | None = None,
        warehouse_code: str | None = None,
        payload_json: dict[str, Any] | None = None,
    ) -> ForecastRunDiagnostic:
        diag = ForecastRunDiagnostic(
            run_id=run_id,
            product_code=product_code,
            warehouse_code=warehouse_code,
            diagnostic_level=diagnostic_level,
            diagnostic_type=diagnostic_type,
            message=message,
            payload_json=payload_json,
        )
        self._db.add(diag)
        self._db.flush()
        return diag

    def list_diagnostics(
        self,
        run_id: int,
        *,
        level: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ForecastRunDiagnostic]:
        q = (
            self._db.query(ForecastRunDiagnostic)
            .filter(ForecastRunDiagnostic.run_id == run_id)
            .order_by(ForecastRunDiagnostic.id)
        )
        if level is not None:
            q = q.filter(ForecastRunDiagnostic.diagnostic_level == level)
        return q.offset(offset).limit(limit).all()

    def list_run_models(self, run_id: int) -> list[ForecastRunModel]:
        return (
            self._db.query(ForecastRunModel)
            .filter(ForecastRunModel.run_id == run_id)
            .order_by(ForecastRunModel.model_code)
            .all()
        )


# ---------------------------------------------------------------------------
# ForecastResultService
# ---------------------------------------------------------------------------

class ForecastResultService:
    """Query helpers for forecast_results_weekly (MySQL)."""

    def __init__(self, forecast_db: Session) -> None:
        self._db = forecast_db

    def get_results(
        self,
        run_id: int,
        *,
        product_code: str | None = None,
        warehouse_code: str | None = None,
        model_details: str | None = None,
        best_only: bool = False,
        limit: int = 5000,
    ) -> list[ForecastResultWeekly]:
        q = (
            self._db.query(ForecastResultWeekly)
            .filter(ForecastResultWeekly.run_id == run_id)
            .order_by(
                ForecastResultWeekly.product_code,
                ForecastResultWeekly.warehouse_code,
                ForecastResultWeekly.forecast_week,
            )
        )
        if product_code is not None:
            q = q.filter(ForecastResultWeekly.product_code == product_code)
        if warehouse_code is not None:
            q = q.filter(ForecastResultWeekly.warehouse_code == warehouse_code)
        if model_details is not None:
            q = q.filter(ForecastResultWeekly.model_details == model_details)
        if best_only:
            q = q.filter(ForecastResultWeekly.is_best_model == True)  # noqa: E712
        return q.limit(limit).all()

    def get_best_results(
        self,
        *,
        product_code: str | None = None,
        warehouse_code: str | None = None,
        from_week: date | None = None,
        to_week: date | None = None,
        limit: int = 5000,
    ) -> list[ForecastResultWeekly]:
        """Return best-model results across all runs (is_best_model=True)."""
        q = (
            self._db.query(ForecastResultWeekly)
            .filter(ForecastResultWeekly.is_best_model == True)  # noqa: E712
            .order_by(
                ForecastResultWeekly.forecast_week,
                ForecastResultWeekly.product_code,
                ForecastResultWeekly.warehouse_code,
            )
        )
        if product_code is not None:
            q = q.filter(ForecastResultWeekly.product_code == product_code)
        if warehouse_code is not None:
            q = q.filter(ForecastResultWeekly.warehouse_code == warehouse_code)
        if from_week is not None:
            q = q.filter(ForecastResultWeekly.forecast_week >= from_week)
        if to_week is not None:
            q = q.filter(ForecastResultWeekly.forecast_week <= to_week)
        return q.limit(limit).all()
