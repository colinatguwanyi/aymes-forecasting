"""SOH ingestion: stock_on_hand_stage, inventory_snapshots_daily, branch mapping, weekly source_type.

Revision ID: 015
Revises: 014
Create Date: 2025-02-03

- stock_on_hand_stage: raw SOH rows (ingestion_run_id, stock_at_raw, branch_name_raw, aah_code_raw, stock_raw, on_order_raw, reject_reason)
- warehouse_branch_mapping: branch_name -> warehouse_code for SOH Branch Name resolution
- inventory_snapshots_daily: (warehouse_code, sku, as_of_date, source_type) + on_hand_units, on_order_units, source_run_id
- inventory_snapshots_weekly: add source_type (default 'legacy'), source_run_id; unique (week_start, sku, warehouse_code, source_type)
- ingestion_entity_enum: add 'stock_on_hand'
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, name: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :t LIMIT 1"
    ), {"t": name})
    return result.scalar() is not None


def _column_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c LIMIT 1"
    ), {"t": table, "c": column})
    return result.scalar() is not None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN ALTER TYPE ingestion_entity_enum ADD VALUE 'stock_on_hand'; EXCEPTION WHEN duplicate_object THEN null; END $$"
    )

    conn = op.get_bind()

    if not _table_exists(conn, "warehouse_branch_mapping"):
        op.create_table(
            "warehouse_branch_mapping",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("branch_name", sa.String(128), nullable=False),
            sa.Column("warehouse_code", sa.String(32), nullable=False),
        )
        op.create_index("ix_warehouse_branch_mapping_branch_name", "warehouse_branch_mapping", ["branch_name"], unique=True)
        op.create_index("ix_warehouse_branch_mapping_warehouse_code", "warehouse_branch_mapping", ["warehouse_code"])

    if not _table_exists(conn, "stock_on_hand_stage"):
        op.create_table(
            "stock_on_hand_stage",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("stock_at_raw", sa.Text(), nullable=True),
            sa.Column("branch_name_raw", sa.Text(), nullable=True),
            sa.Column("aah_code_raw", sa.Text(), nullable=True),
            sa.Column("stock_raw", sa.Text(), nullable=True),
            sa.Column("on_order_raw", sa.Text(), nullable=True),
            sa.Column("description_raw", sa.Text(), nullable=True),
            sa.Column("reject_reason", sa.Text(), nullable=True),
            sa.Column("row_hash", sa.String(64), nullable=True),
        )
        op.create_index("ix_stock_on_hand_stage_ingestion_run_id", "stock_on_hand_stage", ["ingestion_run_id"])
        op.create_index("ix_stock_on_hand_stage_branch_name_raw", "stock_on_hand_stage", ["branch_name_raw"])

    if not _table_exists(conn, "inventory_snapshots_daily"):
        op.create_table(
            "inventory_snapshots_daily",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("warehouse_code", sa.String(32), nullable=False),
            sa.Column("sku", sa.String(64), nullable=False),
            sa.Column("as_of_date", sa.Date(), nullable=False),
            sa.Column("on_hand_units", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("on_order_units", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("source_type", sa.String(32), nullable=False),
            sa.Column("source_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_runs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.UniqueConstraint("warehouse_code", "sku", "as_of_date", "source_type", name="uq_inv_daily_wh_sku_date_source"),
        )
        op.create_index("ix_inventory_snapshots_daily_wh_sku_date", "inventory_snapshots_daily", ["warehouse_code", "sku", "as_of_date"])
        op.create_index("ix_inventory_snapshots_daily_source_run_id", "inventory_snapshots_daily", ["source_run_id"])

    # inventory_snapshots_weekly: add source_type, source_run_id; new unique
    if not _column_exists(conn, "inventory_snapshots_weekly", "source_type"):
        op.add_column("inventory_snapshots_weekly", sa.Column("source_type", sa.String(32), nullable=True))
        op.execute("UPDATE inventory_snapshots_weekly SET source_type = 'legacy' WHERE source_type IS NULL")
        op.alter_column("inventory_snapshots_weekly", "source_type", nullable=False, server_default="legacy")
    if not _column_exists(conn, "inventory_snapshots_weekly", "source_run_id"):
        op.add_column("inventory_snapshots_weekly", sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            "fk_inventory_snapshots_weekly_source_run",
            "inventory_snapshots_weekly", "ingestion_runs",
            ["source_run_id"], ["id"], ondelete="SET NULL"
        )
    # Replace unique constraint: drop old, add (week_start, sku, warehouse_code, source_type)
    try:
        op.drop_constraint("uq_inv_week_sku_wh", "inventory_snapshots_weekly", type_="unique")
    except Exception:
        pass
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_inv_week_sku_wh_source ON inventory_snapshots_weekly (week_start, sku, warehouse_code, COALESCE(source_type, 'legacy'))"
    )


def downgrade() -> None:
    conn = op.get_bind()
    op.drop_index("uq_inv_week_sku_wh_source", table_name="inventory_snapshots_weekly", if_exists=True)
    op.create_unique_constraint("uq_inv_week_sku_wh", "inventory_snapshots_weekly", ["week_start", "sku", "warehouse_code"])
    if _column_exists(conn, "inventory_snapshots_weekly", "source_run_id"):
        op.drop_constraint("fk_inventory_snapshots_weekly_source_run", "inventory_snapshots_weekly", type_="foreignkey")
        op.drop_column("inventory_snapshots_weekly", "source_run_id")
    if _column_exists(conn, "inventory_snapshots_weekly", "source_type"):
        op.drop_column("inventory_snapshots_weekly", "source_type")
    op.drop_table("inventory_snapshots_daily")
    op.drop_table("stock_on_hand_stage")
    op.drop_table("warehouse_branch_mapping")
    # ingestion_entity_enum: no safe way to remove value
