"""Planning correctness: unique constraints receipts/demand, projected_inventory columns, include_samples

Revision ID: 002
Revises: 001
Create Date: 2025-02-03

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # receipts: unique (week_start, sku, warehouse_code, source_type); COALESCE so NULL source_type is one key
    op.execute(
        "CREATE UNIQUE INDEX uq_receipts_week_sku_wh_source ON receipts (week_start, sku, warehouse_code, COALESCE(source_type, ''))"
    )

    # demand_actuals: unique (week_start, sku, warehouse_code, demand_type)
    op.create_unique_constraint(
        "uq_demand_actuals_week_sku_wh_type",
        "demand_actuals",
        ["week_start", "sku", "warehouse_code", "demand_type"],
    )

    # planning_policies: include_samples
    op.add_column("planning_policies", sa.Column("include_samples", sa.Boolean(), nullable=True))
    op.execute("UPDATE planning_policies SET include_samples = true WHERE include_samples IS NULL")
    op.alter_column("planning_policies", "include_samples", nullable=False, server_default=sa.true())

    # projected_inventory: start_qty, receipts_qty, demand_qty; keep projected_qty as end_qty
    op.add_column("projected_inventory", sa.Column("start_qty", sa.Numeric(18, 4), nullable=True))
    op.add_column("projected_inventory", sa.Column("receipts_qty", sa.Numeric(18, 4), nullable=True))
    op.add_column("projected_inventory", sa.Column("demand_qty", sa.Numeric(18, 4), nullable=True))
    op.execute("UPDATE projected_inventory SET start_qty = 0, receipts_qty = 0, demand_qty = 0 WHERE start_qty IS NULL")
    op.alter_column("projected_inventory", "start_qty", nullable=False, server_default="0")
    op.alter_column("projected_inventory", "receipts_qty", nullable=False, server_default="0")
    op.alter_column("projected_inventory", "demand_qty", nullable=False, server_default="0")


def downgrade() -> None:
    op.drop_column("projected_inventory", "demand_qty")
    op.drop_column("projected_inventory", "receipts_qty")
    op.drop_column("projected_inventory", "start_qty")
    op.drop_column("planning_policies", "include_samples")
    op.drop_constraint("uq_demand_actuals_week_sku_wh_type", "demand_actuals", type_="unique")
    op.drop_index("uq_receipts_week_sku_wh_source", table_name="receipts")
