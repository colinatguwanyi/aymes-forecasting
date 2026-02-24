"""Add optional non-unique index on products.aah_code (reference field only; never used as join key).

Revision ID: 008
Revises: 007
Create Date: 2025-02-03

- products.aah_code: non-unique index for lookups only. aah_code is NOT a key; duplicate AAH across SKUs allowed.
"""
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
from typing import Sequence, Union
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_products_aah_code ON products (aah_code)")


def downgrade() -> None:
    op.drop_index("ix_products_aah_code", table_name="products")
