"""
MySQL-first SQLAlchemy ORM models for the forecasting subsystem.

These models target MySQL 8 and are completely separate from the Postgres
platform models (app/models.py) and the original Postgres forecast models
(app/forecast_models.py, kept for reference).

Key differences from the Postgres schema:
  - JSON instead of JSONB
  - BigInteger auto_increment PKs
  - DateTime (not timezone-aware) — MySQL stores UTC, application handles tz
  - Boolean → TINYINT(1) (SQLAlchemy handles this transparently)
  - Column names aligned with the agreed MySQL DDL (product_code, inference_date,
    run_status, etc.)
  - forecast_run_models is run-level aggregate, not per-SKU
  - forecast_results_weekly carries all legacy output fields as flat columns
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import declarative_base

MySQLForecastBase = declarative_base()


# ---------------------------------------------------------------------------
# 1. forecast_source_configs
# ---------------------------------------------------------------------------

class ForecastSourceConfig(MySQLForecastBase):
    """Connection descriptor for a MySQL sales source."""
    __tablename__ = "forecast_source_configs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_name = Column(String(100), nullable=False, unique=True)
    is_active = Column(Boolean, nullable=False, server_default=text("1"))

    mysql_host = Column(String(255), nullable=True)
    mysql_port = Column(Integer, nullable=True)
    mysql_database = Column(String(100), nullable=False)
    mysql_schema_name = Column(String(100), nullable=False, server_default=text("'aymes_reports'"))
    mysql_sales_table = Column(String(100), nullable=False, server_default=text("'adhl_data_daily'"))

    soh_source_mode = Column(String(50), nullable=False, server_default=text("'external_current_source'"))
    soh_connection_name = Column(String(255), nullable=True)
    soh_table_name = Column(String(255), nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------------------
# 2. forecast_runtime_configs
# ---------------------------------------------------------------------------

class ForecastRuntimeConfig(MySQLForecastBase):
    """Tunable parameters for a forecast run."""
    __tablename__ = "forecast_runtime_configs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    config_name = Column(String(100), nullable=False, unique=True)
    is_active = Column(Boolean, nullable=False, server_default=text("0"))

    forecast_horizon_weeks = Column(Integer, nullable=False, server_default=text("52"))
    min_history_weeks = Column(Integer, nullable=False, server_default=text("60"))
    outlier_threshold = Column(Numeric(8, 4), nullable=False, server_default=text("0.5000"))

    zero_stock_units_threshold = Column(Numeric(18, 4), nullable=False, server_default=text("5.0000"))
    low_stock_cover_weeks_threshold = Column(Numeric(18, 4), nullable=False, server_default=text("2.0000"))
    constrained_weeks_handling = Column(String(50), nullable=False, server_default=text("'flag_only'"))

    min_sparse_history_weeks = Column(Integer, nullable=False, server_default=text("12"))
    enable_stock_classification = Column(Boolean, nullable=False, server_default=text("1"))
    enable_launch_routing = Column(Boolean, nullable=False, server_default=text("1"))

    best_model_tie_break_order = Column(JSON, nullable=False)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------------------
# 3. forecast_sku_history_rules
# ---------------------------------------------------------------------------

class ForecastSkuHistoryRule(MySQLForecastBase):
    """Product-code rename / merge rules for building training history."""
    __tablename__ = "forecast_sku_history_rules"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    old_product_code = Column(String(50), nullable=False)
    new_product_code = Column(String(50), nullable=False)
    merged_into_sku = Column(String(50), nullable=True)

    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    multiply_by_item_size = Column(Boolean, nullable=False, server_default=text("0"))
    drop_old_rows_from_effective_from = Column(Boolean, nullable=False, server_default=text("0"))
    is_active = Column(Boolean, nullable=False, server_default=text("1"))
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())


# ---------------------------------------------------------------------------
# 4. forecast_product_profiles
# ---------------------------------------------------------------------------

class ForecastProductProfile(MySQLForecastBase):
    """Per-product forecasting configuration: lifecycle, routing, analogues."""
    __tablename__ = "forecast_product_profiles"
    __table_args__ = (
        UniqueConstraint("product_code", "warehouse_code", name="uq_forecast_product_profile"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_code = Column(String(50), nullable=False)
    warehouse_code = Column(String(50), nullable=True)

    lifecycle_stage = Column(String(50), nullable=False, server_default=text("'mature'"))
    analogue_product_code = Column(String(50), nullable=True)
    force_strategy = Column(String(50), nullable=True)

    launch_date = Column(Date, nullable=True)
    discontinue_date = Column(Date, nullable=True)

    include_in_forecast = Column(Boolean, nullable=False, server_default=text("1"))
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------------------
# 5. forecast_sales_weekly
# ---------------------------------------------------------------------------

class ForecastSalesWeekly(MySQLForecastBase):
    """Weekly sales snapshot ingested from the MySQL source."""
    __tablename__ = "forecast_sales_weekly"
    __table_args__ = (
        UniqueConstraint(
            "product_code", "warehouse_code", "week_start", "source_system",
            name="uq_forecast_sales_weekly",
        ),
        Index("idx_forecast_sales_weekly_product_week", "product_code", "week_start"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, nullable=True)
    product_code = Column(String(50), nullable=False)
    warehouse_code = Column(String(50), nullable=True)
    week_start = Column(Date, nullable=False)

    units_sold = Column(Numeric(18, 4), nullable=False, server_default=text("0.0000"))
    product_name = Column(String(255), nullable=True)
    pip_code = Column(String(50), nullable=True)
    item_size = Column(Numeric(18, 4), nullable=True)

    source_system = Column(String(100), nullable=False, server_default=text("'mysql_vertex_source'"))
    created_at = Column(DateTime, nullable=False, server_default=func.now())


# ---------------------------------------------------------------------------
# 6. forecast_stock_weekly
# ---------------------------------------------------------------------------

class ForecastStockWeekly(MySQLForecastBase):
    """Weekly SOH snapshot synced from Postgres inventory_snapshots_weekly."""
    __tablename__ = "forecast_stock_weekly"
    __table_args__ = (
        UniqueConstraint(
            "product_code", "warehouse_code", "week_start",
            name="uq_forecast_stock_weekly",
        ),
        Index(
            "idx_forecast_stock_weekly_product_week",
            "product_code", "warehouse_code", "week_start",
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, nullable=True)
    product_code = Column(String(50), nullable=False)
    warehouse_code = Column(String(50), nullable=False)
    week_start = Column(Date, nullable=False)

    soh_units = Column(Numeric(18, 4), nullable=False, server_default=text("0.0000"))
    in_transit_units = Column(Numeric(18, 4), nullable=True)
    open_po_units = Column(Numeric(18, 4), nullable=True)

    stock_status = Column(String(50), nullable=True)
    is_stockout = Column(Boolean, nullable=False, server_default=text("0"))
    is_constrained = Column(Boolean, nullable=False, server_default=text("0"))

    created_at = Column(DateTime, nullable=False, server_default=func.now())


# ---------------------------------------------------------------------------
# 7. forecast_runs
# ---------------------------------------------------------------------------

class ForecastRun(MySQLForecastBase):
    """One record per forecast execution."""
    __tablename__ = "forecast_runs"
    __table_args__ = (
        Index("idx_forecast_runs_status", "run_status"),
        Index("idx_forecast_runs_inference", "inference_date"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_uuid = Column(String(36), nullable=False, unique=True)
    run_status = Column(String(50), nullable=False, server_default=text("'queued'"))
    run_type = Column(String(50), nullable=False, server_default=text("'manual'"))

    inference_date = Column(Date, nullable=False)
    horizon_weeks = Column(Integer, nullable=False, server_default=text("52"))

    source_config_id = Column(BigInteger, nullable=True)
    runtime_config_id = Column(BigInteger, nullable=True)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


# ---------------------------------------------------------------------------
# 8. forecast_run_models
# ---------------------------------------------------------------------------

class ForecastRunModel(MySQLForecastBase):
    """Aggregate per-model-code results for a run (not per-SKU)."""
    __tablename__ = "forecast_run_models"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "model_code", "series_variant",
            name="uq_forecast_run_models",
        ),
        Index("idx_forecast_run_models_run", "run_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, nullable=False)
    model_code = Column(String(100), nullable=False)
    model_family = Column(String(50), nullable=False)
    strategy = Column(String(50), nullable=True)
    series_variant = Column(String(50), nullable=False)
    run_status = Column(String(50), nullable=False, server_default=text("'queued'"))

    products_attempted = Column(Integer, nullable=False, server_default=text("0"))
    products_succeeded = Column(Integer, nullable=False, server_default=text("0"))
    products_failed = Column(Integer, nullable=False, server_default=text("0"))

    mape = Column(Numeric(18, 6), nullable=True)
    mae = Column(Numeric(18, 6), nullable=True)
    metrics_json = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# 9. forecast_training_series_weekly
# ---------------------------------------------------------------------------

class ForecastTrainingSeriesWeekly(MySQLForecastBase):
    """Weekly training series per run/product/warehouse."""
    __tablename__ = "forecast_training_series_weekly"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "product_code", "warehouse_code", "week_start", "series_variant",
            name="uq_forecast_training_series",
        ),
        Index(
            "idx_forecast_training_series_run_product",
            "run_id", "product_code", "week_start",
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, nullable=False)
    product_code = Column(String(50), nullable=False)
    warehouse_code = Column(String(50), nullable=True)
    week_start = Column(Date, nullable=False)

    qty = Column(Numeric(18, 4), nullable=True)
    adjusted_qty = Column(Numeric(18, 4), nullable=True)
    stock_adjusted_qty = Column(Numeric(18, 4), nullable=True)
    interpolated_units = Column(Numeric(18, 4), nullable=True)

    is_outlier_flagged = Column(Boolean, nullable=False, server_default=text("0"))
    is_stock_constrained = Column(Boolean, nullable=False, server_default=text("0"))
    is_excluded = Column(Boolean, nullable=False, server_default=text("0"))

    week_classification = Column(String(50), nullable=True)
    soh_units = Column(Numeric(18, 4), nullable=True)

    series_variant = Column(String(50), nullable=False, server_default=text("'raw'"))

    created_at = Column(DateTime, nullable=False, server_default=func.now())


# ---------------------------------------------------------------------------
# 10. forecast_results_weekly
# ---------------------------------------------------------------------------

class ForecastResultWeekly(MySQLForecastBase):
    """
    Per-product per-week forecast output — mirrors the legacy Vertex output shape.

    All legacy output fields are stored as flat columns (not packed into JSON).
    result_meta is available as supplemental context.
    """
    __tablename__ = "forecast_results_weekly"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "product_code", "warehouse_code", "forecast_week", "model_details",
            name="uq_forecast_results_weekly",
        ),
        Index("idx_forecast_results_product_week", "product_code", "forecast_week"),
        Index("idx_forecast_results_run", "run_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, nullable=False)

    product_code = Column(String(50), nullable=False)
    warehouse_code = Column(String(50), nullable=True)
    product_name = Column(String(255), nullable=True)

    inference_date = Column(Date, nullable=False)
    forecast_week = Column(Date, nullable=False)

    actual_units = Column(Numeric(18, 4), nullable=True)
    interpolated_units = Column(Numeric(18, 4), nullable=True)
    forecast_units = Column(Numeric(18, 4), nullable=True)

    model_name = Column(String(100), nullable=False)
    model_details = Column(String(100), nullable=False)

    mape = Column(Numeric(18, 6), nullable=True)
    mae = Column(Numeric(18, 6), nullable=True)

    is_best_model = Column(Boolean, nullable=True)
    predicted_best_model_bool = Column(Boolean, nullable=True)

    outlier_flag = Column(Boolean, nullable=True)
    stockout_flag = Column(Boolean, nullable=True)
    constrained_flag = Column(Boolean, nullable=True)

    result_meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


# ---------------------------------------------------------------------------
# 11. forecast_run_diagnostics
# ---------------------------------------------------------------------------

class ForecastRunDiagnostic(MySQLForecastBase):
    """Explanatory records emitted during a run for audit and debugging."""
    __tablename__ = "forecast_run_diagnostics"
    __table_args__ = (
        Index("idx_forecast_diag_run", "run_id"),
        Index("idx_forecast_diag_product", "product_code"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, nullable=False)
    product_code = Column(String(50), nullable=True)
    warehouse_code = Column(String(50), nullable=True)

    diagnostic_type = Column(String(100), nullable=False)
    diagnostic_level = Column(String(20), nullable=False, server_default=text("'info'"))
    message = Column(Text, nullable=False)
    payload_json = Column(JSON, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())


# ---------------------------------------------------------------------------
# 12. forecast_supply_adjusted
# ---------------------------------------------------------------------------

class ForecastSupplyAdjusted(MySQLForecastBase):
    """
    Supply-aware post-processing output — per-run, per-product, per-week.

    Built from forecast_results_weekly (best-model rows) joined with SOH and
    inbound supply data. The base forecast in forecast_results_weekly is never
    modified; this table is a separate, additive layer.
    """
    __tablename__ = "forecast_supply_adjusted"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "product_code", "warehouse_code", "forecast_week",
            name="uq_supply_adjusted",
        ),
        Index("idx_supply_adjusted_run", "run_id"),
        Index("idx_supply_adjusted_product", "product_code", "forecast_week"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, nullable=False)

    product_code = Column(String(50), nullable=False)
    warehouse_code = Column(String(50), nullable=True)
    forecast_week = Column(Date, nullable=False)

    base_forecast = Column(Numeric(18, 4), nullable=False, server_default=text("0.0000"))

    stock_on_hand = Column(Numeric(18, 4), nullable=True)
    inbound_orders = Column(Numeric(18, 4), nullable=True)
    available_stock = Column(Numeric(18, 4), nullable=True)

    adjusted_forecast = Column(Numeric(18, 4), nullable=True)
    stockout_flag = Column(Boolean, nullable=False, server_default=text("0"))
    excess_stock_flag = Column(Boolean, nullable=False, server_default=text("0"))

    stock_source = Column(String(50), nullable=False, server_default=text("'forecast_stock_weekly'"))
    created_at = Column(DateTime, nullable=False, server_default=func.now())
