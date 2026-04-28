"""Replace legacy forecast ORM tables with MySQL engine schema (app.forecast_mysql_models).

Revisions 001 + app.forecast_models created forecast_source_configs / forecast_runtime_configs
with different columns (code, host_env_var, …) than the v2 /admin forecast engine expects
(source_name, config_name, …).  This migration drops those legacy tables and
create_all() for :class:`app.forecast_mysql_models.MySQLForecastBase`.

downgrade drops engine tables only; it does not restore the legacy app.forecast_models schema.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "004_forecast_engine_mysql"
down_revision: Union[str, None] = "003_warehouse_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Legacy app.forecast_models tables (001 baseline).  Order does not matter with FK checks off.
_LEGACY_FORECAST_TABLES: tuple[str, ...] = (
    "forecast_run_diagnostics",
    "forecast_results_weekly",
    "forecast_training_series_weekly",
    "forecast_run_models",
    "forecast_runs",
    "forecast_sales_weekly",
    "forecast_stock_weekly",
    "forecast_sku_history_rules",
    "forecast_product_profiles",
    "forecast_runtime_configs",
    "forecast_model_configs",
    "forecast_source_configs",
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("SET FOREIGN_KEY_CHECKS=0"))
    for name in _LEGACY_FORECAST_TABLES:
        bind.execute(text(f"DROP TABLE IF EXISTS `{name}`"))
    bind.execute(text("SET FOREIGN_KEY_CHECKS=1"))

    # Load ORM and create engine-only tables (includes forecast_supply_adjusted, etc.)
    import app.forecast_mysql_models  # noqa: F401

    from app.forecast_mysql_models import MySQLForecastBase

    MySQLForecastBase.metadata.create_all(bind=bind)


def downgrade() -> None:
    from app.forecast_mysql_models import MySQLForecastBase

    bind = op.get_bind()
    MySQLForecastBase.metadata.drop_all(bind=bind)
