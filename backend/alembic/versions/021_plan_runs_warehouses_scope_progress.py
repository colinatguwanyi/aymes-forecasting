"""Add plan_runs.warehouses_scope and progress_meta for warehouse-scoped planning.

Revision ID: 021
Revises: 020
Create Date: 2026-02-24

- warehouses_scope JSONB NULL: list of warehouse codes to plan (e.g. ["AAH"], ["BLP"], ["AAH","BLP"])
  NULL = legacy: use all warehouses present in planning_policies
- progress_meta JSONB NULL: run summary (warehouses_planned, warehouses_skipped, projected_inventory_rows_written, etc.)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plan_runs",
        sa.Column("warehouses_scope", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "plan_runs",
        sa.Column("progress_meta", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plan_runs", "progress_meta")
    op.drop_column("plan_runs", "warehouses_scope")
