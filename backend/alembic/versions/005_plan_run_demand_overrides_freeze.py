"""Plan run demand source, overrides, freeze: extend plan_runs; add demand inputs, overrides, freeze events; planned_orders.is_frozen.

Revision ID: 005
Revises: 004
Create Date: 2025-02-03

"""
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Extend plan_runs (backward compatible) ---
    op.add_column("plan_runs", sa.Column("demand_source", sa.String(32), nullable=True))
    op.execute("UPDATE plan_runs SET demand_source = 'actuals' WHERE demand_source IS NULL")
    op.alter_column("plan_runs", "demand_source", nullable=False, server_default="actuals")
    op.add_column("plan_runs", sa.Column("freeze_weeks", sa.Integer(), nullable=True))
    op.execute("UPDATE plan_runs SET freeze_weeks = 4 WHERE freeze_weeks IS NULL")
    op.alter_column("plan_runs", "freeze_weeks", nullable=False, server_default="4")
    op.add_column("plan_runs", sa.Column("created_by", sa.String(256), nullable=True))
    op.add_column("plan_runs", sa.Column("notes", sa.Text(), nullable=True))

    # --- plan_run_demand_inputs_weekly ---
    op.create_table(
        "plan_run_demand_inputs_weekly",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("plan_run_id", sa.Integer(), sa.ForeignKey("plan_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("warehouse_code", sa.String(32), nullable=False),
        sa.Column("demand_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_ref", postgresql.JSONB(), nullable=True),
        sa.Column("is_frozen", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint(
            "plan_run_id", "week_start", "sku", "warehouse_code",
            name="uq_plan_run_demand_inputs_run_week_sku_wh",
        ),
    )
    op.create_index("ix_plan_run_demand_inputs_plan_run_id", "plan_run_demand_inputs_weekly", ["plan_run_id"])

    # --- demand_overrides_weekly ---
    op.create_table(
        "demand_overrides_weekly",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("plan_run_id", sa.Integer(), sa.ForeignKey("plan_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("warehouse_code", sa.String(32), nullable=False),
        sa.Column("override_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(256), nullable=True),
        sa.UniqueConstraint(
            "plan_run_id", "week_start", "sku", "warehouse_code",
            name="uq_demand_overrides_run_week_sku_wh",
        ),
    )
    op.create_index("ix_demand_overrides_plan_run_id", "demand_overrides_weekly", ["plan_run_id"])

    # --- planned_order_overrides_weekly ---
    op.create_table(
        "planned_order_overrides_weekly",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("plan_run_id", sa.Integer(), sa.ForeignKey("plan_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("warehouse_code", sa.String(32), nullable=False),
        sa.Column("override_order_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(256), nullable=True),
        sa.UniqueConstraint(
            "plan_run_id", "week_start", "sku", "warehouse_code",
            name="uq_planned_order_overrides_run_week_sku_wh",
        ),
    )
    op.create_index("ix_planned_order_overrides_plan_run_id", "planned_order_overrides_weekly", ["plan_run_id"])

    # --- plan_run_freeze_events ---
    op.create_table(
        "plan_run_freeze_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("plan_run_id", sa.Integer(), sa.ForeignKey("plan_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("frozen_by", sa.String(256), nullable=True),
        sa.Column("freeze_weeks", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_plan_run_freeze_events_plan_run_id", "plan_run_freeze_events", ["plan_run_id"])

    # --- planned_orders: add is_frozen ---
    op.add_column("planned_orders", sa.Column("is_frozen", sa.Boolean(), nullable=True))
    op.execute("UPDATE planned_orders SET is_frozen = false WHERE is_frozen IS NULL")
    op.alter_column("planned_orders", "is_frozen", nullable=False, server_default=sa.false())


def downgrade() -> None:
    op.drop_column("planned_orders", "is_frozen")
    op.drop_table("plan_run_freeze_events")
    op.drop_table("planned_order_overrides_weekly")
    op.drop_table("demand_overrides_weekly")
    op.drop_table("plan_run_demand_inputs_weekly")
    op.drop_column("plan_runs", "notes")
    op.drop_column("plan_runs", "created_by")
    op.drop_column("plan_runs", "freeze_weeks")
    op.drop_column("plan_runs", "demand_source")
