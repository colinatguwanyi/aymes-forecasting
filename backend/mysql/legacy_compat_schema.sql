-- =============================================================================
-- Legacy compatibility output table for aymes_demand_planning_forecast_by_model.
--
-- Target database: aymes_reports (same server as forecast data).
-- The staging table is written first; the live table is only updated when
-- safe-replace is explicitly enabled (LEGACY_OUTPUT_SAFE_REPLACE=true in .env).
--
-- Column names intentionally match the original Vertex pipeline output shape
-- so that downstream consumers (Power BI, planning tools, Vertex readers) need
-- no changes.
-- =============================================================================

USE aymes_reports;

-- ---------------------------------------------------------------------------
-- Staging table — written to by every forecast run.
-- Rows are always appended per run; old runs are not deleted automatically.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS aymes_demand_planning_forecast_by_model_new (
    id                              BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- Legacy output columns (Vertex pipeline shape)
    AAH_Product_Code                VARCHAR(50)   NOT NULL,
    Product_Name                    VARCHAR(255)  NULL,
    Inference_Date                  DATE          NOT NULL,
    Forecast_Week                   DATE          NOT NULL,
    Actual                          DECIMAL(18,4) NULL,
    Interpolated_Values             DECIMAL(18,4) NULL,
    Forecast                        DECIMAL(18,4) NULL,
    Model                           VARCHAR(100)  NOT NULL,
    Model_Details                   VARCHAR(100)  NOT NULL,
    Mean_Absolute_Percentage_Error  DECIMAL(18,6) NULL,
    Mean_Absolute_Error             DECIMAL(18,6) NULL,
    Is_Best_Model                   BOOLEAN       NULL,
    Outlier                         BOOLEAN       NULL,
    Predicted_Best_Model_Bool       BOOLEAN       NULL,

    -- Traceability (not in the original Vertex output, but useful for auditing)
    run_id          BIGINT       NOT NULL,
    warehouse_code  VARCHAR(50)  NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    KEY idx_legacy_compat_product_week  (AAH_Product_Code, Forecast_Week),
    KEY idx_legacy_compat_run           (run_id),
    KEY idx_legacy_compat_inference     (Inference_Date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- Live table — consumers read from this.
-- Only populated by an explicit safe-replace swap triggered by the exporter
-- when LEGACY_OUTPUT_SAFE_REPLACE=true.
-- This CREATE is a no-op if the original table already exists.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS aymes_demand_planning_forecast_by_model (
    id                              BIGINT AUTO_INCREMENT PRIMARY KEY,
    AAH_Product_Code                VARCHAR(50)   NOT NULL,
    Product_Name                    VARCHAR(255)  NULL,
    Inference_Date                  DATE          NOT NULL,
    Forecast_Week                   DATE          NOT NULL,
    Actual                          DECIMAL(18,4) NULL,
    Interpolated_Values             DECIMAL(18,4) NULL,
    Forecast                        DECIMAL(18,4) NULL,
    Model                           VARCHAR(100)  NOT NULL,
    Model_Details                   VARCHAR(100)  NOT NULL,
    Mean_Absolute_Percentage_Error  DECIMAL(18,6) NULL,
    Mean_Absolute_Error             DECIMAL(18,6) NULL,
    Is_Best_Model                   BOOLEAN       NULL,
    Outlier                         BOOLEAN       NULL,
    Predicted_Best_Model_Bool       BOOLEAN       NULL,
    run_id          BIGINT       NOT NULL,
    warehouse_code  VARCHAR(50)  NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    KEY idx_legacy_live_product_week (AAH_Product_Code, Forecast_Week),
    KEY idx_legacy_live_run          (run_id),
    KEY idx_legacy_live_inference    (Inference_Date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
