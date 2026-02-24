"""Add plan_run_events for audit (e.g. RESET_FORECAST_RUN).

Revision ID: 013
Revises: 012
Create Date: 2025-02-03

- plan_run_events: plan_run_id, event_type, created_at, created_by, details_json
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plan_run_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("plan_run_id", sa.Integer(), sa.ForeignKey("plan_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(256), nullable=True),
        sa.Column("details_json", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_plan_run_events_plan_run_id", "plan_run_events", ["plan_run_id"])
    op.create_index("ix_plan_run_events_event_type", "plan_run_events", ["event_type"])


def downgrade() -> None:
    op.drop_table("plan_run_events")
