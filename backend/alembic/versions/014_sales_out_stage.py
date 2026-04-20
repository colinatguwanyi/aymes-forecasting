"""Sales Out ingestion: staging table, entity enum, ensure AAH warehouse.

Revision ID: 014
Revises: 013
Create Date: 2025-02-03

- sales_out_stage: staging for Sales Out CSV/XLSX (ingestion_run_id, aah_product_code, processed_date, invoiced_qty, etc.)
- ingestion_entity_enum: add 'sales_out'
- warehouses: ensure AAH exists (insert if not)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, name: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :t LIMIT 1"
    ), {"t": name})
    return result.scalar() is not None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN ALTER TYPE ingestion_entity_enum ADD VALUE 'sales_out'; EXCEPTION WHEN duplicate_object THEN null; END $$"
    )

    conn = op.get_bind()
    if not _table_exists(conn, "sales_out_stage"):
        op.create_table(
            "sales_out_stage",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("aah_product_code", sa.Text(), nullable=False),
            sa.Column("account_code", sa.Text(), nullable=True),
            sa.Column("customer_name", sa.Text(), nullable=True),
            sa.Column("postcode", sa.Text(), nullable=True),
            sa.Column("customer_sector", sa.Text(), nullable=True),
            sa.Column("pip_code", sa.Text(), nullable=True),
            sa.Column("product_name", sa.Text(), nullable=True),
            sa.Column("item_size", sa.Text(), nullable=True),
            sa.Column("invoiced_qty", sa.Numeric(18, 4), nullable=True),
            sa.Column("servings_qty", sa.Numeric(18, 4), nullable=True),
            sa.Column("net_sales_value", sa.Numeric(18, 4), nullable=True),
            sa.Column("processed_date", sa.Date(), nullable=False),
            sa.Column("processed_year", sa.Integer(), nullable=True),
            sa.Column("print_branch", sa.Text(), nullable=True),
            sa.Column("branch", sa.Text(), nullable=True),
            sa.Column("raw_json", postgresql.JSONB(), nullable=True),
        )
        op.create_index("ix_sales_out_stage_aah_product_code", "sales_out_stage", ["aah_product_code"])
        op.create_index("ix_sales_out_stage_processed_date", "sales_out_stage", ["processed_date"])
        op.create_index("ix_sales_out_stage_account_code", "sales_out_stage", ["account_code"])
        op.create_index("ix_sales_out_stage_ingestion_run_id", "sales_out_stage", ["ingestion_run_id"])

    # Ensure warehouse AAH exists
    r = conn.execute(sa.text("SELECT 1 FROM warehouses WHERE code = 'AAH' LIMIT 1"))
    if r.scalar() is None:
        conn.execute(sa.text(
            "INSERT INTO warehouses (code, name, timezone, active) VALUES ('AAH', 'AAH (national)', 'Europe/London', true)"
        ))


def downgrade() -> None:
    op.drop_table("sales_out_stage")
    # ingestion_entity_enum: no safe way to remove value in PostgreSQL
    # AAH warehouse: do not remove (may be in use)
