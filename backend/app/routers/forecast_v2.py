"""
Forecasting v2 API — MySQL-backed configuration, run management, and results.

All write operations require admin_or_planner; reads require any_auth.
Prefix registered in main.py: /api/v1/forecast

Session dependencies:
  db          → Postgres (platform data — products, SOH; not used directly here
                but available for extensions that need it)
  forecast_db → MySQL aymes_forecasting (all forecast tables)
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.forecast_mysql_models import ForecastResultWeekly, ForecastRun
from app.security.auth import require_admin_or_planner, require_any_auth
from app.services.forecasting.forecast_services import (
    ForecastResultService,
    ForecastRuntimeConfigService,
    ForecastRunService,
    ForecastSourceConfigService,
)
from app.services.forecasting.mysql_forecast_db import get_forecast_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class SourceConfigCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    source_name: str
    mysql_database: str
    mysql_host: str | None = None
    mysql_port: int | None = None
    mysql_schema_name: str = "aymes_reports"
    mysql_sales_table: str = "adhl_data_daily"
    soh_source_mode: str = "external_current_source"
    is_active: bool = True


class SourceConfigOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int
    source_name: str
    mysql_database: str
    mysql_host: str | None = None
    mysql_port: int | None = None
    mysql_schema_name: str
    mysql_sales_table: str
    soh_source_mode: str
    is_active: bool


class RuntimeConfigOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int
    config_name: str
    is_active: bool
    forecast_horizon_weeks: int
    min_history_weeks: int
    constrained_weeks_handling: str
    enable_stock_classification: bool
    enable_launch_routing: bool


class ForecastRunCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    inference_date: date
    horizon_weeks: int = 52
    source_config_id: int | None = None
    runtime_config_id: int | None = None
    run_type: str = "manual"
    created_by: str | None = None


class SourceConfigUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    mysql_host: str | None = None
    mysql_port: int | None = None
    mysql_database: str | None = None
    mysql_schema_name: str | None = None
    mysql_sales_table: str | None = None
    soh_source_mode: str | None = None
    is_active: bool | None = None


class RuntimeConfigCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    config_name: str
    is_active: bool = False
    forecast_horizon_weeks: int = 52
    min_history_weeks: int = 60
    outlier_threshold: float = 0.5
    zero_stock_units_threshold: float = 5.0
    low_stock_cover_weeks_threshold: float = 2.0
    constrained_weeks_handling: str = "flag_only"
    min_sparse_history_weeks: int = 12
    enable_stock_classification: bool = True
    enable_launch_routing: bool = True
    best_model_tie_break_order: list[str] | None = None


class RuntimeConfigUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    is_active: bool | None = None
    forecast_horizon_weeks: int | None = None
    min_history_weeks: int | None = None
    outlier_threshold: float | None = None
    zero_stock_units_threshold: float | None = None
    low_stock_cover_weeks_threshold: float | None = None
    constrained_weeks_handling: str | None = None
    min_sparse_history_weeks: int | None = None
    enable_stock_classification: bool | None = None
    enable_launch_routing: bool | None = None


class RuntimeConfigDetailOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int
    config_name: str
    is_active: bool
    forecast_horizon_weeks: int
    min_history_weeks: int
    outlier_threshold: float | None = None
    zero_stock_units_threshold: float | None = None
    low_stock_cover_weeks_threshold: float | None = None
    constrained_weeks_handling: str
    min_sparse_history_weeks: int
    enable_stock_classification: bool
    enable_launch_routing: bool
    best_model_tie_break_order: list | None = None


class DiagnosticOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int
    run_id: int
    product_code: str | None = None
    warehouse_code: str | None = None
    diagnostic_type: str
    diagnostic_level: str
    message: str
    payload_json: Any = None
    created_at: str | None = None


class RunModelOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int
    run_id: int
    model_code: str
    model_family: str
    strategy: str | None = None
    series_variant: str
    run_status: str
    products_attempted: int
    products_succeeded: int
    products_failed: int
    mape: float | None = None
    mae: float | None = None
    error_message: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class ForecastRunOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int
    run_uuid: str
    run_status: str
    run_type: str
    inference_date: date
    horizon_weeks: int
    source_config_id: int | None = None
    runtime_config_id: int | None = None
    error_message: str | None = None
    created_by: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None


class ForecastResultOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int
    run_id: int
    product_code: str
    warehouse_code: str | None
    product_name: str | None
    inference_date: date
    forecast_week: date
    actual_units: float | None
    forecast_units: float | None
    model_name: str
    model_details: str
    mape: float | None
    mae: float | None
    is_best_model: bool | None
    outlier_flag: bool | None
    stockout_flag: bool | None
    constrained_flag: bool | None


# ---------------------------------------------------------------------------
# Source config endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/source-configs",
    dependencies=[Depends(require_any_auth)],
    response_model=list[SourceConfigOut],
)
def list_source_configs(
    active_only: bool = Query(True),
    forecast_db: Session = Depends(get_forecast_db),
) -> list[dict[str, Any]]:
    """List forecast source configurations."""
    svc = ForecastSourceConfigService(forecast_db)
    rows = svc.get_all(active_only=active_only)
    return [
        {
            "id": r.id,
            "source_name": r.source_name,
            "mysql_database": r.mysql_database,
            "mysql_host": r.mysql_host,
            "mysql_port": r.mysql_port,
            "mysql_schema_name": r.mysql_schema_name,
            "mysql_sales_table": r.mysql_sales_table,
            "soh_source_mode": r.soh_source_mode,
            "is_active": r.is_active,
        }
        for r in rows
    ]


@router.post(
    "/source-configs",
    dependencies=[Depends(require_admin_or_planner)],
    response_model=SourceConfigOut,
    status_code=status.HTTP_201_CREATED,
)
def create_source_config(
    body: SourceConfigCreate,
    forecast_db: Session = Depends(get_forecast_db),
) -> dict[str, Any]:
    """Create a new forecast source config. source_name must be unique."""
    svc = ForecastSourceConfigService(forecast_db)
    if svc.get_by_name(body.source_name) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Source config '{body.source_name}' already exists.",
        )
    obj = svc.create(
        source_name=body.source_name,
        mysql_database=body.mysql_database,
        mysql_host=body.mysql_host,
        mysql_port=body.mysql_port,
        mysql_schema_name=body.mysql_schema_name,
        mysql_sales_table=body.mysql_sales_table,
        soh_source_mode=body.soh_source_mode,
        is_active=body.is_active,
    )
    forecast_db.commit()
    return {
        "id": obj.id,
        "source_name": obj.source_name,
        "mysql_database": obj.mysql_database,
        "mysql_host": obj.mysql_host,
        "mysql_port": obj.mysql_port,
        "mysql_schema_name": obj.mysql_schema_name,
        "mysql_sales_table": obj.mysql_sales_table,
        "soh_source_mode": obj.soh_source_mode,
        "is_active": obj.is_active,
    }


def _source_config_to_dict(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "source_name": r.source_name,
        "mysql_database": r.mysql_database,
        "mysql_host": r.mysql_host,
        "mysql_port": r.mysql_port,
        "mysql_schema_name": r.mysql_schema_name,
        "mysql_sales_table": r.mysql_sales_table,
        "soh_source_mode": r.soh_source_mode,
        "is_active": r.is_active,
    }


@router.get(
    "/source-configs/{config_id}",
    dependencies=[Depends(require_any_auth)],
    response_model=SourceConfigOut,
)
def get_source_config(
    config_id: int,
    forecast_db: Session = Depends(get_forecast_db),
) -> dict[str, Any]:
    """Get a single source config by id."""
    svc = ForecastSourceConfigService(forecast_db)
    obj = svc.get_by_id(config_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"SourceConfig id={config_id} not found")
    return _source_config_to_dict(obj)


@router.patch(
    "/source-configs/{config_id}",
    dependencies=[Depends(require_admin_or_planner)],
    response_model=SourceConfigOut,
)
def update_source_config(
    config_id: int,
    body: SourceConfigUpdate,
    forecast_db: Session = Depends(get_forecast_db),
) -> dict[str, Any]:
    """Update mutable fields of a source config."""
    svc = ForecastSourceConfigService(forecast_db)
    obj = svc.update(config_id, **body.model_dump(exclude_none=True))
    if obj is None:
        raise HTTPException(status_code=404, detail=f"SourceConfig id={config_id} not found")
    forecast_db.commit()
    return _source_config_to_dict(obj)


# ---------------------------------------------------------------------------
# Runtime config endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/runtime-configs",
    dependencies=[Depends(require_any_auth)],
    response_model=list[RuntimeConfigOut],
)
def list_runtime_configs(
    active_only: bool = Query(True),
    forecast_db: Session = Depends(get_forecast_db),
) -> list[dict[str, Any]]:
    """List forecast runtime configurations."""
    svc = ForecastRuntimeConfigService(forecast_db)
    rows = svc.get_all(active_only=active_only)
    return [
        {
            "id": r.id,
            "config_name": r.config_name,
            "is_active": r.is_active,
            "forecast_horizon_weeks": r.forecast_horizon_weeks,
            "min_history_weeks": r.min_history_weeks,
            "constrained_weeks_handling": r.constrained_weeks_handling,
            "enable_stock_classification": r.enable_stock_classification,
            "enable_launch_routing": r.enable_launch_routing,
        }
        for r in rows
    ]


def _runtime_config_to_detail(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "config_name": r.config_name,
        "is_active": r.is_active,
        "forecast_horizon_weeks": r.forecast_horizon_weeks,
        "min_history_weeks": r.min_history_weeks,
        "outlier_threshold": float(Decimal(str(r.outlier_threshold))) if r.outlier_threshold is not None else None,
        "zero_stock_units_threshold": float(Decimal(str(r.zero_stock_units_threshold))) if r.zero_stock_units_threshold is not None else None,
        "low_stock_cover_weeks_threshold": float(Decimal(str(r.low_stock_cover_weeks_threshold))) if r.low_stock_cover_weeks_threshold is not None else None,
        "constrained_weeks_handling": r.constrained_weeks_handling,
        "min_sparse_history_weeks": r.min_sparse_history_weeks,
        "enable_stock_classification": r.enable_stock_classification,
        "enable_launch_routing": r.enable_launch_routing,
        "best_model_tie_break_order": r.best_model_tie_break_order,
    }


@router.post(
    "/runtime-configs",
    dependencies=[Depends(require_admin_or_planner)],
    response_model=RuntimeConfigDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def create_runtime_config(
    body: RuntimeConfigCreate,
    forecast_db: Session = Depends(get_forecast_db),
) -> dict[str, Any]:
    """Create a new runtime config. config_name must be unique."""
    svc = ForecastRuntimeConfigService(forecast_db)
    if svc.get_by_name(body.config_name) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Runtime config '{body.config_name}' already exists.",
        )
    obj = svc.create(
        config_name=body.config_name,
        is_active=body.is_active,
        forecast_horizon_weeks=body.forecast_horizon_weeks,
        min_history_weeks=body.min_history_weeks,
        outlier_threshold=body.outlier_threshold,
        zero_stock_units_threshold=body.zero_stock_units_threshold,
        low_stock_cover_weeks_threshold=body.low_stock_cover_weeks_threshold,
        constrained_weeks_handling=body.constrained_weeks_handling,
        min_sparse_history_weeks=body.min_sparse_history_weeks,
        enable_stock_classification=body.enable_stock_classification,
        enable_launch_routing=body.enable_launch_routing,
        best_model_tie_break_order=body.best_model_tie_break_order,
    )
    forecast_db.commit()
    return _runtime_config_to_detail(obj)


@router.get(
    "/runtime-configs/{config_id}",
    dependencies=[Depends(require_any_auth)],
    response_model=RuntimeConfigDetailOut,
)
def get_runtime_config(
    config_id: int,
    forecast_db: Session = Depends(get_forecast_db),
) -> dict[str, Any]:
    """Get a single runtime config with all fields including stock parameters."""
    svc = ForecastRuntimeConfigService(forecast_db)
    obj = svc.get_by_id(config_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"RuntimeConfig id={config_id} not found")
    return _runtime_config_to_detail(obj)


@router.patch(
    "/runtime-configs/{config_id}",
    dependencies=[Depends(require_admin_or_planner)],
    response_model=RuntimeConfigDetailOut,
)
def update_runtime_config(
    config_id: int,
    body: RuntimeConfigUpdate,
    forecast_db: Session = Depends(get_forecast_db),
) -> dict[str, Any]:
    """Update mutable fields of a runtime config."""
    svc = ForecastRuntimeConfigService(forecast_db)
    obj = svc.update(config_id, **body.model_dump(exclude_none=True))
    if obj is None:
        raise HTTPException(status_code=404, detail=f"RuntimeConfig id={config_id} not found")
    forecast_db.commit()
    return _runtime_config_to_detail(obj)


# ---------------------------------------------------------------------------
# Forecast run endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/runs",
    dependencies=[Depends(require_admin_or_planner)],
    response_model=ForecastRunOut,
    status_code=status.HTTP_201_CREATED,
)
def create_forecast_run(
    body: ForecastRunCreate,
    forecast_db: Session = Depends(get_forecast_db),
) -> dict[str, Any]:
    """Create a new forecast run record (status=queued)."""
    svc = ForecastRunService(forecast_db)
    run = svc.create(
        inference_date=body.inference_date,
        horizon_weeks=body.horizon_weeks,
        source_config_id=body.source_config_id,
        runtime_config_id=body.runtime_config_id,
        run_type=body.run_type,
        created_by=body.created_by,
    )
    forecast_db.commit()
    return _run_to_dict(run)


class ForecastExecuteBody(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    source_config_name: str
    from_date: date
    to_date: date


@router.post(
    "/runs/{run_id}/execute",
    dependencies=[Depends(require_admin_or_planner)],
)
def execute_forecast_run(
    run_id: int,
    body: ForecastExecuteBody,
    db: Session = Depends(get_db),
    forecast_db: Session = Depends(get_forecast_db),
) -> dict[str, Any]:
    """
    Synchronously execute the Vertex-parity pipeline for an existing run.

    db          → Postgres (platform products, SOH fallback)
    forecast_db → MySQL aymes_forecasting (all forecast I/O)
    """
    from app.services.forecasting.forecasting_engine import ForecastingEngine

    run_svc = ForecastRunService(forecast_db)
    run = run_svc.get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"ForecastRun id={run_id} not found")

    source_config = ForecastSourceConfigService(forecast_db).get_by_name(body.source_config_name)
    if source_config is None:
        raise HTTPException(
            status_code=404,
            detail=f"ForecastSourceConfig '{body.source_config_name}' not found",
        )

    engine = ForecastingEngine()
    summary = engine.run(db, forecast_db, run, source_config, body.from_date, body.to_date)
    forecast_db.commit()

    return {
        "run_id": summary.run_id,
        "status": summary.status,
        "rows_ingest": summary.rows_ingest,
        "skus_included": summary.skus_included,
        "skus_excluded": summary.skus_excluded,
        "outliers_flagged": summary.outliers_flagged,
        "skus_forecast": summary.skus_forecast,
        "rows_results": summary.rows_results,
        "errors": summary.errors,
        "strategy_counts": summary.strategy_counts,
    }


@router.get(
    "/runs",
    dependencies=[Depends(require_any_auth)],
    response_model=list[ForecastRunOut],
)
def list_forecast_runs(
    status_filter: str | None = Query(None, alias="status"),
    inference_date: date | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    forecast_db: Session = Depends(get_forecast_db),
) -> list[dict[str, Any]]:
    """List forecast runs, newest first."""
    svc = ForecastRunService(forecast_db)
    runs = svc.list_runs(limit=limit, status=status_filter, inference_date=inference_date)
    return [_run_to_dict(r) for r in runs]


@router.get(
    "/runs/{run_id}",
    dependencies=[Depends(require_any_auth)],
    response_model=ForecastRunOut,
)
def get_forecast_run(
    run_id: int,
    forecast_db: Session = Depends(get_forecast_db),
) -> dict[str, Any]:
    """Get a single forecast run by id."""
    svc = ForecastRunService(forecast_db)
    run = svc.get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"ForecastRun id={run_id} not found")
    return _run_to_dict(run)


@router.patch(
    "/runs/{run_id}/status",
    dependencies=[Depends(require_admin_or_planner)],
    response_model=ForecastRunOut,
)
def update_forecast_run_status(
    run_id: int,
    new_status: str = Query(...),
    error_message: str | None = Query(None),
    forecast_db: Session = Depends(get_forecast_db),
) -> dict[str, Any]:
    """Update the status of a forecast run."""
    svc = ForecastRunService(forecast_db)
    run = svc.set_status(run_id, new_status, error_message=error_message)
    if run is None:
        raise HTTPException(status_code=404, detail=f"ForecastRun id={run_id} not found")
    forecast_db.commit()
    return _run_to_dict(run)


@router.get(
    "/runs/{run_id}/diagnostics",
    dependencies=[Depends(require_any_auth)],
    response_model=list[DiagnosticOut],
)
def get_run_diagnostics(
    run_id: int,
    level: str | None = Query(None, description="Filter by level: info, warning, error"),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    forecast_db: Session = Depends(get_forecast_db),
) -> list[dict[str, Any]]:
    """Return diagnostic records for a forecast run."""
    svc = ForecastRunService(forecast_db)
    if svc.get_by_id(run_id) is None:
        raise HTTPException(status_code=404, detail=f"ForecastRun id={run_id} not found")
    rows = svc.list_diagnostics(run_id, level=level, limit=limit, offset=offset)
    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "product_code": r.product_code,
            "warehouse_code": r.warehouse_code,
            "diagnostic_type": str(r.diagnostic_type),
            "diagnostic_level": str(r.diagnostic_level),
            "message": str(r.message),
            "payload_json": r.payload_json,
            "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) is not None else None,
        }
        for r in rows
    ]


@router.get(
    "/runs/{run_id}/run-models",
    dependencies=[Depends(require_any_auth)],
    response_model=list[RunModelOut],
)
def get_run_models(
    run_id: int,
    forecast_db: Session = Depends(get_forecast_db),
) -> list[dict[str, Any]]:
    """Return per-model summary rows for a forecast run."""
    svc = ForecastRunService(forecast_db)
    if svc.get_by_id(run_id) is None:
        raise HTTPException(status_code=404, detail=f"ForecastRun id={run_id} not found")
    rows = svc.list_run_models(run_id)
    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "model_code": str(r.model_code),
            "model_family": str(r.model_family),
            "strategy": r.strategy,
            "series_variant": str(r.series_variant),
            "run_status": str(r.run_status),
            "products_attempted": int(str(r.products_attempted)) if r.products_attempted is not None else 0,
            "products_succeeded": int(str(r.products_succeeded)) if r.products_succeeded is not None else 0,
            "products_failed": int(str(r.products_failed)) if r.products_failed is not None else 0,
            "mape": float(Decimal(str(r.mape))) if r.mape is not None else None,
            "mae": float(Decimal(str(r.mae))) if r.mae is not None else None,
            "error_message": r.error_message,
            "started_at": r.started_at.isoformat() if getattr(r, "started_at", None) is not None else None,
            "completed_at": r.completed_at.isoformat() if getattr(r, "completed_at", None) is not None else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Forecast results endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/runs/{run_id}/results",
    dependencies=[Depends(require_any_auth)],
    response_model=list[ForecastResultOut],
)
def get_run_results(
    run_id: int,
    product_code: str | None = Query(None),
    warehouse_code: str | None = Query(None),
    model_details: str | None = Query(None),
    best_only: bool = Query(False),
    limit: int = Query(1000, ge=1, le=10_000),
    forecast_db: Session = Depends(get_forecast_db),
) -> list[dict[str, Any]]:
    """Return forecast output rows for a specific run."""
    svc = ForecastResultService(forecast_db)
    rows = svc.get_results(
        run_id,
        product_code=product_code,
        warehouse_code=warehouse_code,
        model_details=model_details,
        best_only=best_only,
        limit=limit,
    )
    return [_result_to_dict(r) for r in rows]


@router.post(
    "/runs/{run_id}/export-legacy",
    dependencies=[Depends(require_admin_or_planner)],
)
def export_run_legacy(
    run_id: int,
    safe_replace: bool = Query(
        False,
        description=(
            "If true, promote staging → live table after validation. "
            "Overrides LEGACY_OUTPUT_SAFE_REPLACE config for this call."
        ),
    ),
    forecast_db: Session = Depends(get_forecast_db),
) -> dict[str, Any]:
    """
    Export a completed run's results into the legacy Vertex output table shape.

    Writes to aymes_reports.aymes_demand_planning_forecast_by_model_new (staging).
    Pass ?safe_replace=true to also promote into the live consumption table.

    This endpoint is safe to call multiple times — rows are appended with a
    run_id so they can be identified and de-duplicated if needed.
    """
    from app.services.forecasting.legacy_output_exporter import LegacyOutputExporter

    run_svc = ForecastRunService(forecast_db)
    run = run_svc.get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"ForecastRun id={run_id} not found")

    exporter = LegacyOutputExporter()
    result = exporter.export_run(forecast_db, run_id, safe_replace=safe_replace)

    if result.get("errors") and not result.get("rows_written"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Legacy export failed", "errors": result["errors"]},
        )
    return result


@router.get(
    "/best-results",
    dependencies=[Depends(require_any_auth)],
    response_model=list[ForecastResultOut],
)
def get_best_results(
    product_code: str | None = Query(None),
    warehouse_code: str | None = Query(None),
    from_week: date | None = Query(None),
    to_week: date | None = Query(None),
    limit: int = Query(1000, ge=1, le=10_000),
    forecast_db: Session = Depends(get_forecast_db),
) -> list[dict[str, Any]]:
    """Return best-model forecast rows (is_best_model=True) for use by planning."""
    svc = ForecastResultService(forecast_db)
    rows = svc.get_best_results(
        product_code=product_code,
        warehouse_code=warehouse_code,
        from_week=from_week,
        to_week=to_week,
        limit=limit,
    )
    return [_result_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Supply-adjusted forecast endpoints
# ---------------------------------------------------------------------------

class SupplyAdjustedOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int
    run_id: int
    product_code: str
    warehouse_code: str | None = None
    forecast_week: date
    base_forecast: float
    stock_on_hand: float | None = None
    inbound_orders: float | None = None
    available_stock: float | None = None
    adjusted_forecast: float | None = None
    stockout_flag: bool
    excess_stock_flag: bool
    stock_source: str


@router.post(
    "/runs/{run_id}/compute-supply-adjusted",
    dependencies=[Depends(require_admin_or_planner)],
)
def compute_supply_adjusted(
    run_id: int,
    use_mock_data: bool = Query(
        False,
        description=(
            "Generate synthetic SOH + inbound values instead of reading "
            "forecast_stock_weekly. Useful for testing before real stock data is available."
        ),
    ),
    forecast_db: Session = Depends(get_forecast_db),
) -> dict[str, Any]:
    """
    Post-process a completed forecast run to produce supply-adjusted output.

    Reads best-model rows from forecast_results_weekly, joins with stock data
    from forecast_stock_weekly (or synthetic mock values), and writes rows to
    forecast_supply_adjusted.

    This endpoint is idempotent — it replaces any existing supply-adjusted rows
    for the run before inserting fresh ones.  The base forecast in
    forecast_results_weekly is never modified.
    """
    from app.services.forecasting.supply_adjustment_service import SupplyAdjustmentService

    run_svc = ForecastRunService(forecast_db)
    if run_svc.get_by_id(run_id) is None:
        raise HTTPException(status_code=404, detail=f"ForecastRun id={run_id} not found")

    svc = SupplyAdjustmentService()
    summary = svc.compute(run_id, forecast_db, use_mock_data=use_mock_data)
    forecast_db.commit()
    return summary.as_dict()


@router.get(
    "/runs/{run_id}/supply-adjusted",
    dependencies=[Depends(require_any_auth)],
    response_model=list[SupplyAdjustedOut],
)
def get_supply_adjusted(
    run_id: int,
    product_code: str | None = Query(None),
    warehouse_code: str | None = Query(None),
    stockout_only: bool = Query(False),
    excess_only: bool = Query(False),
    limit: int = Query(2000, ge=1, le=20_000),
    forecast_db: Session = Depends(get_forecast_db),
) -> list[dict[str, Any]]:
    """
    Return supply-adjusted forecast rows for a run.

    Filters: product_code, warehouse_code, stockout_only, excess_only.
    Run compute-supply-adjusted first to populate data.
    """
    from app.services.forecasting.supply_adjustment_service import get_supply_adjusted_rows

    run_svc = ForecastRunService(forecast_db)
    if run_svc.get_by_id(run_id) is None:
        raise HTTPException(status_code=404, detail=f"ForecastRun id={run_id} not found")

    rows = get_supply_adjusted_rows(
        run_id,
        forecast_db,
        product_code=product_code,
        warehouse_code=warehouse_code,
        stockout_only=stockout_only,
        excess_only=excess_only,
        limit=limit,
    )

    def _f(v: Any) -> float | None:
        if v is None:
            return None
        try:
            return float(Decimal(str(v)))
        except Exception:
            return None

    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "product_code": str(r.product_code),
            "warehouse_code": str(r.warehouse_code) if r.warehouse_code is not None else None,
            "forecast_week": r.forecast_week,
            "base_forecast": _f(r.base_forecast) or 0.0,
            "stock_on_hand": _f(r.stock_on_hand),
            "inbound_orders": _f(r.inbound_orders),
            "available_stock": _f(r.available_stock),
            "adjusted_forecast": _f(r.adjusted_forecast),
            "stockout_flag": bool(r.stockout_flag),
            "excess_stock_flag": bool(r.excess_stock_flag),
            "stock_source": str(r.stock_source),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# View query endpoints (MySQL-backed equivalents of the old Postgres views)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Legacy output diagnostics — read-only, no forecast_db dependency required
# ---------------------------------------------------------------------------

@router.get(
    "/legacy-output/health",
    dependencies=[Depends(require_any_auth)],
)
def legacy_output_health() -> dict[str, Any]:
    """
    Connectivity and schema health check for the legacy forecast output tables
    in aymes_reports.

    Returns:
      - can_connect
      - target_db
      - staging_table_exists
      - live_table_exists
      - required_columns_present
      - sample_row_count  (total rows in live table)
      - errors
    """
    from app.services.forecasting.legacy_output_repository import LegacyOutputRepository
    repo = LegacyOutputRepository()
    return repo.health_check()


@router.get(
    "/legacy-output/inference-date/{inference_date}",
    dependencies=[Depends(require_any_auth)],
)
def legacy_output_inference_date_summary(
    inference_date: date,
    sample_rows: int = Query(20, ge=1, le=200, description="Number of sample rows to return"),
) -> dict[str, Any]:
    """
    Summary of the legacy live table content for a given inference_date.

    Returns:
      - inference_date
      - live_row_count
      - model_breakdown       (row count per Model_Details variant)
      - distinct_sku_count
      - duplicate_key_count
      - duplicate_key_examples
      - min_forecast_week
      - max_forecast_week
      - null_summary          (null_count/total/null_rate per key column)
      - sample_rows           (first N rows ordered by AAH_Product_Code)
      - errors
    """
    from app.services.forecasting.legacy_output_repository import LegacyOutputRepository

    repo   = LegacyOutputRepository()
    errors: list[str] = []

    live_row_count  = repo.count_live_rows_for_inference_date(inference_date)
    model_breakdown = repo.get_live_model_breakdown(inference_date)
    distinct_skus   = repo.get_live_distinct_sku_count(inference_date)

    dup_info = repo.detect_live_duplicates(inference_date)
    errors.extend(dup_info.get("errors") or [])

    week_range = repo.get_live_min_max_forecast_week(inference_date)
    errors.extend(week_range.get("errors") or [])

    null_info = repo.get_live_null_summary(inference_date)
    errors.extend(null_info.get("errors") or [])

    sample = repo.sample_live_rows(inference_date, limit=sample_rows)

    return {
        "inference_date":          str(inference_date),
        "live_row_count":          live_row_count,
        "model_breakdown":         model_breakdown,
        "distinct_sku_count":      distinct_skus,
        "duplicate_key_count":     dup_info.get("duplicate_key_count", 0),
        "duplicate_key_examples":  dup_info.get("first_duplicates", []),
        "min_forecast_week":       week_range.get("min"),
        "max_forecast_week":       week_range.get("max"),
        "null_summary":            null_info.get("columns", {}),
        "sample_rows":             sample,
        "errors":                  errors,
    }


@router.get(
    "/views/sales-source-weekly",
    dependencies=[Depends(require_any_auth)],
)
def view_sales_source_weekly(
    product_code: str | None = Query(None),
    warehouse_code: str | None = Query(None),
    from_week: date | None = Query(None),
    to_week: date | None = Query(None),
    limit: int = Query(1000, ge=1, le=10_000),
    forecast_db: Session = Depends(get_forecast_db),
) -> list[dict[str, Any]]:
    """Weekly sales from forecast_sales_weekly (MySQL)."""
    from app.services.forecasting.views import query_forecast_sales_source_weekly
    return query_forecast_sales_source_weekly(
        forecast_db,
        product_code=product_code,
        warehouse_code=warehouse_code,
        from_week=from_week,
        to_week=to_week,
        limit=limit,
    )


@router.get(
    "/views/training-base",
    dependencies=[Depends(require_any_auth)],
)
def view_training_base(
    run_id: int | None = Query(None),
    product_code: str | None = Query(None),
    warehouse_code: str | None = Query(None),
    from_week: date | None = Query(None),
    to_week: date | None = Query(None),
    limit: int = Query(1000, ge=1, le=50_000),
    forecast_db: Session = Depends(get_forecast_db),
) -> list[dict[str, Any]]:
    """Non-excluded training series rows (MySQL)."""
    from app.services.forecasting.views import query_forecast_training_base
    return query_forecast_training_base(
        forecast_db,
        run_id=run_id,
        product_code=product_code,
        warehouse_code=warehouse_code,
        from_week=from_week,
        to_week=to_week,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# File export endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/runs/{run_id}/export-files",
    dependencies=[Depends(require_admin_or_planner)],
)
def export_run_files(
    run_id: int,
    forecast_db: Session = Depends(get_forecast_db),
) -> dict[str, Any]:
    """
    Generate legacy-compatible CSV files and run_manifest.json for a completed run.

    Writes to {FORECAST_OUTPUT_ROOT}/{run_uuid}/ on the server filesystem.
    Returns output_path, files_generated, row_counts, and any errors.
    """
    from app.services.forecasting.legacy_file_exporter import LegacyFileExporter

    run_svc = ForecastRunService(forecast_db)
    run = run_svc.get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"ForecastRun id={run_id} not found")

    exporter = LegacyFileExporter()
    result = exporter.export_run(forecast_db, run)
    return result


# ---------------------------------------------------------------------------
# Parity validation endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/runs/{run_id}/validate-parity",
    dependencies=[Depends(require_admin_or_planner)],
)
def validate_run_parity(
    run_id: int,
    sample_size: int = Query(
        50,
        ge=1,
        le=500,
        description="Number of SKUs to sample for value-level comparison.",
    ),
    forecast_db: Session = Depends(get_forecast_db),
) -> dict[str, Any]:
    """
    Compare rebuilt forecast_results_weekly against the legacy Vertex output table
    (aymes_reports.aymes_demand_planning_forecast_by_model).

    Returns:
      - valid                         : bool (True if parity_status == "pass")
      - compared_against_inference_date
      - counts_summary                : row counts, SKU counts, model breakdown
      - mismatch_summary              : mismatch_count, mismatch_types, parity_status
      - sample_mismatches             : list of per-row discrepancies for sample SKUs
    """
    from app.services.forecasting.parity_validator import ParityValidator

    run_svc = ForecastRunService(forecast_db)
    run = run_svc.get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"ForecastRun id={run_id} not found")

    validator = ParityValidator()
    parity = validator.validate_run(
        forecast_db,
        run_id,
        inference_date=run.inference_date,  # type: ignore[arg-type]
        sample_size=sample_size,
    )

    return {
        "valid":                            parity.get("parity_status") == "pass",
        "compared_against_inference_date":  parity.get("compared_against_inference_date"),
        "counts_summary":                   parity.get("counts_summary", {}),
        "mismatch_summary": {
            "parity_status":    parity.get("parity_status"),
            "mismatch_count":   parity.get("mismatch_count"),
            "mismatch_types":   parity.get("mismatch_types"),
            "legacy_row_count": parity.get("legacy_row_count"),
            "rebuilt_row_count":parity.get("rebuilt_row_count"),
            "null_rates":       parity.get("null_rates"),
            "duplicate_keys":   parity.get("duplicate_keys"),
        },
        "sample_mismatches":                parity.get("sample_mismatches", []),
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _run_to_dict(run: ForecastRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "run_uuid": str(run.run_uuid),
        "run_status": str(run.run_status),
        "run_type": str(run.run_type),
        "inference_date": run.inference_date,
        "horizon_weeks": run.horizon_weeks,
        "source_config_id": run.source_config_id,
        "runtime_config_id": run.runtime_config_id,
        "error_message": run.error_message,
        "created_by": run.created_by,
        "started_at": run.started_at.isoformat() if run.started_at is not None else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at is not None else None,
        "created_at": run.created_at.isoformat() if getattr(run, "created_at", None) is not None else None,
    }


def _result_to_dict(r: ForecastResultWeekly) -> dict[str, Any]:
    return {
        "id": r.id,
        "run_id": r.run_id,
        "product_code": str(r.product_code),
        "warehouse_code": str(r.warehouse_code) if r.warehouse_code is not None else None,
        "product_name": str(r.product_name) if r.product_name is not None else None,
        "inference_date": r.inference_date,
        "forecast_week": r.forecast_week,
        "actual_units": float(Decimal(str(r.actual_units))) if r.actual_units is not None else None,
        "forecast_units": float(Decimal(str(r.forecast_units))) if r.forecast_units is not None else 0.0,
        "model_name": str(r.model_name),
        "model_details": str(r.model_details),
        "mape": float(Decimal(str(r.mape))) if r.mape is not None else None,
        "mae": float(Decimal(str(r.mae))) if r.mae is not None else None,
        "is_best_model": bool(r.is_best_model) if r.is_best_model is not None else None,
        "outlier_flag": bool(r.outlier_flag) if r.outlier_flag is not None else None,
        "stockout_flag": bool(r.stockout_flag) if r.stockout_flag is not None else None,
        "constrained_flag": bool(r.constrained_flag) if r.constrained_flag is not None else None,
    }
