"""Seed standard RBAC role names (create_all does not insert rows).

Idempotent: skips if roles table is non-empty so re-runs are safe.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "002_rbac_roles_seed"
down_revision: Union[str, None] = "001_mysql_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Must match app.security.auth.VALID_ROLES / ROLE_* constants.
_STANDARD_RBAC_ROLES = ("Admin", "Planner", "Viewer", "Operator")


def upgrade() -> None:
    conn = op.get_bind()
    count = conn.execute(text("SELECT COUNT(*) FROM roles")).scalar()
    if count is not None and int(count) > 0:
        return
    for name in _STANDARD_RBAC_ROLES:
        conn.execute(text("INSERT INTO roles (name) VALUES (:name)"), {"name": name})


def downgrade() -> None:
    pass
