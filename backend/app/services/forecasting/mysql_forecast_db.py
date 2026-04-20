"""
MySQL forecast database session factory.

All forecast tables (forecast_runs, forecast_results_weekly, etc.) live in a
dedicated MySQL database (default: aymes_forecasting).  This module provides
the SQLAlchemy engine and the FastAPI dependency used to inject a MySQL session
into routers and services.

Configuration (via .env / environment variables):
    MYSQL_HOST          — MySQL server host  (default: localhost)
    MYSQL_PORT          — MySQL server port  (default: 3306)
    MYSQL_USER          — MySQL username
    MYSQL_PASSWORD      — MySQL password
    MYSQL_FORECAST_DATABASE — database that holds forecast tables
                              (default: aymes_forecasting)

The MySQL credentials are shared with the existing sales-source connection
(they are assumed to run on the same server).  Only the database name differs.
"""
from __future__ import annotations

import logging
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _build_engine() -> Engine:
    from app.config import settings

    db_name = getattr(settings, "mysql_forecast_database", "aymes_forecasting")
    url = (
        f"mysql+pymysql://{settings.mysql_user}:{settings.mysql_password}"
        f"@{settings.mysql_host}:{settings.mysql_port}/{db_name}"
        "?charset=utf8mb4"
    )
    engine = create_engine(
        url,
        connect_args={"connect_timeout": 3600},
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
        pool_timeout=3600,
    )
    logger.info("MySQL forecast engine created: %s:%d/%s", settings.mysql_host, settings.mysql_port, db_name)
    return engine


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
