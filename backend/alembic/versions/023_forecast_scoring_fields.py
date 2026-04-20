"""Add scoring fields and adjusted series columns for Vertex-parity pipeline.

Revision ID: 023
Revises: 022
Create Date: 2026-03-25

Changes:
  forecast_sku_history_rules  + merged_into_sku  (old-code → new-code mapping)
  forecast_training_series_weekly + adjusted_qty  (outlier-replaced value)
  forecast_run_models         + mape, mae
  forecast_results_weekly     + result_meta JSONB  (legacy output fields)

All ALTER statements use IF NOT EXISTS / IF EXISTS guards to remain idempotent.
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

from alembic import op

logger = logging.getLogger(__name__)

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # forecast_sku_history_rules: product-code merge support
    op.execute("""
        ALTER TABLE forecast_sku_history_rules
        ADD COLUMN IF NOT EXISTS merged_into_sku VARCHAR(64)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_fshr_merged_into_sku
        ON forecast_sku_history_rules (merged_into_sku)
    """)

    # forecast_training_series_weekly: outlier-adjusted value
    op.execute("""
        ALTER TABLE forecast_training_series_weekly
        ADD COLUMN IF NOT EXISTS adjusted_qty NUMERIC(18, 4)
    """)

    # forecast_run_models: MAPE and MAE per model per SKU/warehouse
    op.execute("""
        ALTER TABLE forecast_run_models
        ADD COLUMN IF NOT EXISTS mape NUMERIC(10, 6)
    """)
    op.execute("""
        ALTER TABLE forecast_run_models
        ADD COLUMN IF NOT EXISTS mae NUMERIC(18, 4)
    """)

    # forecast_results_weekly: JSONB bag for legacy output fields
    # (actual_units, interpolated_units, outlier_flag, predicted_best_model_bool, etc.)
    op.execute("""
        ALTER TABLE forecast_results_weekly
        ADD COLUMN IF NOT EXISTS result_meta JSONB
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE forecast_results_weekly DROP COLUMN IF EXISTS result_meta")
    op.execute("ALTER TABLE forecast_run_models DROP COLUMN IF EXISTS mae")
    op.execute("ALTER TABLE forecast_run_models DROP COLUMN IF EXISTS mape")
    op.execute("ALTER TABLE forecast_training_series_weekly DROP COLUMN IF EXISTS adjusted_qty")
    op.execute("ALTER TABLE forecast_sku_history_rules DROP COLUMN IF EXISTS merged_into_sku")
