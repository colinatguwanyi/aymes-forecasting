"""Add warehouse site metadata columns (3PL, address, site type)."""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_warehouse_metadata"
down_revision: Union[str, None] = "002_rbac_roles_seed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("warehouses", sa.Column("is_own_site", sa.Boolean(), nullable=False, server_default=sa.text("1")))
    op.add_column("warehouses", sa.Column("operator_name", sa.String(256), nullable=True))
    op.add_column("warehouses", sa.Column("address", sa.Text(), nullable=True))
    op.add_column(
        "warehouses",
        sa.Column("site_type", sa.String(32), nullable=False, server_default="soh_warehouse"),
    )


def downgrade() -> None:
    op.drop_column("warehouses", "site_type")
    op.drop_column("warehouses", "address")
    op.drop_column("warehouses", "operator_name")
    op.drop_column("warehouses", "is_own_site")
