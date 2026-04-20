"""Add warehouse_product_codes table for persistent external code → sku mapping.

Revision ID: 020
Revises: 019
Create Date: 2026-02-24

- warehouse_product_codes: warehouse_code, external_code, sku, external_name, hs_code, active, match_method, match_confidence, created_at, updated_at
- UNIQUE(warehouse_code, external_code)
"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "warehouse_product_codes" in inspector.get_table_names():
        return  # Table already exists (e.g. from Base.metadata.create_all)
    op.create_table(
        "warehouse_product_codes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("warehouse_code", sa.String(32), nullable=False),
        sa.Column("external_code", sa.String(128), nullable=False),
        sa.Column("sku", sa.String(64), sa.ForeignKey("products.sku", ondelete="CASCADE"), nullable=False),
        sa.Column("external_name", sa.Text(), nullable=True),
        sa.Column("hs_code", sa.String(64), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("match_method", sa.String(32), nullable=True),
        sa.Column("match_confidence", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("warehouse_code", "external_code", name="uq_warehouse_product_codes_wh_ext"),
    )
    op.create_index("ix_warehouse_product_codes_warehouse_code", "warehouse_product_codes", ["warehouse_code"])
    op.create_index("ix_warehouse_product_codes_sku", "warehouse_product_codes", ["sku"])
    op.create_index("ix_warehouse_product_codes_external_code", "warehouse_product_codes", ["external_code"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "warehouse_product_codes" in inspector.get_table_names():
        op.drop_table("warehouse_product_codes")
