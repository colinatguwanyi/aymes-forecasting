"""Ingestion mode: weekly vs historical, date_min/max, requires_confirm, progress_meta.

Revision ID: 016
Revises: 015
Create Date: 2025-02-24

- ingestion_runs: mode (weekly/historical), date_min, date_max, file_size_bytes,
  requires_confirm, confirmed_at, confirmed_by, progress_meta
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c LIMIT 1"
    ), {"t": table, "c": column})
    return result.scalar() is not None


def upgrade() -> None:
    conn = op.get_bind()
    op.execute(
        "DO $$ BEGIN CREATE TYPE ingestion_mode_enum AS ENUM ('weekly', 'historical'); EXCEPTION WHEN duplicate_object THEN null; END $$"
    )
    if not _column_exists(conn, "ingestion_runs", "mode"):
        mode_enum = postgresql.ENUM("weekly", "historical", name="ingestion_mode_enum", create_type=False)
        op.add_column("ingestion_runs", sa.Column("mode", mode_enum, nullable=True))
        op.execute("UPDATE ingestion_runs SET mode = 'weekly' WHERE mode IS NULL")
        op.alter_column("ingestion_runs", "mode", nullable=False, server_default=sa.text("'weekly'::ingestion_mode_enum"))
    if not _column_exists(conn, "ingestion_runs", "date_min"):
        op.add_column("ingestion_runs", sa.Column("date_min", sa.Date(), nullable=True))
    if not _column_exists(conn, "ingestion_runs", "date_max"):
        op.add_column("ingestion_runs", sa.Column("date_max", sa.Date(), nullable=True))
    if not _column_exists(conn, "ingestion_runs", "file_size_bytes"):
        op.add_column("ingestion_runs", sa.Column("file_size_bytes", sa.Integer(), nullable=True))
    if not _column_exists(conn, "ingestion_runs", "requires_confirm"):
        op.add_column("ingestion_runs", sa.Column("requires_confirm", sa.Boolean(), nullable=True))
        op.execute("UPDATE ingestion_runs SET requires_confirm = false WHERE requires_confirm IS NULL")
        op.alter_column("ingestion_runs", "requires_confirm", nullable=False, server_default="false")
    if not _column_exists(conn, "ingestion_runs", "confirmed_at"):
        op.add_column("ingestion_runs", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
    if not _column_exists(conn, "ingestion_runs", "confirmed_by"):
        op.add_column("ingestion_runs", sa.Column("confirmed_by", sa.String(256), nullable=True))
    if not _column_exists(conn, "ingestion_runs", "progress_meta"):
        op.add_column("ingestion_runs", sa.Column("progress_meta", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    for col in ("progress_meta", "confirmed_by", "confirmed_at", "requires_confirm", "file_size_bytes", "date_max", "date_min", "mode"):
        if _column_exists(conn, "ingestion_runs", col):
            op.drop_column("ingestion_runs", col)
    op.execute("DROP TYPE IF EXISTS ingestion_mode_enum")
