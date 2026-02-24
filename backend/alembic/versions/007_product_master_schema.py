"""Product master: extend products, add product_master_attributes and product_master_stage.

Revision ID: 007
Revises: 006
Create Date: 2025-02-03

- products: aah_code, brand, product_family, selling_unit_text, single_unit_content, content_uom, is_recipe
- product_master_attributes: logistics/cost (sku fk, shelf_life, hs_code, pallet, ti_hi, price, cogs, currency)
- product_master_stage: staging for ingestion (ingestion_run_id, row_number, payload JSONB)
- ingestion_entity_enum: add 'product_master'
"""
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, name: str) -> bool:
    return inspect(conn).has_table(name)


def _column_exists(conn, table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(conn).get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()
    # --- products: new columns (nullable or with default) ---
    if not _column_exists(conn, "products", "aah_code"):
        op.add_column("products", sa.Column("aah_code", sa.Text(), nullable=True))
    if not _column_exists(conn, "products", "brand"):
        op.add_column("products", sa.Column("brand", sa.Text(), nullable=True))
    if not _column_exists(conn, "products", "product_family"):
        op.add_column("products", sa.Column("product_family", sa.Text(), nullable=True))
    if not _column_exists(conn, "products", "selling_unit_text"):
        op.add_column("products", sa.Column("selling_unit_text", sa.Text(), nullable=True))
    if not _column_exists(conn, "products", "single_unit_content"):
        op.add_column("products", sa.Column("single_unit_content", sa.Numeric(18, 4), nullable=True))
    if not _column_exists(conn, "products", "content_uom"):
        op.add_column("products", sa.Column("content_uom", sa.String(16), nullable=True))
    if not _column_exists(conn, "products", "is_recipe"):
        op.add_column("products", sa.Column("is_recipe", sa.Boolean(), nullable=True))
        op.execute("UPDATE products SET is_recipe = false WHERE is_recipe IS NULL")
        op.alter_column("products", "is_recipe", nullable=False, server_default=sa.false())

    # --- product_master_attributes (one row per sku) ---
    if not _table_exists(conn, "product_master_attributes"):
        op.create_table(
            "product_master_attributes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("sku", sa.String(64), sa.ForeignKey("products.sku", ondelete="CASCADE"), nullable=False),
            sa.Column("shelf_life_text", sa.Text(), nullable=True),
            sa.Column("hs_code", sa.String(64), nullable=True),
            sa.Column("pallet_weight_kg", sa.Numeric(12, 4), nullable=True),
            sa.Column("pallet_dimensions_text", sa.Text(), nullable=True),
            sa.Column("ti_hi", sa.String(32), nullable=True),
            sa.Column("price_unit", sa.Numeric(18, 4), nullable=True),
            sa.Column("cogs_unit", sa.Numeric(18, 4), nullable=True),
            sa.Column("cogs_selling_unit", sa.Numeric(18, 4), nullable=True),
            sa.Column("currency", sa.String(8), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("sku", name="uq_product_master_attributes_sku"),
        )
        op.create_index("ix_product_master_attributes_sku", "product_master_attributes", ["sku"])

    # --- product_master_stage (for ingestion) ---
    if not _table_exists(conn, "product_master_stage"):
        op.create_table(
            "product_master_stage",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("row_number", sa.Integer(), nullable=False),
            sa.Column("payload", postgresql.JSONB(), nullable=False),
        )
        op.create_index("ix_product_master_stage_run_id", "product_master_stage", ["ingestion_run_id"])

    # --- ingestion_entity_enum: add product_master ---
    op.execute(
        "DO $$ BEGIN ALTER TYPE ingestion_entity_enum ADD VALUE 'product_master'; EXCEPTION WHEN duplicate_object THEN null; END $$"
    )


def downgrade() -> None:
    op.drop_table("product_master_stage")
    op.drop_table("product_master_attributes")
    op.drop_column("products", "is_recipe")
    op.drop_column("products", "content_uom")
    op.drop_column("products", "single_unit_content")
    op.drop_column("products", "selling_unit_text")
    op.drop_column("products", "product_family")
    op.drop_column("products", "brand")
    op.drop_column("products", "aah_code")
    # Cannot remove enum value in PG easily