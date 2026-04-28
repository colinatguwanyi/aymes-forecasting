"""
MySQL forecast database session factory.

All forecast tables (forecast_runs, forecast_results_weekly, etc.) live in a
MySQL database.  This module provides the engine and the FastAPI dependency
``get_forecast_db``.

The forecast engine MySQL connection is built from the same URL as
``DATABASE_URL`` (host, port, user, password, query params) with the database
name taken from ``MYSQL_FORECAST_DATABASE`` when set; **when unset**, the
database name in ``DATABASE_URL`` is reused (e.g. ``supply_planning``) so one
set of user privileges is enough for local dev.  Optional separate
``aymes_forecasting`` database: set ``MYSQL_FORECAST_DATABASE=aymes_forecasting`` and
``GRANT`` the user on that database.

If ``DATABASE_URL`` is not a MySQL URL, the code falls back to
``MYSQL_HOST`` / ``MYSQL_PORT`` / ``MYSQL_USER`` / ``MYSQL_PASSWORD`` and
``MYSQL_FORECAST_DATABASE``.
"""
from __future__ import annotations

import logging
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


def _resolve_forecast_database_name() -> str:
    """
    Return the schema/database that holds app.forecast_mysql_models tables.

    If ``MYSQL_FORECAST_DATABASE`` is set, use it. Otherwise use the same
    database as ``DATABASE_URL`` (platform DB), or fall back to ``aymes_forecasting``.
    """
    from sqlalchemy.engine.url import make_url

    from app.config import settings

    override = (getattr(settings, "mysql_forecast_database", None) or "").strip()
    if override:
        return override
    try:
        u = make_url(settings.database_url)
        if u.database:
            return str(u.database)
    except Exception as exc:
        logger.debug("Could not read database from DATABASE_URL: %s", exc)
    return "aymes_forecasting"


@lru_cache(maxsize=1)
def _build_engine() -> Engine:
    from sqlalchemy.engine.url import make_url

    from app.config import settings

    db_name = _resolve_forecast_database_name()
    connect_args: dict[str, object] = {"connect_timeout": 3600}
    if settings.database_ssl_disabled:
        connect_args["ssl_disabled"] = True

    use_url: object = None
    try:
        parsed = make_url(settings.database_url)
    except Exception as exc:
        logger.warning("Could not parse DATABASE_URL; using MYSQL_* for forecast: %s", exc)
        parsed = None

    if parsed is not None and "mysql" in (parsed.drivername or "").lower():
        use_url = parsed.set(database=db_name)
        logger.info(
            "MySQL forecast engine (from DATABASE_URL): %s:%s/%s",
            use_url.host,
            use_url.port,
            db_name,
        )
    else:
        use_url = (
            f"mysql+pymysql://{settings.mysql_user}:{settings.mysql_password}"
            f"@{settings.mysql_host}:{settings.mysql_port}/{db_name}"
            "?charset=utf8mb4"
        )
        logger.info(
            "MySQL forecast engine (from MYSQL_*): %s:%s/%s",
            settings.mysql_host,
            settings.mysql_port,
            db_name,
        )
    return create_engine(
        use_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
        pool_timeout=3600,
    )


def get_forecast_engine() -> Engine:
    """Return the shared MySQL forecast engine (singleton)."""
    return _build_engine()


def get_forecast_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a MySQL session bound to the forecast database.

    Usage in a router:
        forecast_db: Session = Depends(get_forecast_db)
    """
    engine = get_forecast_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_forecast_schema() -> None:
    """
    Create all MySQL forecast tables from the ORM metadata.

    Call once at application startup (or from a CLI migration tool).
    Does not touch Postgres.
    """
    from app.forecast_mysql_models import MySQLForecastBase
    engine = get_forecast_engine()
    MySQLForecastBase.metadata.create_all(engine)
    logger.info("MySQL forecast schema initialised (create_all).")
