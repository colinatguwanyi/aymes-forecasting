"""Add plan_runs.selected_train_end_week_start for default baseline run selection.

Revision ID: 012
Revises: 011
Create Date: 2025-02-03

- plan_runs.selected_train_end_week_start DATE NULL: set on first baseline resolve to chosen
  MAX(train_end_week_start) for reproducibility; not a user input.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plan_runs",
        sa.Column("selected_train_end_week_start", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plan_runs", "selected_train_end_week_start")
