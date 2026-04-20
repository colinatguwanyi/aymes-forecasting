"""Add forecasting subsystem tables and views.

Revision ID: 022
Revises: 021
Create Date: 2026-03-25

New tables (creation order respects FK dependencies):
  forecast_source_configs
  forecast_model_configs
  forecast_runtime_configs
  forecast_sku_history_rules
  forecast_product_profiles
  forecast_sales_weekly
  forecast_stock_weekly
  forecast_runs
  forecast_run_models
  forecast_results_weekly
  forecast_training_series_weekly
  forecast_run_diagnostics

New views (CREATE OR REPLACE — always idempotent):
  vw_forecast_sales_source_weekly
  vw_forecast_stock_source_weekly
  vw_forecast_training_base

Design notes:
  - All CREATE TABLE / CREATE INDEX statements use IF NOT EXISTS so the
    migration is safe to re-run against a database where Base.metadata.create_all()
    already created the tables (e.g. after the models were imported at app startup).
  - Credentials are never stored; only env-var names appear in source_configs.
  - W-TUE weekly alignment is enforced at the application layer, not in DDL.
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

from alembic import op

logger = logging.getLogger(__name__)

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # ------------------------------------------------------------------
    # forecast_source_configs
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS forecast_source_configs (
            id              SERIAL          NOT NULL,
            code            VARCHAR(64)     NOT NULL,
            source_type     VARCHAR(32)     NOT NULL,
            host_env_var    VARCHAR(128)    NOT NULL,
            port_env_var    VARCHAR(128)    NOT NULL,
            user_env_var    VARCHAR(128)    NOT NULL,
            password_env_var VARCHAR(128)   NOT NULL,
            database_name   VARCHAR(128)    NOT NULL,
            table_name      VARCHAR(256)    NOT NULL,
            active          BOOLEAN         NOT NULL DEFAULT true,
            notes           TEXT,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT uq_fsc_code UNIQUE (code)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_fsc_code ON forecast_source_configs (code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_forecast_source_configs_id ON forecast_source_configs (id)")

    # ------------------------------------------------------------------
    # forecast_model_configs
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS forecast_model_configs (
            id              SERIAL          NOT NULL,
            code            VARCHAR(64)     NOT NULL,
            display_name    VARCHAR(256)    NOT NULL,
            method_type     VARCHAR(64)     NOT NULL,
            hyperparams     JSONB           NOT NULL DEFAULT '{}'::jsonb,
            active          BOOLEAN         NOT NULL DEFAULT true,
            notes           TEXT,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT uq_fmc_code UNIQUE (code)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_fmc_code ON forecast_model_configs (code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_forecast_model_configs_id ON forecast_model_configs (id)")

    # ------------------------------------------------------------------
    # forecast_runtime_configs
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS forecast_runtime_configs (
            id                  SERIAL      NOT NULL,
            code                VARCHAR(64) NOT NULL,
            source_config_id    INTEGER     NOT NULL
                REFERENCES forecast_source_configs (id) ON DELETE RESTRICT,
            model_config_ids    JSONB       NOT NULL DEFAULT '[]'::jsonb,
            warehouse_codes     JSONB,
            sku_filter_sql      TEXT,
            train_window_weeks  INTEGER     NOT NULL DEFAULT 104,
            horizon_weeks       INTEGER     NOT NULL DEFAULT 52,
            wtue_alignment      BOOLEAN     NOT NULL DEFAULT true,
            active              BOOLEAN     NOT NULL DEFAULT true,
            notes               TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT uq_frc_code UNIQUE (code)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_frc_code ON forecast_runtime_configs (code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_frc_source_config_id ON forecast_runtime_configs (source_config_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_forecast_runtime_configs_id ON forecast_runtime_configs (id)")

    # ------------------------------------------------------------------
    # forecast_sku_history_rules
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS forecast_sku_history_rules (
            id                      SERIAL          NOT NULL,
            sku                     VARCHAR(64)     NOT NULL,
            warehouse_code          VARCHAR(32),
            min_history_weeks       INTEGER,
            max_history_weeks       INTEGER,
            outlier_threshold_sigma NUMERIC(6, 3),
            exclude_weeks           JSONB,
            override_model_code     VARCHAR(64),
            active                  BOOLEAN         NOT NULL DEFAULT true,
            created_at              TIMESTAMPTZ     NOT NULL DEFAULT now(),
            updated_at              TIMESTAMPTZ     NOT NULL DEFAULT now(),
            PRIMARY KEY (id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_fshr_sku ON forecast_sku_history_rules (sku)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_fshr_wh ON forecast_sku_history_rules (warehouse_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_forecast_sku_history_rules_id ON forecast_sku_history_rules (id)")

    # ------------------------------------------------------------------
    # forecast_product_profiles
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS forecast_product_profiles (
            id                  SERIAL          NOT NULL,
            sku                 VARCHAR(64)     NOT NULL,
            category            VARCHAR(128),
            seasonality_class   VARCHAR(32),
            preferred_model_code VARCHAR(64),
            demand_pattern      VARCHAR(32),
            lifecycle_stage     VARCHAR(32),
            notes               TEXT,
            created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT uq_fpp_sku UNIQUE (sku)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_forecast_product_profiles_id ON forecast_product_profiles (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_forecast_product_profiles_sku ON forecast_product_profiles (sku)")

    # ------------------------------------------------------------------
    # forecast_sales_weekly
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS forecast_sales_weekly (
            id                  SERIAL          NOT NULL,
            source_config_id    INTEGER         NOT NULL
                REFERENCES forecast_source_configs (id) ON DELETE RESTRICT,
            sku                 VARCHAR(64)     NOT NULL,
            warehouse_code      VARCHAR(32)     NOT NULL,
            week_start          DATE            NOT NULL,
            qty                 NUMERIC(18, 4)  NOT NULL,
            demand_type         VARCHAR(32)     NOT NULL DEFAULT 'CUSTOMER',
            source_row_count    INTEGER,
            ingested_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT uq_fsw_source_sku_wh_week_type
                UNIQUE (source_config_id, sku, warehouse_code, week_start, demand_type)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_fsw_sku ON forecast_sales_weekly (sku)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_fsw_warehouse_code ON forecast_sales_weekly (warehouse_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_fsw_week_start ON forecast_sales_weekly (week_start)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_fsw_source_config_id ON forecast_sales_weekly (source_config_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_forecast_sales_weekly_id ON forecast_sales_weekly (id)")

    # ------------------------------------------------------------------
    # forecast_stock_weekly
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS forecast_stock_weekly (
            id              SERIAL          NOT NULL,
            sku             VARCHAR(64)     NOT NULL,
            warehouse_code  VARCHAR(32)     NOT NULL,
            week_start      DATE            NOT NULL,
            on_hand_qty     NUMERIC(18, 4)  NOT NULL DEFAULT 0,
            source          VARCHAR(32)     NOT NULL DEFAULT 'inventory_snapshots_weekly',
            ingested_at     TIMESTAMPTZ     NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT uq_fstw_sku_wh_week_source
                UNIQUE (sku, warehouse_code, week_start, source)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_fstw_sku ON forecast_stock_weekly (sku)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_fstw_warehouse_code ON forecast_stock_weekly (warehouse_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_fstw_week_start ON forecast_stock_weekly (week_start)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_forecast_stock_weekly_id ON forecast_stock_weekly (id)")

    # ------------------------------------------------------------------
    # forecast_runs
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS forecast_runs (
            id                      SERIAL          NOT NULL,
            runtime_config_id       INTEGER
                REFERENCES forecast_runtime_configs (id) ON DELETE SET NULL,
            run_at                  TIMESTAMPTZ     NOT NULL DEFAULT now(),
            train_end_week_start    DATE            NOT NULL,
            horizon_weeks           INTEGER         NOT NULL DEFAULT 52,
            status                  VARCHAR(32)     NOT NULL DEFAULT 'pending',
            triggered_by            VARCHAR(256),
            rows_trained            INTEGER,
            rows_forecast           INTEGER,
            error_message           TEXT,
            run_meta                JSONB,
            created_at              TIMESTAMPTZ     NOT NULL DEFAULT now(),
            completed_at            TIMESTAMPTZ,
            PRIMARY KEY (id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_fr_train_end_week_start ON forecast_runs (train_end_week_start)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_fr_runtime_config_id ON forecast_runs (runtime_config_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_forecast_runs_id ON forecast_runs (id)")

    # ------------------------------------------------------------------
    # forecast_run_models
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS forecast_run_models (
            id              SERIAL          NOT NULL,
            run_id          INTEGER         NOT NULL
                REFERENCES forecast_runs (id) ON DELETE CASCADE,
            sku             VARCHAR(64)     NOT NULL,
            warehouse_code  VARCHAR(32)     NOT NULL,
            model_code      VARCHAR(64)     NOT NULL,
            selected        BOOLEAN         NOT NULL DEFAULT false,
            train_weeks     INTEGER,
            wape            NUMERIC(10, 6),
            bias            NUMERIC(10, 6),
            fit_meta        JSONB,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT uq_frm_run_sku_wh_model
                UNIQUE (run_id, sku, warehouse_code, model_code)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_frm_run_id ON forecast_run_models (run_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_frm_sku ON forecast_run_models (sku)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_frm_warehouse_code ON forecast_run_models (warehouse_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_frm_model_code ON forecast_run_models (model_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_forecast_run_models_id ON forecast_run_models (id)")

    # ------------------------------------------------------------------
    # forecast_results_weekly
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS forecast_results_weekly (
            id                  SERIAL          NOT NULL,
            run_id              INTEGER         NOT NULL
                REFERENCES forecast_runs (id) ON DELETE CASCADE,
            sku                 VARCHAR(64)     NOT NULL,
            warehouse_code      VARCHAR(32)     NOT NULL,
            week_start          DATE            NOT NULL,
            model_code          VARCHAR(64)     NOT NULL,
            forecast_qty        NUMERIC(18, 4)  NOT NULL,
            lower_bound         NUMERIC(18, 4),
            upper_bound         NUMERIC(18, 4),
            horizon_week_index  INTEGER         NOT NULL,
            is_published        BOOLEAN         NOT NULL DEFAULT false,
            created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT uq_frw_run_sku_wh_week_model
                UNIQUE (run_id, sku, warehouse_code, week_start, model_code)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_frw_run_id ON forecast_results_weekly (run_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_frw_sku ON forecast_results_weekly (sku)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_frw_warehouse_code ON forecast_results_weekly (warehouse_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_frw_week_start ON forecast_results_weekly (week_start)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_frw_model_code ON forecast_results_weekly (model_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_forecast_results_weekly_id ON forecast_results_weekly (id)")

    # ------------------------------------------------------------------
    # forecast_training_series_weekly
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS forecast_training_series_weekly (
            id                  SERIAL          NOT NULL,
            run_id              INTEGER         NOT NULL
                REFERENCES forecast_runs (id) ON DELETE CASCADE,
            sku                 VARCHAR(64)     NOT NULL,
            warehouse_code      VARCHAR(32)     NOT NULL,
            week_start          DATE            NOT NULL,
            qty                 NUMERIC(18, 4)  NOT NULL,
            is_outlier_flagged  BOOLEAN         NOT NULL DEFAULT false,
            is_excluded         BOOLEAN         NOT NULL DEFAULT false,
            exclusion_reason    VARCHAR(128),
            PRIMARY KEY (id),
            CONSTRAINT uq_ftsw_run_sku_wh_week
                UNIQUE (run_id, sku, warehouse_code, week_start)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_ftsw_run_id ON forecast_training_series_weekly (run_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ftsw_sku ON forecast_training_series_weekly (sku)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ftsw_warehouse_code ON forecast_training_series_weekly (warehouse_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ftsw_week_start ON forecast_training_series_weekly (week_start)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_forecast_training_series_weekly_id ON forecast_training_series_weekly (id)")

    # ------------------------------------------------------------------
    # forecast_run_diagnostics
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS forecast_run_diagnostics (
            id              SERIAL          NOT NULL,
            run_id          INTEGER         NOT NULL
                REFERENCES forecast_runs (id) ON DELETE CASCADE,
            sku             VARCHAR(64),
            warehouse_code  VARCHAR(32),
            level           VARCHAR(16)     NOT NULL DEFAULT 'info',
            category        VARCHAR(64),
            message         TEXT            NOT NULL,
            detail          JSONB,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
            PRIMARY KEY (id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_frd_run_id ON forecast_run_diagnostics (run_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_frd_sku ON forecast_run_diagnostics (sku)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_frd_warehouse_code ON forecast_run_diagnostics (warehouse_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_forecast_run_diagnostics_id ON forecast_run_diagnostics (id)")

    # ------------------------------------------------------------------
    # SQL views (CREATE OR REPLACE is inherently idempotent)
    # ------------------------------------------------------------------

    op.execute("""
        CREATE OR REPLACE VIEW vw_forecast_sales_source_weekly AS
        SELECT
            fsw.id,
            fsc.code          AS source_code,
            fsc.source_type,
            fsc.database_name AS source_database,
            fsc.table_name    AS source_table,
            fsw.sku,
            fsw.warehouse_code,
            fsw.week_start,
            fsw.qty,
            fsw.demand_type,
            fsw.source_row_count,
            fsw.ingested_at
        FROM forecast_sales_weekly fsw
        JOIN forecast_source_configs fsc ON fsc.id = fsw.source_config_id
        WHERE fsc.active = true
    """)

    op.execute("""
        CREATE OR REPLACE VIEW vw_forecast_stock_source_weekly AS
        SELECT
            fstw.id,
            fstw.sku,
            fstw.warehouse_code,
            fstw.week_start,
            fstw.on_hand_qty,
            fstw.source,
            fstw.ingested_at,
            ROW_NUMBER() OVER (
                PARTITION BY fstw.sku, fstw.warehouse_code
                ORDER BY fstw.week_start DESC
            ) AS rn_latest
        FROM forecast_stock_weekly fstw
    """)

    op.execute("""
        CREATE OR REPLACE VIEW vw_forecast_training_base AS
        SELECT
            ftsw.id,
            ftsw.run_id,
            fr.train_end_week_start,
            fr.status           AS run_status,
            ftsw.sku,
            ftsw.warehouse_code,
            ftsw.week_start,
            ftsw.qty,
            ftsw.is_outlier_flagged,
            ftsw.exclusion_reason,
            frm.model_code      AS selected_model_code
        FROM forecast_training_series_weekly ftsw
        JOIN forecast_runs fr ON fr.id = ftsw.run_id
        LEFT JOIN forecast_run_models frm
            ON  frm.run_id         = ftsw.run_id
            AND frm.sku            = ftsw.sku
            AND frm.warehouse_code = ftsw.warehouse_code
            AND frm.selected       = true
        WHERE ftsw.is_excluded = false
    """)


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS vw_forecast_training_base")
    op.execute("DROP VIEW IF EXISTS vw_forecast_stock_source_weekly")
    op.execute("DROP VIEW IF EXISTS vw_forecast_sales_source_weekly")

    op.execute("DROP TABLE IF EXISTS forecast_run_diagnostics")
    op.execute("DROP TABLE IF EXISTS forecast_training_series_weekly")
    op.execute("DROP TABLE IF EXISTS forecast_results_weekly")
    op.execute("DROP TABLE IF EXISTS forecast_run_models")
    op.execute("DROP TABLE IF EXISTS forecast_runs")
    op.execute("DROP TABLE IF EXISTS forecast_stock_weekly")
    op.execute("DROP TABLE IF EXISTS forecast_sales_weekly")
    op.execute("DROP TABLE IF EXISTS forecast_product_profiles")
    op.execute("DROP TABLE IF EXISTS forecast_sku_history_rules")
    op.execute("DROP TABLE IF EXISTS forecast_runtime_configs")
    op.execute("DROP TABLE IF EXISTS forecast_model_configs")
    op.execute("DROP TABLE IF EXISTS forecast_source_configs")
