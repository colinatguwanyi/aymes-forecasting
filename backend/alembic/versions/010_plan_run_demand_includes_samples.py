"""Add demand_includes_samples to plan_run_demand_inputs_weekly (policy-driven audit).

Revision ID: 010
Revises: 009
Create Date: 2025-02-03

- plan_run_demand_inputs_weekly.demand_includes_samples BOOLEAN NOT NULL DEFAULT true
  (stored at resolve time from planning_policies.include_samples for audit/explainability)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plan_run_demand_inputs_weekly",
        sa.Column("demand_includes_samples", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("plan_run_demand_inputs_weekly", "demand_includes_samples")
