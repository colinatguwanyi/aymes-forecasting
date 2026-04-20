from __future__ import annotations
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from pydantic_settings import BaseSettings, SettingsConfigDict

# Always load backend/.env regardless of process cwd (e.g. uvicorn started from repo root).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )
    # Platform DB: MySQL 8 only (mysql+pymysql://...).
    database_url: str = "mysql+pymysql://aymes:@localhost:3306/supply_planning?charset=utf8mb4"
    # PyMySQL: set true for many local / Docker installs; use false when the server requires TLS (e.g. Azure).
    database_ssl_disabled: bool = False
    environment: str = "dev"  # dev, local, prod
    # Dev/sandbox only: seeds and planning demo-SKU bypass (see .env.example).
    allow_demo_data: bool = False
    dev_default_user_email: str | None = None  # Fallback when X-Dev-User not provided (dev/local only)
    rbac_bootstrap_admin_emails: str | None = None  # Comma-separated emails for first-admin bootstrap (non-dev only)

    # MySQL source for historical sales (aymes_reports.adhl_data_daily).
    # Set these in .env; they are never hard-coded.
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "aymes"
    mysql_password: str = ""
    mysql_database: str = "aymes_reports"
    # Dedicated MySQL database for all forecast tables.
    # Set MYSQL_FORECAST_DATABASE in .env to override.
    mysql_forecast_database: str = "aymes_forecasting"

    # ---------------------------------------------------------------------------
    # Legacy output compatibility (Vertex pipeline shape)
    # ---------------------------------------------------------------------------
    # Set LEGACY_OUTPUT_ENABLED=true to write to the compatibility table after
    # each successful forecast run.
    legacy_output_enabled: bool = False
    # Set LEGACY_OUTPUT_SAFE_REPLACE=true to also promote the staging table
    # content into the live consumption table after validation.
    legacy_output_safe_replace: bool = False
    # MySQL database that hosts the legacy output tables (usually aymes_reports).
    legacy_output_target_db: str = "aymes_reports"
    # Staging table name — written by every run (rows appended, not replaced).
    legacy_output_staging_table: str = "aymes_demand_planning_forecast_by_model_new"
    # Live table name — only updated when safe_replace is True.
    legacy_output_live_table: str = "aymes_demand_planning_forecast_by_model"

    # Optional per-connection overrides for the legacy output MySQL database.
    # When not set (None), each falls back to the corresponding mysql_* value above.
    # Use these when the legacy output database lives on a different server or
    # requires a different user from the main aymes_reports sales connection.
    #
    # Live aymes_reports credentials (GCP Cloud SQL):
    #   host:     35.233.108.189
    #   user:     aymesBI
    #   password: set in .env as LEGACY_OUTPUT_MYSQL_PASSWORD
    #   database: aymes_reports  (legacy_output_target_db above)
    legacy_output_mysql_host: str | None = None
    legacy_output_mysql_port: int | None = None
    legacy_output_mysql_user: str | None = None
    legacy_output_mysql_password: str | None = None

    # ---------------------------------------------------------------------------
    # File export and parity validation
    # ---------------------------------------------------------------------------
    # Root directory where per-run output folders are written.
    # Each run writes to {forecast_output_root}/{run_uuid}/
    forecast_output_root: str = "forecast_output"
    # Set LEGACY_FILE_EXPORT_ENABLED=true to generate CSV files after each run.
    legacy_file_export_enabled: bool = False
    # Set LEGACY_PARITY_VALIDATION_ENABLED=true to compare against the legacy
    # MySQL table after each run.
    legacy_parity_validation_enabled: bool = False
    # How many SKUs to sample for value-level comparison during parity validation.
    legacy_parity_sample_size: int = 50
    # If true, a parity mismatch will cause the run to be marked 'partial' and
    # an error diagnostic is written.  False records a warning but does not
    # affect run status.
    legacy_parity_fail_on_mismatch: bool = False


settings: Settings = Settings()
