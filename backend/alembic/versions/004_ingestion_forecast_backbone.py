"""Ingestion + weekly canonical + baseline forecast backbone.

Revision ID: 004
Revises: 003
Create Date: 2025-02-03

Adds: ingestion_runs, ingestion_rejections, sku_code_map, demand_stage_weekly,
demand_facts_weekly, baseline_forecasts_weekly.
"""
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Enums for ingestion_runs ---
    op.execute(
        "DO $$ BEGIN CREATE TYPE ingestion_source_type_enum AS ENUM ('CSV', 'DB sync', 'manual');"
        " EXCEPTION WHEN duplicate_object THEN null; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE ingestion_entity_enum AS ENUM ('demand', 'receipts', 'inventory', 'sku_map');"
        " EXCEPTION WHEN duplicate_object THEN null; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE ingestion_status_enum AS ENUM ('pending', 'running', 'success', 'failed');"
        " EXCEPTION WHEN duplicate_object THEN null; END $$"
    )

    # --- ingestion_runs (id UUID) ---
    op.execute(
        "CREATE TABLE ingestion_runs ("
        " id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
        " source_type ingestion_source_type_enum NOT NULL,"
        " entity ingestion_entity_enum NOT NULL,"
        " file_name VARCHAR(512),"
        " file_sha256 VARCHAR(64),"
        " started_at TIMESTAMP WITH TIME ZONE,"
        " finished_at TIMESTAMP WITH TIME ZONE,"
        " status ingestion_status_enum NOT NULL DEFAULT 'pending',"
        " row_count INTEGER DEFAULT 0,"
        " inserted_count INTEGER DEFAULT 0,"
        " updated_count INTEGER DEFAULT 0,"
        " rejected_count INTEGER DEFAULT 0,"
        " error_summary TEXT,"
        " created_by VARCHAR(256)"
        ")"
    )
    op.create_index("ix_ingestion_runs_status", "ingestion_runs", ["status"])
    op.create_index("ix_ingestion_runs_entity", "ingestion_runs", ["entity"])
    op.create_index("ix_ingestion_runs_started_at", "ingestion_runs", ["started_at"])

    # --- ingestion_rejections ---
    op.create_table(
        "ingestion_rejections",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
    )
    op.create_index("ix_ingestion_rejections_run_id", "ingestion_rejections", ["ingestion_run_id"])

    # --- sku_code_map ---
    op.create_table(
        "sku_code_map",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("old_sku", sa.String(64), nullable=False),
        sa.Column("new_sku", sa.String(64), nullable=False),
        sa.Column("effective_from_week_start", sa.Date(), nullable=True),
        sa.Column("effective_to_week_start", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "old_sku", "new_sku", "effective_from_week_start",
            name="uq_sku_code_map_old_new_from",
        ),
    )
    op.create_index("ix_sku_code_map_old_sku", "sku_code_map", ["old_sku"])
    op.create_index("ix_sku_code_map_new_sku", "sku_code_map", ["new_sku"])

    # --- demand_stage_weekly (demand_type: reuse existing demandtype enum) ---
    op.execute(
        "CREATE TABLE demand_stage_weekly ("
        " id SERIAL PRIMARY KEY,"
        " ingestion_run_id UUID NOT NULL REFERENCES ingestion_runs(id) ON DELETE CASCADE,"
        " week_start DATE NOT NULL,"
        " sku_raw VARCHAR(64) NOT NULL,"
        " sku VARCHAR(64) NOT NULL,"
        " warehouse_code VARCHAR(32) NOT NULL,"
        " demand_type demandtype NOT NULL,"
        " qty NUMERIC(18,4) NOT NULL,"
        " source VARCHAR(64)"
        ")"
    )
    op.create_index("ix_demand_stage_weekly_run_id", "demand_stage_weekly", ["ingestion_run_id"])
    op.create_index("ix_demand_stage_weekly_week_sku_wh", "demand_stage_weekly", ["week_start", "sku", "warehouse_code"])

    # --- demand_facts_weekly (canonical weekly demand; reuse demandtype) ---
    op.execute(
        "CREATE TABLE demand_facts_weekly ("
        " id SERIAL PRIMARY KEY,"
        " week_start DATE NOT NULL,"
        " sku VARCHAR(64) NOT NULL,"
        " warehouse_code VARCHAR(32) NOT NULL,"
        " demand_type demandtype NOT NULL,"
        " qty NUMERIC(18,4) NOT NULL,"
        " source_run_id UUID REFERENCES ingestion_runs(id) ON DELETE SET NULL,"
        " is_imputed BOOLEAN NOT NULL DEFAULT false,"
        " is_outlier BOOLEAN NOT NULL DEFAULT false,"
        " outlier_method VARCHAR(64),"
        " CONSTRAINT uq_demand_facts_weekly_week_sku_wh_type UNIQUE (week_start, sku, warehouse_code, demand_type)"
        ")"
    )
    op.create_index("ix_demand_facts_weekly_week_start", "demand_facts_weekly", ["week_start"])
    op.create_index("ix_demand_facts_weekly_sku_wh", "demand_facts_weekly", ["sku", "warehouse_code"])

    # --- baseline_forecasts_weekly ---
    op.create_table(
        "baseline_forecasts_weekly",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("warehouse_code", sa.String(32), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("horizon_week_index", sa.Integer(), nullable=False),
        sa.Column("forecast_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("model_name", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("train_window_start", sa.Date(), nullable=False),
        sa.Column("train_window_end", sa.Date(), nullable=False),
        sa.Column("metrics_json", postgresql.JSONB(), nullable=True),
        sa.UniqueConstraint(
            "sku", "warehouse_code", "week_start", "model_name", "model_version",
            name="uq_baseline_forecasts_sku_wh_week_model",
        ),
    )
    op.create_index("ix_baseline_forecasts_weekly_sku_wh", "baseline_forecasts_weekly", ["sku", "warehouse_code"])
    op.create_index("ix_baseline_forecasts_weekly_week_start", "baseline_forecasts_weekly", ["week_start"])


def downgrade() -> None:
    op.drop_table("baseline_forecasts_weekly")
    op.drop_table("demand_facts_weekly")
    op.drop_table("demand_stage_weekly")
    op.drop_table("sku_code_map")
    op.drop_table("ingestion_rejections")
    op.drop_table("ingestion_runs")
    op.execute("DROP TYPE IF EXISTS ingestion_status_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS ingestion_entity_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS ingestion_source_type_enum CASCADE")
