"""Add eval_weeks to forecast_run_metrics (number of weeks used for WAPE/Bias scoring).

Revision ID: 009
Revises: 008
Create Date: 2025-02-03

- forecast_run_metrics.eval_weeks (integer, nullable for backward compat)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "forecast_run_metrics",
        sa.Column("eval_weeks", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("forecast_run_metrics", "eval_weeks")
