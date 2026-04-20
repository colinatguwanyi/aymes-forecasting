"""
Forecasting subsystem ORM models.

All tables use W-TUE week_start alignment (same as the rest of the platform).
MySQL holds raw sales (aymes_reports) and forecast subsystem tables (see MYSQL_FORECAST_DATABASE).

Table dependency order (for FK clarity):
  standalone → forecast_source_configs, forecast_model_configs,
                forecast_sku_history_rules, forecast_product_profiles
  l1 deps    → forecast_runtime_configs (FK source_configs)
               forecast_sales_weekly   (FK source_configs)
               forecast_stock_weekly   (standalone)
  l2 deps    → forecast_runs           (FK runtime_configs)
  l3 deps    → forecast_training_series_weekly, forecast_run_models,
               forecast_results_weekly, forecast_run_diagnostics (all FK runs)
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)

from app.database import Base


# ---------------------------------------------------------------------------
# forecast_source_configs
# ---------------------------------------------------------------------------

class ForecastSourceConfig(Base):
    """
    Describes a data source connection (MySQL or Postgres).
    Credentials are never stored; only the env-var *names* are recorded so the
    reader service knows which variables to read at runtime.
    """
    __tablename__ = "forecast_source_configs"
    __table_args__ = (
        Index("ix_fsc_code", "code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(64), unique=True, nullable=False)
    source_type = Column(String(32), nullable=False)          # "mysql" | "postgres"
    host_env_var = Column(String(128), nullable=False)        # e.g. "MYSQL_HOST"
    port_env_var = Column(String(128), nullable=False)        # e.g. "MYSQL_PORT"
    user_env_var = Column(String(128), nullable=False)        # e.g. "MYSQL_USER"
    password_env_var = Column(String(128), nullable=False)    # e.g. "MYSQL_PASSWORD"
    database_name = Column(String(128), nullable=False)       # e.g. "aymes_reports"
    table_name = Column(String(256), nullable=False)          # e.g. "adhl_data_daily"
    active = Column(Boolean, nullable=False, server_default="true")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# forecast_model_configs
# ---------------------------------------------------------------------------

class ForecastModelConfig(Base):
    """
    A named forecasting algorithm with its hyperparameters stored as JSON.
    Multiple model configs can be tried in a single runtime config (ensemble / selection).
    """
    __tablename__ = "forecast_model_configs"
    __table_args__ = (
        Index("ix_fmc_code", "code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(64), unique=True, nullable=False)       # e.g. "trailing_mean_8"
    display_name = Column(String(256), nullable=False)
    method_type = Column(String(64), nullable=False)             # "trailing_mean" | "seasonal_naive" | "ets"
    hyperparams = Column(JSON, nullable=False, server_default=text("'{}'"))
    active = Column(Boolean, nullable=False, server_default="true")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# forecast_runtime_configs
# ---------------------------------------------------------------------------

class ForecastRuntimeConfig(Base):
    """
    Ties a source config to one or more model configs plus run-level settings.
    model_config_ids is a JSON array of ForecastModelConfig.id values to try.
    """
    __tablename__ = "forecast_runtime_configs"
    __table_args__ = (
        Index("ix_frc_code", "code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(64), unique=True, nullable=False)
    source_config_id = Column(
        Integer,
        ForeignKey("forecast_source_configs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    model_config_ids = Column(JSON, nullable=False, server_default=text("'[]'"))
    warehouse_codes = Column(JSON, nullable=True)       # NULL = all warehouses
    sku_filter_sql = Column(Text, nullable=True)         # optional extra WHERE clause
    train_window_weeks = Column(Integer, nullable=False, server_default="104")
    horizon_weeks = Column(Integer, nullable=False, server_default="52")
    wtue_alignment = Column(Boolean, nullable=False, server_default="true")
    active = Column(Boolean, nullable=False, server_default="true")
    notes = Column(Text, nullable=True)
    stock_params = Column(JSON, nullable=True)                  # stock-aware preprocessing thresholds
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# forecast_sku_history_rules
# ---------------------------------------------------------------------------

class ForecastSkuHistoryRule(Base):
    """
    Per-SKU (optionally per-warehouse) overrides for history preparation.
    warehouse_code NULL means the rule applies across all warehouses for that SKU.
    The unique constraint handles the NULL case at the application layer.
    merged_into_sku: when set, historical data for this SKU is merged into the
    target SKU when building training series (legacy product-code rename support).
    """
    __tablename__ = "forecast_sku_history_rules"
    __table_args__ = (
        Index("ix_fshr_sku", "sku"),
        Index("ix_fshr_wh", "warehouse_code"),
        Index("ix_fshr_merged_into_sku", "merged_into_sku"),
    )

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(64), nullable=False)
    warehouse_code = Column(String(32), nullable=True)           # NULL = all warehouses
    min_history_weeks = Column(Integer, nullable=True)
    max_history_weeks = Column(Integer, nullable=True)
    outlier_threshold_sigma = Column(Numeric(6, 3), nullable=True)
    exclude_weeks = Column(JSON, nullable=True)                 # ["2024-01-02", ...]
    override_model_code = Column(String(64), nullable=True)
    merged_into_sku = Column(String(64), nullable=True)          # old_code → new_code merge
    active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# forecast_product_profiles
# ---------------------------------------------------------------------------

class ForecastProductProfile(Base):
    """
    Forecasting-specific product metadata (one row per SKU).
    Complements the main products table without polluting it.

    lifecycle_stage values: "npi" | "launch" | "growth" | "mature" | "decline"
    force_strategy values:  "mature_history" | "sparse_history" | "launch" | "exclude"
    """
    __tablename__ = "forecast_product_profiles"
    __table_args__ = (
        Index("ix_fpp_lifecycle_stage", "lifecycle_stage"),
    )

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(64), unique=True, nullable=False, index=True)
    category = Column(String(128), nullable=True)
    seasonality_class = Column(String(32), nullable=True)        # "high"|"medium"|"low"|"none"
    preferred_model_code = Column(String(64), nullable=True)
    demand_pattern = Column(String(32), nullable=True)           # "steady"|"sporadic"|"lumpy"
    lifecycle_stage = Column(String(32), nullable=True)          # "npi"|"growth"|"mature"|"decline"
    analogue_product_code = Column(String(64), nullable=True)    # reference SKU for launch scaling
    force_strategy = Column(String(64), nullable=True)           # override routing decision
    launch_date = Column(Date, nullable=True)                    # estimated product launch date
    discontinue_date = Column(Date, nullable=True)               # estimated discontinuation date
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# forecast_sales_weekly
# ---------------------------------------------------------------------------

class ForecastSalesWeekly(Base):
    """
    Weekly sales data ingested from the MySQL source (aymes_reports.adhl_data_daily).
    Rows are W-TUE bucketed and deduplicated by (source_config_id, sku, warehouse_code,
    week_start, demand_type).
    """
    __tablename__ = "forecast_sales_weekly"
    __table_args__ = (
        UniqueConstraint(
            "source_config_id", "sku", "warehouse_code", "week_start", "demand_type",
            name="uq_fsw_source_sku_wh_week_type",
        ),
        Index("ix_fsw_sku", "sku"),
        Index("ix_fsw_warehouse_code", "warehouse_code"),
        Index("ix_fsw_week_start", "week_start"),
        Index("ix_fsw_source_config_id", "source_config_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    source_config_id = Column(
        Integer,
        ForeignKey("forecast_source_configs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sku = Column(String(64), nullable=False)
    warehouse_code = Column(String(32), nullable=False)
    week_start = Column(Date, nullable=False)                    # W-TUE
    qty = Column(Numeric(18, 4), nullable=False)
    demand_type = Column(String(32), nullable=False, server_default="CUSTOMER")
    source_row_count = Column(Integer, nullable=True)            # daily rows aggregated
    ingested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# forecast_stock_weekly
# ---------------------------------------------------------------------------

class ForecastStockWeekly(Base):
    """
    Weekly SOH snapshot copied from inventory_snapshots_weekly for use as
    the stock-state input to the forecasting engine (read-only staging copy).
    """
    __tablename__ = "forecast_stock_weekly"
    __table_args__ = (
        UniqueConstraint(
            "sku", "warehouse_code", "week_start", "source",
            name="uq_fstw_sku_wh_week_source",
        ),
        Index("ix_fstw_sku", "sku"),
        Index("ix_fstw_warehouse_code", "warehouse_code"),
        Index("ix_fstw_week_start", "week_start"),
    )

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(64), nullable=False)
    warehouse_code = Column(String(32), nullable=False)
    week_start = Column(Date, nullable=False)                    # W-TUE
    on_hand_qty = Column(Numeric(18, 4), nullable=False, server_default="0")
    source = Column(
        String(32), nullable=False, server_default="inventory_snapshots_weekly"
    )
    ingested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# forecast_runs
# ---------------------------------------------------------------------------

class ForecastRun(Base):
    """
    A top-level forecast execution record.  One run covers all in-scope
    SKU × warehouse combinations and produces rows in forecast_results_weekly.
    """
    __tablename__ = "forecast_runs"
    __table_args__ = (
        Index("ix_fr_train_end_week_start", "train_end_week_start"),
    )

    id = Column(Integer, primary_key=True, index=True)
    runtime_config_id = Column(
        Integer,
        ForeignKey("forecast_runtime_configs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    run_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    train_end_week_start = Column(Date, nullable=False)          # last training week (W-TUE)
    horizon_weeks = Column(Integer, nullable=False, server_default="52")
    status = Column(String(32), nullable=False, server_default="pending")
    triggered_by = Column(String(256), nullable=True)
    rows_trained = Column(Integer, nullable=True)
    rows_forecast = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    run_meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# forecast_run_models
# ---------------------------------------------------------------------------

class ForecastRunModel(Base):
    """
    Records which model was evaluated (and optionally selected) per
    SKU × warehouse in a forecast run.  Stores in-sample fit metrics.
    """
    __tablename__ = "forecast_run_models"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "sku", "warehouse_code", "model_code",
            name="uq_frm_run_sku_wh_model",
        ),
        Index("ix_frm_run_id", "run_id"),
        Index("ix_frm_sku", "sku"),
        Index("ix_frm_warehouse_code", "warehouse_code"),
        Index("ix_frm_model_code", "model_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(
        Integer,
        ForeignKey("forecast_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku = Column(String(64), nullable=False)
    warehouse_code = Column(String(32), nullable=False)
    model_code = Column(String(64), nullable=False)
    selected = Column(Boolean, nullable=False, server_default="false")
    train_weeks = Column(Integer, nullable=True)
    wape = Column(Numeric(10, 6), nullable=True)
    bias = Column(Numeric(10, 6), nullable=True)
    mape = Column(Numeric(10, 6), nullable=True)
    mae = Column(Numeric(18, 4), nullable=True)
    fit_meta = Column(JSON, nullable=True)
    strategy = Column(String(64), nullable=True)                 # mature_history/sparse_history/launch/exclude
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# forecast_results_weekly
# ---------------------------------------------------------------------------

class ForecastResultWeekly(Base):
    """
    Final forecast output: one row per (run, SKU, warehouse, week, model).
    is_published marks rows that have been promoted for use by planning.
    """
    __tablename__ = "forecast_results_weekly"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "sku", "warehouse_code", "week_start", "model_code",
            name="uq_frw_run_sku_wh_week_model",
        ),
        Index("ix_frw_run_id", "run_id"),
        Index("ix_frw_sku", "sku"),
        Index("ix_frw_warehouse_code", "warehouse_code"),
        Index("ix_frw_week_start", "week_start"),
        Index("ix_frw_model_code", "model_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(
        Integer,
        ForeignKey("forecast_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku = Column(String(64), nullable=False)
    warehouse_code = Column(String(32), nullable=False)
    week_start = Column(Date, nullable=False)                    # W-TUE forecast week
    model_code = Column(String(64), nullable=False)
    forecast_qty = Column(Numeric(18, 4), nullable=False)
    lower_bound = Column(Numeric(18, 4), nullable=True)          # prediction interval
    upper_bound = Column(Numeric(18, 4), nullable=True)
    horizon_week_index = Column(Integer, nullable=False)         # 1 = first forecast week
    is_published = Column(Boolean, nullable=False, server_default="false")
    result_meta = Column(JSON, nullable=True)                   # actual_units, interpolated_units, outlier_flag, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# forecast_training_series_weekly
# ---------------------------------------------------------------------------

class ForecastTrainingSeriesWeekly(Base):
    """
    The cleaned, outlier-adjusted demand series that was used as training input
    for a specific forecast run.  Preserved for auditability and re-runs.
    """
    __tablename__ = "forecast_training_series_weekly"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "sku", "warehouse_code", "week_start",
            name="uq_ftsw_run_sku_wh_week",
        ),
        Index("ix_ftsw_run_id", "run_id"),
        Index("ix_ftsw_sku", "sku"),
        Index("ix_ftsw_warehouse_code", "warehouse_code"),
        Index("ix_ftsw_week_start", "week_start"),
    )

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(
        Integer,
        ForeignKey("forecast_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku = Column(String(64), nullable=False)
    warehouse_code = Column(String(32), nullable=False)
    week_start = Column(Date, nullable=False)                    # W-TUE
    qty = Column(Numeric(18, 4), nullable=False)
    adjusted_qty = Column(Numeric(18, 4), nullable=True)         # outlier-replaced value
    stock_adjusted_qty = Column(Numeric(18, 4), nullable=True)   # stock-aware imputed demand
    soh_units = Column(Numeric(18, 4), nullable=True)            # SOH at this week
    week_classification = Column(String(32), nullable=True)      # normal / zero_stockout / etc.
    is_outlier_flagged = Column(Boolean, nullable=False, server_default="false")
    is_stock_constrained = Column(Boolean, nullable=False, server_default="false")
    is_excluded = Column(Boolean, nullable=False, server_default="false")
    exclusion_reason = Column(String(128), nullable=True)


# ---------------------------------------------------------------------------
# forecast_run_diagnostics
# ---------------------------------------------------------------------------

class ForecastRunDiagnostic(Base):
    """
    Free-form diagnostic messages for a run.  sku / warehouse_code NULL means
    the message applies at run level, not per-SKU.
    """
    __tablename__ = "forecast_run_diagnostics"
    __table_args__ = (
        Index("ix_frd_run_id", "run_id"),
        Index("ix_frd_sku", "sku"),
        Index("ix_frd_warehouse_code", "warehouse_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(
        Integer,
        ForeignKey("forecast_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku = Column(String(64), nullable=True)
    warehouse_code = Column(String(32), nullable=True)
    level = Column(String(16), nullable=False, server_default="info")  # info|warning|error
    category = Column(String(64), nullable=True)   # e.g. "insufficient_history"
    message = Column(Text, nullable=False)
    detail = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
