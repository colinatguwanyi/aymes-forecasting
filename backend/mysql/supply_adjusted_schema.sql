-- =============================================================================
-- Supply-Aware Forecasting Layer — MySQL 8 DDL
-- Post-processing table: applies SOH + inbound supply to base forecast output.
-- Does NOT modify forecast_results_weekly (SAP/legacy output is untouched).
-- Run this against the aymes_forecasting database.
-- =============================================================================

USE aymes_forecasting;

-- ---------------------------------------------------------------------------
-- forecast_supply_adjusted
-- One row per run × product × warehouse × forecast_week (best-model only).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS forecast_supply_adjusted (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id              BIGINT          NOT NULL,

    product_code        VARCHAR(50)     NOT NULL,
    warehouse_code      VARCHAR(50)     NULL,
    forecast_week       DATE            NOT NULL,

    -- Base forecast from forecast_results_weekly (is_best_model = true)
    base_forecast       DECIMAL(18, 4)  NOT NULL DEFAULT 0.0000,

    -- Stock position at forecast_week
    stock_on_hand       DECIMAL(18, 4)  NULL,
    inbound_orders      DECIMAL(18, 4)  NULL,   -- in_transit + open_po
    available_stock     DECIMAL(18, 4)  NULL,   -- soh + inbound

    -- Adjusted output
    adjusted_forecast   DECIMAL(18, 4)  NULL,   -- min(base_forecast, available_stock)
    stockout_flag       BOOLEAN         NOT NULL DEFAULT FALSE,  -- available < base
    excess_stock_flag   BOOLEAN         NOT NULL DEFAULT FALSE,  -- available > base * 2

    -- Source tracking
    stock_source        VARCHAR(50)     NOT NULL DEFAULT 'forecast_stock_weekly',
                                                -- 'forecast_stock_weekly' | 'mock'
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_supply_adjusted (run_id, product_code, warehouse_code, forecast_week),
    KEY idx_supply_adjusted_run     (run_id),
    KEY idx_supply_adjusted_product (product_code, forecast_week)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
