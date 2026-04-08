"""
MySQL source reader: reads raw daily sales from aymes_reports.adhl_data_daily
and returns W-TUE weekly aggregates ready to upsert into forecast_sales_weekly.

Connection settings come entirely from environment variables (via app.config.settings)
— no credentials appear in code.

Requires: pip install pymysql (or mysqlclient).  pymysql is preferred for
pure-Python environments; the connection string uses the +pymysql dialect.

If MySQL is unreachable (e.g. running tests offline) every public method raises
MySQLUnavailableError with a clear message rather than letting a generic
OperationalError propagate.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.services.time_bucketing import week_start_for_date

logger = logging.getLogger(__name__)


class MySQLUnavailableError(RuntimeError):
    """Raised when the MySQL source database cannot be reached."""


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _build_mysql_url() -> str:
    """Build the SQLAlchemy connection URL from settings (no hard-coded values)."""
    host = settings.mysql_host
    port = settings.mysql_port
    user = settings.mysql_user
    password = settings.mysql_password
    database = settings.mysql_database
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"


def _get_engine() -> Engine:
    url = _build_mysql_url()
    return create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=0)


# ---------------------------------------------------------------------------
# MySQLSalesReader
# ---------------------------------------------------------------------------

class MySQLSalesReader:
    """
    Reads from aymes_reports.adhl_data_daily and aggregates to W-TUE weekly buckets.

    Expected columns in adhl_data_daily (based on Vertex legacy logic):
        - trans_date   DATE           sale/shipment date
        - product_code VARCHAR        maps to platform SKU (via sku_code_map if needed)
        - warehouse    VARCHAR        maps to platform warehouse_code
        - qty          NUMERIC        units sold / shipped
        - demand_type  VARCHAR NULL   'CUSTOMER' or 'SAMPLES'; NULL treated as 'CUSTOMER'

    If the column layout of adhl_data_daily differs, adjust _ROW_QUERY below and
    document the mapping assumption.

    Assumption: product_code in adhl_data_daily is already the canonical SKU used
    in the Postgres products table.  If a sku_code_map lookup is required, apply
    it in the calling service before persisting to forecast_sales_weekly.
    """

    # SELECT used to pull the raw daily data.  Parameters: :from_date, :to_date.
    _ROW_QUERY = """
        SELECT
            trans_date,
            product_code,
            warehouse      AS warehouse_code,
            COALESCE(demand_type, 'CUSTOMER') AS demand_type,
            SUM(qty)       AS daily_qty,
            COUNT(*)       AS row_count
        FROM adhl_data_daily
        WHERE trans_date >= :from_date
          AND trans_date <= :to_date
          AND qty > 0
        GROUP BY
            trans_date,
            product_code,
            warehouse,
            COALESCE(demand_type, 'CUSTOMER')
        ORDER BY trans_date
    """

    def __init__(self) -> None:
        self._engine: Engine | None = None

    def _engine_or_raise(self) -> Engine:
        if self._engine is None:
            self._engine = _get_engine()
        return self._engine

    def ping(self) -> bool:
        """Return True if MySQL is reachable; False otherwise (never raises)."""
        try:
            with self._engine_or_raise().connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.warning("MySQL ping failed: %s", exc)
            return False

    def read_weekly(
        self,
        from_date: date,
        to_date: date,
    ) -> list[dict[str, Any]]:
        """
        Pull daily rows from adhl_data_daily in [from_date, to_date], aggregate
        to W-TUE weekly buckets, and return a list of dicts with keys:

            sku, warehouse_code, week_start (date), demand_type (str),
            qty (Decimal), source_row_count (int)

        The caller is responsible for upserting the results into
        forecast_sales_weekly with the appropriate source_config_id.

        Raises MySQLUnavailableError if the database cannot be reached.
        """
        try:
            engine = self._engine_or_raise()
            with engine.connect() as conn:
                rows = conn.execute(
                    text(self._ROW_QUERY),
                    {"from_date": from_date, "to_date": to_date},
                ).fetchall()
        except OperationalError as exc:
            raise MySQLUnavailableError(
                f"Cannot connect to MySQL at {settings.mysql_host}:{settings.mysql_port}. "
                f"Check MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD env vars. "
                f"Detail: {exc}"
            ) from exc

        # Aggregate daily rows → weekly buckets keyed by (sku, wh, week_start, demand_type)
        buckets: dict[tuple[str, str, date, str], dict[str, Any]] = {}
        for row in rows:
            trans_date: date = row.trans_date if isinstance(row.trans_date, date) else row.trans_date
            ws: date = week_start_for_date(trans_date)
            sku: str = str(row.product_code).strip()
            wh: str = str(row.warehouse_code).strip().upper()
            dtype: str = str(row.demand_type).strip().upper()
            qty = Decimal(str(row.daily_qty))
            src_rows: int = int(row.row_count)

            key = (sku, wh, ws, dtype)
            if key in buckets:
                buckets[key]["qty"] += qty
                buckets[key]["source_row_count"] += src_rows
            else:
                buckets[key] = {
                    "sku": sku,
                    "warehouse_code": wh,
                    "week_start": ws,
                    "demand_type": dtype,
                    "qty": qty,
                    "source_row_count": src_rows,
                }

        result = list(buckets.values())
        logger.info(
            "MySQLSalesReader: read %d daily rows → %d weekly buckets (from=%s to=%s)",
            len(rows),
            len(result),
            from_date,
            to_date,
        )
        return result

    def read_trailing_weeks(self, weeks: int = 104) -> list[dict[str, Any]]:
        """
        Convenience wrapper: read the last N weeks of data ending today.
        W-TUE bucketing is applied automatically.
        """
        today = date.today()
        to_date = today
        from_date = today - timedelta(days=weeks * 7)
        return self.read_weekly(from_date, to_date)
