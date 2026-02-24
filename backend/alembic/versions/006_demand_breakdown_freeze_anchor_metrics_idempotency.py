"""Demand breakdown, freeze anchor, baseline horizon_week nullable, ingestion duplicate_noop, forecast_run_metrics.

Revision ID: 006
Revises: 005
Create Date: 2025-02-03

- plan_run_demand_inputs_weekly: add demand_breakdown_json JSONB NULL
- plan_runs: add plan_start_week_start DATE NOT NULL (backfill from run_at)
- baseline_forecasts_weekly: horizon_week_index nullable
- ingestion_status_enum: add 'duplicate_noop'
- forecast_run_metrics: new table (model_name, model_version, train_end_week_start, sku, warehouse_code, wape, bias)
"""
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- plan_run_demand_inputs_weekly: demand_breakdown_json ---
    op.add_column(
        "plan_run_demand_inputs_weekly",
        sa.Column("demand_breakdown_json", postgresql.JSONB(), nullable=True),
    )

    # --- plan_runs: plan_start_week_start (W-TUE anchor for freeze) ---
    op.add_column("plan_runs", sa.Column("plan_start_week_start", sa.Date(), nullable=True))
    # Backfill: set to run_at for existing rows (application will use W-TUE; for old runs we use run_at as proxy)
    op.execute(
        "UPDATE plan_runs SET plan_start_week_start = run_at WHERE plan_start_week_start IS NULL"
    )
    op.alter_column(
        "plan_runs",
        "plan_start_week_start",
        nullable=False,
        server_default=sa.text("CURRENT_DATE"),
    )

    # --- baseline_forecasts_weekly: horizon_week_index nullable (derived, not part of identity) ---
    op.alter_column(
        "baseline_forecasts_weekly",
        "horizon_week_index",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # --- ingestion_status_enum: add duplicate_noop ---
    op.execute(
        "DO $$ BEGIN ALTER TYPE ingestion_status_enum ADD VALUE 'duplicate_noop'; EXCEPTION WHEN duplicate_object THEN null; END $$"
    )

    # --- forecast_run_metrics ---
    op.create_table(
        "forecast_run_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("model_name", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("train_end_week_start", sa.Date(), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("warehouse_code", sa.String(32), nullable=False),
        sa.Column("wape", sa.Numeric(12, 6), nullable=True),
        sa.Column("bias", sa.Numeric(18, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "model_name", "model_version", "train_end_week_start", "sku", "warehouse_code",
            name="uq_forecast_run_metrics_model_train_sku_wh",
        ),
    )
    op.create_index("ix_forecast_run_metrics_train", "forecast_run_metrics", ["train_end_week_start", "model_name"])
    op.create_index("ix_forecast_run_metrics_sku_wh", "forecast_run_metrics", ["sku", "warehouse_code"])


def downgrade() -> None:
    op.drop_table("forecast_run_metrics")
    # Cannot remove enum value in PG easily; leave duplicate_noop
    op.execute("UPDATE baseline_forecasts_weekly SET horizon_week_index = 1 WHERE horizon_week_index IS NULL")
    op.alter_column(
        "baseline_forecasts_weekly",
        "horizon_week_index",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.drop_column("plan_runs", "plan_start_week_start")
    op.drop_column("plan_run_demand_inputs_weekly", "demand_breakdown_json")
