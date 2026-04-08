"""
Add stock-aware preprocessing and new-product routing fields.

Revision ID: 024
Revises: 023
Create Date: 2026-03-25

Schema additions (all guarded with IF NOT EXISTS):

forecast_product_profiles:
  + analogue_product_code  VARCHAR(64)   — reference SKU for launch scaling
  + force_strategy         VARCHAR(64)   — override routing decision
  + launch_date            DATE          — estimated product launch date
  + discontinue_date       DATE          — estimated discontinuation date

forecast_training_series_weekly:
  + week_classification    VARCHAR(32)   — normal / zero_true_demand / zero_stockout /
                                           constrained_low_stock / launch_gap
  + soh_units              NUMERIC(18,4) — SOH at this week (from inventory_snapshots_weekly)
  + stock_adjusted_qty     NUMERIC(18,4) — stock-aware imputed demand value
  + is_stock_constrained   BOOLEAN       — true when classification signals constrained supply

forecast_runtime_configs:
  + stock_params           JSONB         — thresholds and handling mode for stock-aware logic
                                           keys: zero_stock_units_threshold,
                                                 low_stock_cover_weeks_threshold,
                                                 constrained_weeks_handling,
                                                 min_sparse_history_weeks,
                                                 min_mature_history_weeks,
                                                 enable_launch_routing

forecast_run_models:
  + strategy               VARCHAR(64)   — routing strategy used: mature_history /
                                           sparse_history / launch / exclude
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

from alembic import op

logger = logging.getLogger(__name__)

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # forecast_product_profiles — new-product routing fields
    op.execute("""
        ALTER TABLE forecast_product_profiles
        ADD COLUMN IF NOT EXISTS analogue_product_code VARCHAR(64)
    """)
    op.execute("""
        ALTER TABLE forecast_product_profiles
        ADD COLUMN IF NOT EXISTS force_strategy VARCHAR(64)
    """)
    op.execute("""
        ALTER TABLE forecast_product_profiles
        ADD COLUMN IF NOT EXISTS launch_date DATE
    """)
    op.execute("""
        ALTER TABLE forecast_product_profiles
        ADD COLUMN IF NOT EXISTS discontinue_date DATE
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_fpp_lifecycle_stage
        ON forecast_product_profiles (lifecycle_stage)
    """)

    # forecast_training_series_weekly — stock classification columns
    op.execute("""
        ALTER TABLE forecast_training_series_weekly
        ADD COLUMN IF NOT EXISTS week_classification VARCHAR(32)
    """)
    op.execute("""
        ALTER TABLE forecast_training_series_weekly
        ADD COLUMN IF NOT EXISTS soh_units NUMERIC(18, 4)
    """)
    op.execute("""
        ALTER TABLE forecast_training_series_weekly
        ADD COLUMN IF NOT EXISTS stock_adjusted_qty NUMERIC(18, 4)
    """)
    op.execute("""
        ALTER TABLE forecast_training_series_weekly
        ADD COLUMN IF NOT EXISTS is_stock_constrained BOOLEAN NOT NULL DEFAULT false
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_ftsw_week_classification
        ON forecast_training_series_weekly (week_classification)
    """)

    # forecast_runtime_configs — stock-aware preprocessing params
    op.execute("""
        ALTER TABLE forecast_runtime_configs
        ADD COLUMN IF NOT EXISTS stock_params JSONB
    """)

    # forecast_run_models — strategy used for this sku/warehouse
    op.execute("""
        ALTER TABLE forecast_run_models
        ADD COLUMN IF NOT EXISTS strategy VARCHAR(64)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE forecast_run_models DROP COLUMN IF EXISTS strategy")
    op.execute("ALTER TABLE forecast_runtime_configs DROP COLUMN IF EXISTS stock_params")
    op.execute("DROP INDEX IF EXISTS ix_ftsw_week_classification")
    op.execute("ALTER TABLE forecast_training_series_weekly DROP COLUMN IF EXISTS is_stock_constrained")
    op.execute("ALTER TABLE forecast_training_series_weekly DROP COLUMN IF EXISTS stock_adjusted_qty")
    op.execute("ALTER TABLE forecast_training_series_weekly DROP COLUMN IF EXISTS soh_units")
    op.execute("ALTER TABLE forecast_training_series_weekly DROP COLUMN IF EXISTS week_classification")
    op.execute("DROP INDEX IF EXISTS ix_fpp_lifecycle_stage")
    op.execute("ALTER TABLE forecast_product_profiles DROP COLUMN IF EXISTS discontinue_date")
    op.execute("ALTER TABLE forecast_product_profiles DROP COLUMN IF EXISTS launch_date")
    op.execute("ALTER TABLE forecast_product_profiles DROP COLUMN IF EXISTS force_strategy")
    op.execute("ALTER TABLE forecast_product_profiles DROP COLUMN IF EXISTS analogue_product_code")
