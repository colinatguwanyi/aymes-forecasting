"""
LegacyOutputRepository — read-only repository for the legacy forecast output tables.

Targets MySQL database aymes_reports (or LEGACY_OUTPUT_TARGET_DB):
    aymes_demand_planning_forecast_by_model_new   (staging)
    aymes_demand_planning_forecast_by_model       (live / consumer-facing)

This module owns the single engine factory for the legacy output database.
LegacyOutputExporter and ParityValidator both import _get_legacy_engine from here
so there is exactly one connection pool for this database.

Configuration (via .env / config.py):
    LEGACY_OUTPUT_TARGET_DB          — target database  (default: aymes_reports)
    LEGACY_OUTPUT_STAGING_TABLE      — staging table    (default: ..._new)
    LEGACY_OUTPUT_LIVE_TABLE         — live table
    LEGACY_OUTPUT_MYSQL_HOST         — override host    (falls back to MYSQL_HOST)
    LEGACY_OUTPUT_MYSQL_PORT         — override port    (falls back to MYSQL_PORT)
    LEGACY_OUTPUT_MYSQL_USER         — override user    (falls back to MYSQL_USER)
    LEGACY_OUTPUT_MYSQL_PASSWORD     — override password (falls back to MYSQL_PASSWORD)

All repository methods are read-only; write / promote operations remain in
LegacyOutputExporter.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Expected columns — used for shape validation
# ---------------------------------------------------------------------------
_REQUIRED_COLS: set[str] = {
    "AAH_Product_Code",
    "Product_Name",
    "Inference_Date",
    "Forecast_Week",
    "Actual",
    "Interpolated_Values",
    "Forecast",
    "Model",
    "Model_Details",
    "Mean_Absolute_Percentage_Error",
    "Mean_Absolute_Error",
    "Is_Best_Model",
    "Outlier",
    "Predicted_Best_Model_Bool",
}


# ---------------------------------------------------------------------------
# Engine factory (single instance, used by exporter + validator + repository)
# ---------------------------------------------------------------------------
#
# We deliberately avoid @lru_cache here.  lru_cache would bake the URL at
# first import time, before .env values are applied by pydantic-settings.
# Instead we cache via a module-level dict so the engine is built once on
# first actual call, but can still be cleared in tests via _clear_engine().

_engine_cache: dict[str, Engine] = {}


def _get_legacy_engine() -> Engine:
    """
    Return (and cache) a SQLAlchemy engine for the legacy output MySQL database.

    Connection parameters resolve as:
        host     → LEGACY_OUTPUT_MYSQL_HOST  or  MYSQL_HOST
        port     → LEGACY_OUTPUT_MYSQL_PORT  or  MYSQL_PORT
        user     → LEGACY_OUTPUT_MYSQL_USER  or  MYSQL_USER
        password → LEGACY_OUTPUT_MYSQL_PASSWORD or MYSQL_PASSWORD
        database → LEGACY_OUTPUT_TARGET_DB   (always explicit)

    The cache key is the full URL string so that different runtime configs
    produce separate engines automatically.
    """
    from app.config import settings

    host     = settings.legacy_output_mysql_host     or settings.mysql_host
    port     = settings.legacy_output_mysql_port     or settings.mysql_port
    user     = settings.legacy_output_mysql_user     or settings.mysql_user
    password = (
        settings.legacy_output_mysql_password
        if settings.legacy_output_mysql_password is not None
        else settings.mysql_password
    )
    database = settings.legacy_output_target_db

    url = (
        f"mysql+pymysql://{user}:{password}"
        f"@{host}:{port}/{database}"
        "?charset=utf8mb4"
    )

    if url not in _engine_cache:
        engine = create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=0)
        _engine_cache[url] = engine
        logger.info(
            "LegacyOutputRepository: engine created → %s:%s/%s (user=%s)",
            host, port, database, user,
        )
    return _engine_cache[url]


def _clear_engine_cache() -> None:
    """Dispose all cached engines and clear the cache (useful in tests)."""
    for engine in _engine_cache.values():
        engine.dispose()
    _engine_cache.clear()


# ---------------------------------------------------------------------------
# LegacyOutputRepository
# ---------------------------------------------------------------------------

class LegacyOutputRepository:
    """
    Read-only access to the legacy forecast output tables in aymes_reports.

    All methods handle connection failures, missing tables, and missing columns
    gracefully — returning empty results and structured error information rather
    than raising.
    """

    def __init__(
        self,
        live_table: str | None = None,
        staging_table: str | None = None,
    ) -> None:
        from app.config import settings
        self.live_table = live_table or settings.legacy_output_live_table
        self.staging_table = staging_table or settings.legacy_output_staging_table

    # ------------------------------------------------------------------
    # Row retrieval
    # ------------------------------------------------------------------

    def get_live_rows_for_inference_date(
        self,
        inference_date: date,
        limit: int = 10_000,
    ) -> list[dict[str, Any]]:
        """Return all rows in the live table for inference_date."""
        return self._query_rows(
            self.live_table,
            "WHERE Inference_Date = :inference_date LIMIT :lim",
            {"inference_date": inference_date, "lim": limit},
        )

    def get_staging_rows_for_run(
        self,
        run_id: int,
        limit: int = 10_000,
    ) -> list[dict[str, Any]]:
        """Return staging rows for a specific run_id."""
        return self._query_rows(
            self.staging_table,
            "WHERE run_id = :run_id LIMIT :lim",
            {"run_id": run_id, "lim": limit},
        )

    def sample_live_rows(
        self,
        inference_date: date,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return a small sample from the live table for a given inference_date."""
        return self._query_rows(
            self.live_table,
            "WHERE Inference_Date = :inference_date ORDER BY AAH_Product_Code LIMIT :lim",
            {"inference_date": inference_date, "lim": limit},
        )

    # ------------------------------------------------------------------
    # Count queries
    # ------------------------------------------------------------------

    def count_live_rows_for_inference_date(self, inference_date: date) -> int:
        """Total row count in the live table for the given inference_date."""
        return self._scalar_int(
            self.live_table,
            "SELECT COUNT(*) FROM {table} WHERE Inference_Date = :dt",
            {"dt": inference_date},
        )

    def count_staging_rows_for_run(self, run_id: int) -> int:
        """Total row count in the staging table for the given run_id."""
        return self._scalar_int(
            self.staging_table,
            "SELECT COUNT(*) FROM {table} WHERE run_id = :rid",
            {"rid": run_id},
        )

    # ------------------------------------------------------------------
    # Analytical queries (live table only)
    # ------------------------------------------------------------------

    def get_live_model_breakdown(self, inference_date: date) -> dict[str, int]:
        """
        Row count per Model_Details value in the live table for inference_date.
        Returns {} on error.
        """
        try:
            engine = _get_legacy_engine()
            with engine.connect() as conn:
                result = conn.execute(
                    text(  # noqa: S608
                        f"SELECT Model_Details, COUNT(*) AS cnt "
                        f"FROM {self.live_table} "
                        "WHERE Inference_Date = :dt "
                        "GROUP BY Model_Details "
                        "ORDER BY Model_Details"
                    ),
                    {"dt": inference_date},
                )
                return {str(row[0]): int(row[1]) for row in result.fetchall()}
        except Exception as exc:
            logger.warning("get_live_model_breakdown failed: %s", exc)
            return {}

    def get_live_distinct_sku_count(self, inference_date: date) -> int:
        """Distinct AAH_Product_Code count for inference_date in the live table."""
        return self._scalar_int(
            self.live_table,
            "SELECT COUNT(DISTINCT AAH_Product_Code) FROM {table} "
            "WHERE Inference_Date = :dt",
            {"dt": inference_date},
        )

    def get_live_min_max_forecast_week(
        self, inference_date: date
    ) -> dict[str, Any]:
        """
        Return the MIN and MAX Forecast_Week for the given inference_date.

        Returns:
            {"min": "YYYY-MM-DD" | None, "max": "YYYY-MM-DD" | None, "errors": list[str]}
        """
        errors: list[str] = []
        try:
            engine = _get_legacy_engine()
            with engine.connect() as conn:
                row = conn.execute(
                    text(  # noqa: S608
                        f"SELECT MIN(Forecast_Week), MAX(Forecast_Week) "
                        f"FROM {self.live_table} WHERE Inference_Date = :dt"
                    ),
                    {"dt": inference_date},
                ).fetchone()
                if row:
                    return {
                        "min":    str(row[0]) if row[0] is not None else None,
                        "max":    str(row[1]) if row[1] is not None else None,
                        "errors": errors,
                    }
        except Exception as exc:
            msg = f"get_live_min_max_forecast_week failed: {exc}"
            logger.warning(msg)
            errors.append(msg)
        return {"min": None, "max": None, "errors": errors}

    def get_live_null_summary(self, inference_date: date) -> dict[str, Any]:
        """
        Compute the NULL rate for each key column in the live table for the
        given inference_date.

        Returns a dict mapping column_name → {"null_count": int, "total": int, "null_rate": float}
        for the following columns:
            Forecast, Actual, Interpolated_Values,
            Is_Best_Model, Outlier, Predicted_Best_Model_Bool,
            Mean_Absolute_Percentage_Error, Mean_Absolute_Error, Product_Name
        """
        cols = [
            "Forecast",
            "Actual",
            "Interpolated_Values",
            "Is_Best_Model",
            "Outlier",
            "Predicted_Best_Model_Bool",
            "Mean_Absolute_Percentage_Error",
            "Mean_Absolute_Error",
            "Product_Name",
        ]
        errors: list[str] = []
        summary: dict[str, Any] = {}
        try:
            engine = _get_legacy_engine()
            # Build a single query that counts NULLs for every column at once
            null_exprs = ", ".join(
                f"SUM(CASE WHEN `{c}` IS NULL THEN 1 ELSE 0 END) AS `null_{c}`"
                for c in cols
            )
            with engine.connect() as conn:
                row = conn.execute(
                    text(  # noqa: S608
                        f"SELECT COUNT(*) AS total_rows, {null_exprs} "
                        f"FROM {self.live_table} WHERE Inference_Date = :dt"
                    ),
                    {"dt": inference_date},
                ).fetchone()
                if row:
                    total = int(row[0] or 0)
                    for idx, col in enumerate(cols, start=1):
                        null_count = int(row[idx] or 0)
                        summary[col] = {
                            "null_count": null_count,
                            "total":      total,
                            "null_rate":  round(null_count / total, 4) if total > 0 else 0.0,
                        }
        except Exception as exc:
            msg = f"get_live_null_summary failed: {exc}"
            logger.warning(msg)
            errors.append(msg)
        return {"columns": summary, "errors": errors}

    def detect_live_duplicates(self, inference_date: date) -> dict[str, Any]:
        """
        Find rows with duplicate composite keys
        (AAH_Product_Code, Inference_Date, Forecast_Week, Model_Details).

        Returns:
            duplicate_key_count   : int — number of rows that share a key with another
            first_duplicates      : list[dict] — up to 20 example duplicated key groups
            errors                : list[str]
        """
        errors: list[str] = []
        try:
            engine = _get_legacy_engine()
            with engine.connect() as conn:
                # Count rows involved in duplicate key groups
                count_sql = text(  # noqa: S608
                    f"""
                    SELECT SUM(cnt) FROM (
                        SELECT COUNT(*) AS cnt
                        FROM {self.live_table}
                        WHERE Inference_Date = :dt
                        GROUP BY AAH_Product_Code, Inference_Date, Forecast_Week, Model_Details
                        HAVING cnt > 1
                    ) AS dupes
                    """
                )
                dup_count = int(conn.execute(count_sql, {"dt": inference_date}).scalar() or 0)

                # Fetch example duplicate groups (limit 20)
                examples_sql = text(  # noqa: S608
                    f"""
                    SELECT AAH_Product_Code, Forecast_Week, Model_Details, COUNT(*) AS cnt
                    FROM {self.live_table}
                    WHERE Inference_Date = :dt
                    GROUP BY AAH_Product_Code, Inference_Date, Forecast_Week, Model_Details
                    HAVING cnt > 1
                    ORDER BY cnt DESC
                    LIMIT 20
                    """
                )
                rows = conn.execute(examples_sql, {"dt": inference_date}).fetchall()
                examples = [
                    {
                        "AAH_Product_Code": str(r[0]),
                        "Forecast_Week":    str(r[1]),
                        "Model_Details":    str(r[2]),
                        "count":            int(r[3]),
                    }
                    for r in rows
                ]
        except Exception as exc:
            msg = f"detect_live_duplicates failed: {exc}"
            logger.warning(msg)
            errors.append(msg)
            return {"duplicate_key_count": 0, "first_duplicates": [], "errors": errors}

        return {
            "duplicate_key_count": dup_count,
            "first_duplicates":    examples,
            "errors":              errors,
        }

    # ------------------------------------------------------------------
    # Shape / health validation
    # ------------------------------------------------------------------

    def validate_live_table_shape(self) -> dict[str, Any]:
        """
        Verify the live table exists and contains all expected columns.

        Returns:
            table_exists           : bool
            columns_present        : list[str]
            missing_columns        : list[str]
            extra_columns          : list[str]
            required_columns_present : bool
            errors                 : list[str]
        """
        return self._validate_table_shape(self.live_table)

    def validate_staging_table_shape(self) -> dict[str, Any]:
        """Same check for the staging table."""
        return self._validate_table_shape(self.staging_table)

    def health_check(self) -> dict[str, Any]:
        """
        Full connectivity and schema health check.

        Returns:
            can_connect                : bool
            target_db                  : str
            staging_table_exists       : bool
            live_table_exists          : bool
            required_columns_present   : bool
            sample_row_count           : int  (recent rows in live table)
            errors                     : list[str]
        """
        from app.config import settings

        result: dict[str, Any] = {
            "can_connect":               False,
            "target_db":                 settings.legacy_output_target_db,
            "staging_table_exists":      False,
            "live_table_exists":         False,
            "required_columns_present":  False,
            "sample_row_count":          0,
            "errors":                    [],
        }
        errors: list[str] = result["errors"]

        # Step 1: basic connectivity
        try:
            engine = _get_legacy_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            result["can_connect"] = True
        except Exception as exc:
            errors.append(f"Connection failed: {exc}")
            return result

        # Step 2: inspect tables
        try:
            engine = _get_legacy_engine()
            insp = inspect(engine)
            existing = set(insp.get_table_names())
            result["live_table_exists"]    = self.live_table    in existing
            result["staging_table_exists"] = self.staging_table in existing
        except Exception as exc:
            errors.append(f"Table inspection failed: {exc}")

        # Step 3: column check on live table
        if result["live_table_exists"]:
            shape = self._validate_table_shape(self.live_table)
            result["required_columns_present"] = shape["required_columns_present"]
            if shape["missing_columns"]:
                errors.append(
                    f"Live table missing columns: {shape['missing_columns']}"
                )
            errors.extend(shape.get("errors", []))

        # Step 4: sample row count
        if result["live_table_exists"]:
            try:
                engine = _get_legacy_engine()
                with engine.connect() as conn:
                    n = conn.execute(
                        text(f"SELECT COUNT(*) FROM {self.live_table} LIMIT 1")  # noqa: S608
                    ).scalar()
                    result["sample_row_count"] = int(n or 0)
            except Exception as exc:
                errors.append(f"Row count check failed: {exc}")

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _query_rows(
        self,
        table: str,
        where_clause: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Execute a SELECT * with a given WHERE clause and return list of dicts."""
        try:
            engine = _get_legacy_engine()
            with engine.connect() as conn:
                result = conn.execute(
                    text(f"SELECT * FROM {table} {where_clause}"),  # noqa: S608
                    params,
                )
                cols = list(result.keys())
                return [dict(zip(cols, row)) for row in result.fetchall()]
        except (OperationalError, ProgrammingError) as exc:
            logger.warning("_query_rows(%s): %s", table, exc)
            return []
        except Exception as exc:
            logger.warning("_query_rows(%s) unexpected error: %s", table, exc)
            return []

    def _scalar_int(
        self,
        table: str,
        sql_template: str,
        params: dict[str, Any],
    ) -> int:
        """Execute a scalar COUNT query and return the integer result."""
        try:
            engine = _get_legacy_engine()
            with engine.connect() as conn:
                result = conn.execute(
                    text(sql_template.format(table=table)),  # noqa: S608
                    params,
                )
                return int(result.scalar() or 0)
        except (OperationalError, ProgrammingError) as exc:
            logger.warning("_scalar_int(%s): %s", table, exc)
            return 0
        except Exception as exc:
            logger.warning("_scalar_int(%s) unexpected error: %s", table, exc)
            return 0

    def _validate_table_shape(self, table: str) -> dict[str, Any]:
        errors: list[str] = []
        try:
            engine = _get_legacy_engine()
            insp = inspect(engine)
            if table not in set(insp.get_table_names()):
                return {
                    "table_exists":              False,
                    "columns_present":           [],
                    "missing_columns":           sorted(_REQUIRED_COLS),
                    "extra_columns":             [],
                    "required_columns_present":  False,
                    "errors":                    [f"Table '{table}' does not exist"],
                }
            cols_present = {c["name"] for c in insp.get_columns(table)}
            missing = sorted(_REQUIRED_COLS - cols_present)
            extra   = sorted(cols_present - _REQUIRED_COLS - {"id", "run_id", "warehouse_code", "created_at"})
            return {
                "table_exists":              True,
                "columns_present":           sorted(cols_present),
                "missing_columns":           missing,
                "extra_columns":             extra,
                "required_columns_present":  len(missing) == 0,
                "errors":                    errors,
            }
        except Exception as exc:
            msg = f"Shape validation for '{table}' failed: {exc}"
            logger.warning(msg)
            errors.append(msg)
            return {
                "table_exists":              False,
                "columns_present":           [],
                "missing_columns":           [],
                "extra_columns":             [],
                "required_columns_present":  False,
                "errors":                    errors,
            }
