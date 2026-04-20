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
  - SOURCE (read):  built from ForecastSourceConfig.mysql_host/port/database +
                    env-var credentials.  Falls back to app.config.settings values
                    when host/port are null (convenience for dev/local envs).
  - FORECAST (write): passed in as forecast_db (MySQL aymes_forecasting session).
  - PLATFORM (read):  pg_db (Postgres) — only used to resolve active product codes.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import settings
from app.forecast_mysql_models import ForecastSalesWeekly, ForecastSourceConfig
from app.models import Product
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


class MySQLSalesIngestService:
    """
    Extracts raw daily sales from adhl_data_daily, aggregates to W-TUE weekly
    buckets, filters inactive products, and upserts into forecast_sales_weekly.
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

        pg_db       — Postgres session (read active products from platform).
        forecast_db — MySQL forecast session (write forecast_sales_weekly).

        Returns dict with: rows_extracted, rows_after_filter, rows_upserted.
        """
        table_fqn = (
            f"{source_config.mysql_schema_name}.{source_config.mysql_sales_table}"
        )

        raw_rows = self._extract_from_mysql(source_config, from_date, to_date, table_fqn)
        logger.info(
            "Extracted %d daily rows from MySQL (%s to %s)", len(raw_rows), from_date, to_date
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

    def _get_source_engine(self, source_config: ForecastSourceConfig) -> Engine:
        """Build a SQLAlchemy engine from ForecastSourceConfig + env-var credentials."""
        from sqlalchemy import create_engine as sa_create_engine

        host = str(source_config.mysql_host) if source_config.mysql_host is not None else settings.mysql_host
        port = int(str(source_config.mysql_port)) if source_config.mysql_port is not None else settings.mysql_port
        database = str(source_config.mysql_database)
        user = settings.mysql_user
        pwd = settings.mysql_password

        url = f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{database}?charset=utf8mb4"
        return sa_create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=0)

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
            raise MySQLUnavailableError(
                f"Cannot connect to MySQL source. "
                f"host={source_config.mysql_host} db={source_config.mysql_database}. "
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
