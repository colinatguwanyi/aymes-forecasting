"""Forecast output ingestion: staging, published baseline, baseline_forecasts_weekly train_end_week_start, plan_runs baseline_train_end.

Revision ID: 011
Revises: 010
Create Date: 2025-02-03

- forecast_run_output_stage: staging for Excel/CSV forecast output rows
- published_baseline_forecasts_weekly: single selected series per (sku, warehouse, week, train_end_week_start)
- baseline_forecasts_weekly: add train_end_week_start, unique includes it
- plan_runs: add baseline_train_end_week_start (which published run to use when demand_source=baseline)
- ingestion_entity_enum: add 'forecast_output'
"""
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- ingestion_entity_enum: add forecast_output ---
    op.execute(
        "DO $$ BEGIN ALTER TYPE ingestion_entity_enum ADD VALUE 'forecast_output'; EXCEPTION WHEN duplicate_object THEN null; END $$"
    )

    # --- forecast_run_output_stage ---
    op.create_table(
        "forecast_run_output_stage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aah_product_code", sa.Text(), nullable=False),
        sa.Column("product_name", sa.Text(), nullable=True),
        sa.Column("inference_date", sa.Date(), nullable=False),
        sa.Column("forecast_week", sa.Date(), nullable=False),
        sa.Column("actual", sa.Numeric(18, 4), nullable=True),
        sa.Column("interpolated_values", sa.Numeric(18, 4), nullable=True),
        sa.Column("forecast", sa.Numeric(18, 4), nullable=True),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("model_details", sa.Text(), nullable=True),
        sa.Column("mae", sa.Numeric(18, 4), nullable=True),
        sa.Column("mape", sa.Numeric(18, 4), nullable=True),
        sa.Column("is_best_model", sa.Boolean(), nullable=True),
        sa.Column("outlier", sa.Integer(), nullable=True),
        sa.Column("predicted_best_model_bool", sa.Boolean(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["ingestion_run_id"], ["ingestion_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_forecast_run_output_stage_aah_product_code", "forecast_run_output_stage", ["aah_product_code"])
    op.create_index("ix_forecast_run_output_stage_inference_date", "forecast_run_output_stage", ["inference_date"])
    op.create_index("ix_forecast_run_output_stage_forecast_week", "forecast_run_output_stage", ["forecast_week"])

    # --- baseline_forecasts_weekly: add train_end_week_start ---
    op.add_column(
        "baseline_forecasts_weekly",
        sa.Column("train_end_week_start", sa.Date(), nullable=True),
    )
    op.execute(
        "UPDATE baseline_forecasts_weekly SET train_end_week_start = train_window_end WHERE train_end_week_start IS NULL"
    )
    op.alter_column(
        "baseline_forecasts_weekly",
        "train_end_week_start",
        nullable=False,
        existing_type=sa.Date(),
    )
    op.create_index(
        "ix_baseline_forecasts_weekly_train_end_week_start",
        "baseline_forecasts_weekly",
        ["train_end_week_start"],
    )
    # Drop old unique and create new one including train_end_week_start
    op.drop_constraint("uq_baseline_forecasts_sku_wh_week_model", "baseline_forecasts_weekly", type_="unique")
    op.create_unique_constraint(
        "uq_baseline_forecasts_sku_wh_week_model_train",
        "baseline_forecasts_weekly",
        ["sku", "warehouse_code", "week_start", "model_name", "model_version", "train_end_week_start"],
    )

    # --- published_baseline_forecasts_weekly ---
    op.create_table(
        "published_baseline_forecasts_weekly",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("warehouse_code", sa.String(32), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("forecast_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("train_end_week_start", sa.Date(), nullable=False),
        sa.Column("selected_model_name", sa.String(64), nullable=False),
        sa.Column("selected_model_version", sa.String(256), nullable=False),
        sa.UniqueConstraint(
            "sku", "warehouse_code", "week_start", "train_end_week_start",
            name="uq_published_baseline_sku_wh_week_train",
        ),
    )
    op.create_index(
        "ix_published_baseline_forecasts_weekly_sku_wh",
        "published_baseline_forecasts_weekly",
        ["sku", "warehouse_code"],
    )
    op.create_index(
        "ix_published_baseline_forecasts_weekly_train_end",
        "published_baseline_forecasts_weekly",
        ["train_end_week_start"],
    )

    # --- plan_runs: baseline_train_end_week_start ---
    op.add_column(
        "plan_runs",
        sa.Column("baseline_train_end_week_start", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plan_runs", "baseline_train_end_week_start")
    op.drop_table("published_baseline_forecasts_weekly")
    op.drop_constraint("uq_baseline_forecasts_sku_wh_week_model_train", "baseline_forecasts_weekly", type_="unique")
    op.create_unique_constraint(
        "uq_baseline_forecasts_sku_wh_week_model",
        "baseline_forecasts_weekly",
        ["sku", "warehouse_code", "week_start", "model_name", "model_version"],
    )
    op.drop_index("ix_baseline_forecasts_weekly_train_end_week_start", table_name="baseline_forecasts_weekly")
    op.drop_column("baseline_forecasts_weekly", "train_end_week_start")
    op.drop_table("forecast_run_output_stage")
    # ingestion_entity_enum: no safe way to remove value in PostgreSQL
    pass
