"""Add RBAC tables: users, roles, user_roles.

Revision ID: 018
Revises: 017
Create Date: 2026-02-24

- users: id (uuid pk), entra_oid (unique, nullable), email, display_name,
  is_active, created_at, last_login_at
- roles: id (pk), name (unique) [Admin, Planner, Viewer, Operator]
- user_roles: user_id, role_id (unique composite)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, name: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :t"
    ), {"t": name})
    return result.scalar() is not None


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(conn, "roles"):
        op.create_table(
            "roles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(64), nullable=False),
        )
        op.create_index("ix_roles_name", "roles", ["name"], unique=True)

    # Seed roles (idempotent: only insert if missing)
    for role in ("Admin", "Planner", "Viewer", "Operator"):
        r = conn.execute(sa.text("SELECT 1 FROM roles WHERE name = :n"), {"n": role})
        if r.scalar() is None:
            conn.execute(sa.text("INSERT INTO roles (name) VALUES (:n)"), {"n": role})

    if not _table_exists(conn, "users"):
        op.create_table(
            "users",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("entra_oid", sa.String(256), nullable=True),
            sa.Column("email", sa.String(256), nullable=False),
            sa.Column("display_name", sa.String(256), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_users_entra_oid", "users", ["entra_oid"], unique=True)
        op.create_index("ix_users_email", "users", ["email"])

    if not _table_exists(conn, "user_roles"):
        op.create_table(
            "user_roles",
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
            sa.PrimaryKeyConstraint("user_id", "role_id"),
        )
        op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
        op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])


def downgrade() -> None:
    op.drop_table("user_roles")
    op.drop_table("users")
    op.drop_table("roles")
