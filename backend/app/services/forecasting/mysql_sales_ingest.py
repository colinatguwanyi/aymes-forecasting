"""
MySQL sales ingest service — Vertex pipeline field mapping.

Reads aymes_reports.adhl_data_daily using the exact field names from the
extracted Vertex pipeline:
    Business_Processed_Date → W-TUE week_start
    AAH_Product_Code        → product_code
    Invoiced_Qty            → units_sold (summed per week)
    Product_Name            → product_name
    Item_Size               → item_size
    PIP_Code                → pip_code

Connection:
  - SOURCE (read):  user/password (and default host/port) from ``DATABASE_URL`` so they
                    match the working platform DB login; ``mysql_database`` and optional
                    host/port overrides come from ForecastSourceConfig.
  - **Canonical weekly facts** — if ``mysql_database`` matches ``DATABASE_URL``'s database
    and ``mysql_sales_table`` is ``demand_facts_weekly``, ingest reads
    ``DemandType.CUSTOMER`` rows from the **platform** session (``pg_db``), same data as
    the Sales Grid — no ``aymes_reports`` / ``adhl_data_daily`` required.
  - FORECAST (write): passed in as forecast_db (MySQL aymes_forecasting session).
  - PLATFORM (read):  pg_db — active products, or full ``demand_facts_weekly`` when using
    the path above.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import text
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import settings
from app.forecast_mysql_models import ForecastSalesWeekly, ForecastSourceConfig
from app.models import DemandFactsWeekly, DemandType, Product
from app.services.time_bucketing import week_start_for_date

logger = logging.getLogger(__name__)


def _int(v: Any) -> int:
    return int(str(v))


class MySQLUnavailableError(RuntimeError):
    """Raised when the MySQL source database cannot be reached."""


_QUERY_WITH_WAREHOUSE = """
    SELECT
        Business_Processed_Date          AS trans_date,
        AAH_Product_Code                 AS product_code,
        Product_Name                     AS product_name,
        Item_Size                        AS item_size,
        PIP_Code                         AS pip_code,
        warehouse                        AS warehouse_col,
        SUM(Invoiced_Qty)                AS weekly_qty,
        COUNT(*)                         AS row_count
    FROM {table}
    WHERE Business_Processed_Date >= :from_date
      AND Business_Processed_Date <= :to_date
      AND Invoiced_Qty > 0
      AND AAH_Product_Code IS NOT NULL
      AND AAH_Product_Code <> ''
    GROUP BY
        Business_Processed_Date,
        AAH_Product_Code,
        Product_Name,
        Item_Size,
        PIP_Code,
        warehouse
    ORDER BY Business_Processed_Date
"""

_QUERY_NO_WAREHOUSE = """
    SELECT
        Business_Processed_Date          AS trans_date,
        AAH_Product_Code                 AS product_code,
        Product_Name                     AS product_name,
        Item_Size                        AS item_size,
        PIP_Code                         AS pip_code,
        SUM(Invoiced_Qty)                AS weekly_qty,
        COUNT(*)                         AS row_count
    FROM {table}
    WHERE Business_Processed_Date >= :from_date
      AND Business_Processed_Date <= :to_date
      AND Invoiced_Qty > 0
      AND AAH_Product_Code IS NOT NULL
      AND AAH_Product_Code <> ''
    GROUP BY
        Business_Processed_Date,
        AAH_Product_Code,
        Product_Name,
        Item_Size,
        PIP_Code
    ORDER BY Business_Processed_Date
"""


def _base_user_pass_host_port_from_settings() -> tuple[str, str, str, int]:
    """
    Prefer user/password/host/port from ``DATABASE_URL`` so ingest uses the same
    successful login as the rest of the app. ``MYSQL_USER``/``MYSQL_PASSWORD`` can
    otherwise drift and cause 1045 on ``aymes_reports`` while ``supply_planning`` works.
    """
    from sqlalchemy.engine.url import make_url

    try:
        u = make_url(settings.database_url)
    except Exception as exc:  # pragma: no cover
        logger.debug("parse DATABASE_URL for ingest: %s", exc)
        u = None
    if u is None or "mysql" not in (u.drivername or "").lower():
        return (
            str(settings.mysql_user),
            str(settings.mysql_password or ""),
            str(settings.mysql_host),
            int(settings.mysql_port),
        )
    user = (u.username or str(settings.mysql_user)) or ""
    pwd = str(u.password) if u.password is not None else str(settings.mysql_password or "")
    host = (u.host or str(settings.mysql_host)) or "localhost"
    prt = int(u.port) if u.port is not None else int(settings.mysql_port)
    return (user, pwd, str(host), prt)


def _ingest_source_connection(
    source: ForecastSourceConfig,
) -> tuple[str, str, str, int, str]:
    """
    (user, password, host, port, database) for the sales read connection.
    Source config may override host/port only; user/password follow DATABASE_URL.
    """
    bu, bp, def_host, def_port = _base_user_pass_host_port_from_settings()
    raw_h = getattr(source, "mysql_host", None)
    if raw_h is not None and str(raw_h).strip() != "":
        eff_host = str(raw_h).strip()
    else:
        eff_host = def_host
    raw_p = getattr(source, "mysql_port", None)
    if raw_p is not None and str(raw_p).strip() != "":
        try:
            eff_port = int(str(raw_p).strip())
        except ValueError:
            eff_port = def_port
    else:
        eff_port = def_port
    return (bu, bp, eff_host, eff_port, str(source.mysql_database))


def _platform_database_name() -> str | None:
    from sqlalchemy.engine.url import make_url

    try:
        u = make_url(settings.database_url)
    except Exception:
        return None
    return u.database


def _ingest_source_host_matches_platform(source: ForecastSourceConfig) -> bool:
    """If source overrides host, require it to match (or be loopback-same) as DATABASE_URL."""
    from sqlalchemy.engine.url import make_url

    raw = getattr(source, "mysql_host", None)
    if raw is None or str(raw).strip() == "":
        return True
    try:
        u = make_url(settings.database_url)
    except Exception:
        return True
    h_src = str(raw).strip().lower()
    h_def = (u.host or "localhost").strip().lower()
    loop = frozenset({"localhost", "127.0.0.1", "::1"})
    if h_src == h_def or (h_src in loop and h_def in loop):
        return True
    return False


def _uses_platform_demand_facts_table(source: ForecastSourceConfig) -> bool:
    plat = _platform_database_name()
    if not plat:
        return False
    dbn = str(getattr(source, "mysql_database", None) or "").lower()
    if dbn != str(plat).lower():
        return False
    tbl = str(getattr(source, "mysql_sales_table", None) or "").lower()
    if tbl != "demand_facts_weekly":
        return False
    return _ingest_source_host_matches_platform(source)


class MySQLSalesIngestService:
    """
    Extracts sales from a MySQL source (legacy ``adhl_data_daily`` or canonical
    ``demand_facts_weekly``), aggregates to W-TUE weekly buckets when needed,
    filters inactive products, and upserts into forecast_sales_weekly.
    """

    def __init__(self, default_warehouse: str = "AAH") -> None:
        self._default_warehouse = default_warehouse.upper()
        self._engine: Engine | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest(
        self,
        pg_db: Session,
        forecast_db: Session,
        source_config: ForecastSourceConfig,
        from_date: date,
        to_date: date,
    ) -> dict[str, int]:
        """
        Full ingest cycle: extract → aggregate → filter → upsert.

        pg_db       — Platform DB session (MySQL): active products, or
                     ``demand_facts_weekly`` when the source is configured for it.
        forecast_db — MySQL forecast session (write forecast_sales_weekly).

        Returns dict with: rows_extracted, rows_after_filter, rows_upserted.
        """
        if _uses_platform_demand_facts_table(source_config):
            raw_rows = self._extract_from_demand_facts_weekly(
                pg_db, from_date, to_date
            )
            logger.info(
                "Extracted %d rows from platform demand_facts_weekly (CUSTOMER) "
                "(%s to %s)",
                len(raw_rows),
                from_date,
                to_date,
            )
        else:
            table_fqn = (
                f"{source_config.mysql_schema_name}.{source_config.mysql_sales_table}"
            )
            raw_rows = self._extract_from_mysql(
                source_config, from_date, to_date, table_fqn
            )
            logger.info(
                "Extracted %d daily rows from MySQL (%s to %s)",
                len(raw_rows),
                from_date,
                to_date,
            )

        weekly_df = self._aggregate_to_weekly(raw_rows)
        rows_extracted = len(weekly_df)

        active_skus = self._load_active_skus(pg_db)
        weekly_df = weekly_df[weekly_df["product_code"].isin(active_skus)].reset_index(drop=True)
        rows_after_filter = len(weekly_df)
        logger.info(
            "After active-product filter: %d → %d weekly rows", rows_extracted, rows_after_filter
        )

        rows_upserted = self._upsert(forecast_db, weekly_df)
        return {
            "rows_extracted": rows_extracted,
            "rows_after_filter": rows_after_filter,
            "rows_upserted": rows_upserted,
        }

    def ping(self, source_config: ForecastSourceConfig) -> bool:
        """Check MySQL source connectivity without raising."""
        if _uses_platform_demand_facts_table(source_config):
            return True
        try:
            engine = self._get_source_engine(source_config)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.warning("MySQL ping failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_from_demand_facts_weekly(
        self,
        pg_db: Session,
        from_date: date,
        to_date: date,
    ) -> list[dict[str, Any]]:
        """Build the same row shape as ``_extract_from_mysql`` from canonical weekly facts."""
        rows: list[dict[str, Any]] = []
        q = (
            pg_db.query(DemandFactsWeekly, Product)
            .outerjoin(Product, Product.sku == DemandFactsWeekly.sku)
            .filter(DemandFactsWeekly.demand_type == DemandType.CUSTOMER)
            .filter(DemandFactsWeekly.week_start >= from_date)
            .filter(DemandFactsWeekly.week_start <= to_date)
        )
        for dfw, prod in q.all():
            wh = str(dfw.warehouse_code).strip().upper() if dfw.warehouse_code else self._default_warehouse
            item_size_raw = prod.single_unit_content if prod is not None else None
            row_dict: dict[str, Any] = {
                "trans_date": dfw.week_start,
                "product_code": str(dfw.sku).strip(),
                "product_name": str(prod.name).strip() if prod and prod.name else None,
                "item_size": float(str(item_size_raw)) if item_size_raw is not None else None,
                "pip_code": str(prod.aah_code).strip() if prod and prod.aah_code else None,
                "warehouse_code": wh,
                "units_sold": Decimal(str(dfw.qty)) if dfw.qty is not None else Decimal("0"),
            }
            rows.append(row_dict)
        return rows

    def _get_source_engine(self, source_config: ForecastSourceConfig) -> Engine:
        """Build a SQLAlchemy engine: credentials from DATABASE_URL, DB from source config."""
        from sqlalchemy import create_engine as sa_create_engine

        user, pwd, host, port, database = _ingest_source_connection(source_config)
        url = (
            f"mysql+pymysql://{quote_plus(user)}:{quote_plus(pwd)}"
            f"@{host}:{port}/{quote_plus(database)}?charset=utf8mb4"
        )
        connect_args: dict[str, object] = {}
        if settings.database_ssl_disabled:
            connect_args["ssl_disabled"] = True
        return sa_create_engine(
            url,
            connect_args=connect_args,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=0,
        )

    def _extract_from_mysql(
        self,
        source_config: ForecastSourceConfig,
        from_date: date,
        to_date: date,
        table_fqn: str,
    ) -> list[dict[str, Any]]:
        engine = self._get_source_engine(source_config)
        try:
            with engine.connect() as conn:
                try:
                    q = text(_QUERY_WITH_WAREHOUSE.format(table=table_fqn))
                    rows = conn.execute(q, {"from_date": from_date, "to_date": to_date}).fetchall()
                    has_warehouse = True
                except Exception:
                    q = text(_QUERY_NO_WAREHOUSE.format(table=table_fqn))
                    rows = conn.execute(q, {"from_date": from_date, "to_date": to_date}).fetchall()
                    has_warehouse = False
        except OperationalError as exc:
            user, _pwd, eff_host, eff_port, _dbn = _ingest_source_connection(source_config)
            raise MySQLUnavailableError(
                f"Cannot connect to MySQL source. "
                f"user={user!r} effective_host={eff_host!r} effective_port={eff_port} "
                f"db={source_config.mysql_database!r} (stored mysql_host={source_config.mysql_host!r}). "
                f"User/password for ingest match DATABASE_URL (same as platform). "
                f"1044 = no privilege on that database; 1045 = bad password. "
                f"Example: GRANT SELECT ON aymes_reports.* TO 'user'@'localhost'; FLUSH PRIVILEGES; "
                f"Also grant @'127.0.0.1' if you connect that way. "
                f"Detail: {exc}"
            ) from exc

        result: list[dict[str, Any]] = []
        for row in rows:
            wh = (
                str(row.warehouse_col).strip().upper()
                if has_warehouse and getattr(row, "warehouse_col", None)
                else self._default_warehouse
            )
            item_size_raw = getattr(row, "item_size", None)
            result.append({
                "trans_date": row.trans_date,
                "product_code": str(row.product_code).strip(),
                "product_name": str(row.product_name).strip() if row.product_name else None,
                "item_size": float(str(item_size_raw)) if item_size_raw else None,
                "pip_code": str(row.pip_code).strip() if row.pip_code else None,
                "warehouse_code": wh,
                "units_sold": Decimal(str(row.weekly_qty)) if row.weekly_qty else Decimal("0"),
            })
        return result

    def _aggregate_to_weekly(self, raw_rows: list[dict[str, Any]]) -> pd.DataFrame:
        if not raw_rows:
            return pd.DataFrame(
                columns=["product_code", "warehouse_code", "week_start", "units_sold",
                         "product_name", "item_size", "pip_code"]
            )
        df = pd.DataFrame(raw_rows)
        df["week_start"] = df["trans_date"].apply(
            lambda d: week_start_for_date(d) if d else None
        )
        df = df.dropna(subset=["week_start", "product_code"])
        agg = (
            df.groupby(["product_code", "warehouse_code", "week_start"])
            .agg(
                units_sold=("units_sold", "sum"),
                product_name=("product_name", "first"),
                item_size=("item_size", "first"),
                pip_code=("pip_code", "first"),
            )
            .reset_index()
        )
        return agg

    def _load_active_skus(self, pg_db: Session) -> set[str]:
        rows = pg_db.query(Product.sku).filter(Product.active == True).all()  # noqa: E712
        return {str(r.sku) for r in rows}

    def _upsert(self, forecast_db: Session, df: pd.DataFrame) -> int:
        """Upsert rows into MySQL forecast_sales_weekly."""
        if df.empty:
            return 0

        rows_written = 0
        for _, row in df.iterrows():
            item_size_val = float(row["item_size"]) if row.get("item_size") and pd.notna(row["item_size"]) else None
            stmt = mysql_insert(ForecastSalesWeekly).values(
                product_code=str(row["product_code"]),
                warehouse_code=str(row["warehouse_code"]),
                week_start=row["week_start"],
                units_sold=float(row["units_sold"]),
                product_name=row.get("product_name"),
                pip_code=row.get("pip_code"),
                item_size=item_size_val,
                source_system="mysql_vertex_source",
            ).on_duplicate_key_update(
                units_sold=float(row["units_sold"]),
                product_name=row.get("product_name"),
                pip_code=row.get("pip_code"),
            )
            forecast_db.execute(stmt)
            rows_written += 1

        forecast_db.flush()
        logger.info("Upserted %d rows into forecast_sales_weekly", rows_written)
        return rows_written
