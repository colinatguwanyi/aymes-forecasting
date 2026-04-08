-- =============================================================================
-- MySQL 8 DDL for the aymes_forecasting forecast subsystem.
-- Run this once against the target MySQL 8 server to create the schema.
-- All tables use InnoDB, utf8mb4, and MySQL-native JSON columns.
-- =============================================================================

CREATE DATABASE IF NOT EXISTS aymes_forecasting
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE aymes_forecasting;

-- ---------------------------------------------------------------------------
-- 1. forecast_source_configs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS forecast_source_configs (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_name         VARCHAR(100) NOT NULL UNIQUE,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,

    mysql_host          VARCHAR(255),
    mysql_port          INT,
    mysql_database      VARCHAR(100) NOT NULL,
    mysql_schema_name   VARCHAR(100) NOT NULL DEFAULT 'aymes_reports',
    mysql_sales_table   VARCHAR(100) NOT NULL DEFAULT 'adhl_data_daily',

    soh_source_mode     VARCHAR(50)  NOT NULL DEFAULT 'external_current_source',
    soh_connection_name VARCHAR(255) NULL,
    soh_table_name      VARCHAR(255) NULL,

    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- 2. forecast_runtime_configs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS forecast_runtime_configs (
    id                              BIGINT AUTO_INCREMENT PRIMARY KEY,
    config_name                     VARCHAR(100) NOT NULL UNIQUE,
    is_active                       BOOLEAN NOT NULL DEFAULT FALSE,

    forecast_horizon_weeks          INT           NOT NULL DEFAULT 52,
    min_history_weeks               INT           NOT NULL DEFAULT 60,
    outlier_threshold               DECIMAL(8,4)  NOT NULL DEFAULT 0.5000,

    zero_stock_units_threshold      DECIMAL(18,4) NOT NULL DEFAULT 5.0000,
    low_stock_cover_weeks_threshold DECIMAL(18,4) NOT NULL DEFAULT 2.0000,
    constrained_weeks_handling      VARCHAR(50)   NOT NULL DEFAULT 'flag_only',

    min_sparse_history_weeks        INT     NOT NULL DEFAULT 12,
    enable_stock_classification     BOOLEAN NOT NULL DEFAULT TRUE,
    enable_launch_routing           BOOLEAN NOT NULL DEFAULT TRUE,

    best_model_tie_break_order      JSON NOT NULL,

    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- 3. forecast_sku_history_rules
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS forecast_sku_history_rules (
    id                              BIGINT AUTO_INCREMENT PRIMARY KEY,
    old_product_code                VARCHAR(50) NOT NULL,
    new_product_code                VARCHAR(50) NOT NULL,
    merged_into_sku                 VARCHAR(50) NULL,

    effective_from                  DATE NULL,
    effective_to                    DATE NULL,
    multiply_by_item_size           BOOLEAN NOT NULL DEFAULT FALSE,
    drop_old_rows_from_effective_from BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                       BOOLEAN NOT NULL DEFAULT TRUE,
    notes                           TEXT NULL,

    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- 4. forecast_product_profiles
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS forecast_product_profiles (
    id                      BIGINT AUTO_INCREMENT PRIMARY KEY,
    product_code            VARCHAR(50) NOT NULL,
    warehouse_code          VARCHAR(50) NULL,

    lifecycle_stage         VARCHAR(50) NOT NULL DEFAULT 'mature',
    analogue_product_code   VARCHAR(50) NULL,
    force_strategy          VARCHAR(50) NULL,

    launch_date             DATE NULL,
    discontinue_date        DATE NULL,

    include_in_forecast     BOOLEAN NOT NULL DEFAULT TRUE,
    notes                   TEXT NULL,

    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_forecast_product_profile (product_code, warehouse_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- 5. forecast_sales_weekly
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS forecast_sales_weekly (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id          BIGINT NULL,
    product_code    VARCHAR(50) NOT NULL,
    warehouse_code  VARCHAR(50) NULL,
    week_start      DATE NOT NULL,

    units_sold      DECIMAL(18,4) NOT NULL DEFAULT 0.0000,
    product_name    VARCHAR(255) NULL,
    pip_code        VARCHAR(50)  NULL,
    item_size       DECIMAL(18,4) NULL,

    source_system   VARCHAR(100) NOT NULL DEFAULT 'mysql_vertex_source',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_forecast_sales_weekly (product_code, warehouse_code, week_start, source_system),
    KEY idx_forecast_sales_weekly_product_week (product_code, week_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- 6. forecast_stock_weekly
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS forecast_stock_weekly (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id          BIGINT NULL,
    product_code    VARCHAR(50) NOT NULL,
    warehouse_code  VARCHAR(50) NOT NULL,
    week_start      DATE NOT NULL,

    soh_units           DECIMAL(18,4) NOT NULL DEFAULT 0.0000,
    in_transit_units    DECIMAL(18,4) NULL,
    open_po_units       DECIMAL(18,4) NULL,

    stock_status        VARCHAR(50) NULL,
    is_stockout         BOOLEAN NOT NULL DEFAULT FALSE,
    is_constrained      BOOLEAN NOT NULL DEFAULT FALSE,

    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_forecast_stock_weekly (product_code, warehouse_code, week_start),
    KEY idx_forecast_stock_weekly_product_week (product_code, warehouse_code, week_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- 7. forecast_runs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS forecast_runs (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_uuid        CHAR(36) NOT NULL UNIQUE,
    run_status      VARCHAR(50) NOT NULL DEFAULT 'queued',
    run_type        VARCHAR(50) NOT NULL DEFAULT 'manual',

    inference_date  DATE NOT NULL,
    horizon_weeks   INT  NOT NULL DEFAULT 52,

    source_config_id    BIGINT NULL,
    runtime_config_id   BIGINT NULL,

    started_at      DATETIME NULL,
    completed_at    DATETIME NULL,
    error_message   TEXT NULL,

    created_by  VARCHAR(255) NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    KEY idx_forecast_runs_status    (run_status),
    KEY idx_forecast_runs_inference (inference_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- 8. forecast_run_models
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS forecast_run_models (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id          BIGINT NOT NULL,
    model_code      VARCHAR(100) NOT NULL,
    model_family    VARCHAR(50)  NOT NULL,
    strategy        VARCHAR(50)  NULL,
    series_variant  VARCHAR(50)  NOT NULL,
    run_status      VARCHAR(50)  NOT NULL DEFAULT 'queued',

    products_attempted  INT NOT NULL DEFAULT 0,
    products_succeeded  INT NOT NULL DEFAULT 0,
    products_failed     INT NOT NULL DEFAULT 0,

    mape            DECIMAL(18,6) NULL,
    mae             DECIMAL(18,6) NULL,
    metrics_json    JSON NULL,
    error_message   TEXT NULL,

    started_at      DATETIME NULL,
    completed_at    DATETIME NULL,

    UNIQUE KEY uq_forecast_run_models (run_id, model_code, series_variant),
    KEY idx_forecast_run_models_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- 9. forecast_training_series_weekly
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS forecast_training_series_weekly (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id          BIGINT NOT NULL,
    product_code    VARCHAR(50) NOT NULL,
    warehouse_code  VARCHAR(50) NULL,
    week_start      DATE NOT NULL,

    qty                  DECIMAL(18,4) NULL,
    adjusted_qty         DECIMAL(18,4) NULL,
    stock_adjusted_qty   DECIMAL(18,4) NULL,
    interpolated_units   DECIMAL(18,4) NULL,

    is_outlier_flagged   BOOLEAN NOT NULL DEFAULT FALSE,
    is_stock_constrained BOOLEAN NOT NULL DEFAULT FALSE,
    is_excluded          BOOLEAN NOT NULL DEFAULT FALSE,

    week_classification  VARCHAR(50) NULL,
    soh_units            DECIMAL(18,4) NULL,

    series_variant  VARCHAR(50) NOT NULL DEFAULT 'raw',

    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_forecast_training_series (run_id, product_code, warehouse_code, week_start, series_variant),
    KEY idx_forecast_training_series_run_product (run_id, product_code, week_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- 10. forecast_results_weekly
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS forecast_results_weekly (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id          BIGINT NOT NULL,

    product_code    VARCHAR(50)  NOT NULL,
    warehouse_code  VARCHAR(50)  NULL,
    product_name    VARCHAR(255) NULL,

    inference_date  DATE NOT NULL,
    forecast_week   DATE NOT NULL,

    actual_units        DECIMAL(18,4) NULL,
    interpolated_units  DECIMAL(18,4) NULL,
    forecast_units      DECIMAL(18,4) NULL,

    model_name      VARCHAR(100) NOT NULL,
    model_details   VARCHAR(100) NOT NULL,

    mape    DECIMAL(18,6) NULL,
    mae     DECIMAL(18,6) NULL,

    is_best_model               BOOLEAN NULL,
    predicted_best_model_bool   BOOLEAN NULL,

    outlier_flag    BOOLEAN NULL,
    stockout_flag   BOOLEAN NULL,
    constrained_flag BOOLEAN NULL,

    result_meta JSON NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_forecast_results_weekly (run_id, product_code, warehouse_code, forecast_week, model_details),
    KEY idx_forecast_results_product_week (product_code, forecast_week),
    KEY idx_forecast_results_run          (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- 11. forecast_run_diagnostics
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS forecast_run_diagnostics (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id          BIGINT NOT NULL,
    product_code    VARCHAR(50) NULL,
    warehouse_code  VARCHAR(50) NULL,

    diagnostic_type     VARCHAR(100) NOT NULL,
    diagnostic_level    VARCHAR(20)  NOT NULL DEFAULT 'info',
    message             TEXT NOT NULL,
    payload_json        JSON NULL,

    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    KEY idx_forecast_diag_run     (run_id),
    KEY idx_forecast_diag_product (product_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
