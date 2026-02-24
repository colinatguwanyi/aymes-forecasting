"""Forecast method acknowledgements: governance sign-off table.

Revision ID: 017
Revises: 016
Create Date: 2026-02-24

- forecast_method_acknowledgements: id, created_by, method_version, method_hash,
  acknowledged_at, notes
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "forecast_method_acknowledgements",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_by", sa.String(256), nullable=False),
        sa.Column("method_version", sa.String(64), nullable=False),
        sa.Column("method_hash", sa.String(64), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_forecast_method_ack_method_version", "forecast_method_acknowledgements", ["method_version"])
    op.create_index("ix_forecast_method_ack_acknowledged_at", "forecast_method_acknowledgements", ["acknowledged_at"])


def downgrade() -> None:
    op.drop_index("ix_forecast_method_ack_acknowledged_at", table_name="forecast_method_acknowledgements")
    op.drop_index("ix_forecast_method_ack_method_version", table_name="forecast_method_acknowledgements")
    op.drop_table("forecast_method_acknowledgements")
