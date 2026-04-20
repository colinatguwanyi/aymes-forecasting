"""Add app_settings table for key-value config (e.g. sample_sales_soh_warehouses).

Revision ID: 019
Revises: 018
Create Date: 2026-02-24

- app_settings: key (pk), value (JSONB)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, name: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :t"
    ), {"t": name})
    return result.scalar() is not None


def upgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "app_settings"):
        op.create_table(
            "app_settings",
            sa.Column("key", sa.String(128), primary_key=True),
            sa.Column("value", postgresql.JSONB(), nullable=False),
        )
    op.execute(
        sa.text(
            "INSERT INTO app_settings (key, value) VALUES ('sample_sales_soh_warehouses', '[\"BLP\"]'::jsonb) ON CONFLICT (key) DO NOTHING"
        )
    )


def downgrade() -> None:
    op.drop_table("app_settings")
