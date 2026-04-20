"""MySQL 8 baseline: create full platform schema from ORM metadata.

Replaces the previous PostgreSQL-specific revision chain. Fresh databases should
use DATABASE_URL=mysql+pymysql://... and run ``alembic upgrade head``.

Downgrade drops all tables registered on Base.metadata (destructive).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "001_mysql_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Register all mapped tables on shared Base.metadata
    import app.models  # noqa: F401
    import app.forecast_models  # noqa: F401

    from app.database import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    import app.models  # noqa: F401
    import app.forecast_models  # noqa: F401

    from app.database import Base

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
