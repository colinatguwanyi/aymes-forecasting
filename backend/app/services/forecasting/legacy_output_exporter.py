"""
Legacy output exporter — compatibility layer for aymes_demand_planning_forecast_by_model.

Maps rows from aymes_forecasting.forecast_results_weekly into the legacy
Vertex pipeline output shape and writes them to:

    aymes_reports.aymes_demand_planning_forecast_by_model_new  (staging)

Optional safe-replace (disabled by default):
    After validating row counts, the exporter can promote the staging table
    content into the live table aymes_reports.aymes_demand_planning_forecast_by_model
    using a TRUNCATE + INSERT SELECT pattern — preserving the live table structure
    so downstream consumers see no schema change.

Column mapping (forecast_results_weekly → legacy output)
---------------------------------------------------------
Source column              Legacy column                     Type         Nullable
--------------------------  --------------------------------  -----------  --------
product_code               AAH_Product_Code                  VARCHAR(50)  NOT NULL
product_name               Product_Name                      VARCHAR(255) NULL
inference_date             Inference_Date                    DATE         NOT NULL
forecast_week              Forecast_Week                     DATE         NOT NULL
actual_units               Actual                            DECIMAL(18,4) NULL
interpolated_units         Interpolated_Values               DECIMAL(18,4) NULL
forecast_units             Forecast                          DECIMAL(18,4) NULL
model_name                 Model                             VARCHAR(100) NOT NULL
model_details              Model_Details                     VARCHAR(100) NOT NULL
mape                       Mean_Absolute_Percentage_Error    DECIMAL(18,6) NULL
mae                        Mean_Absolute_Error               DECIMAL(18,6) NULL
is_best_model              Is_Best_Model                     BOOLEAN      NULL
outlier_flag               Outlier                           BOOLEAN      NULL
predicted_best_model_bool  Predicted_Best_Model_Bool         BOOLEAN      NULL
run_id (extra)             run_id                            BIGINT       NOT NULL
warehouse_code (extra)     warehouse_code                    VARCHAR(50)  NULL

Conversion rules
----------------
- Strings        : str(v), stripped, truncated to column limit; None preserved as NULL.
- Dates          : normalized to datetime.date; datetime objects are truncated to date.
- Decimals(18,4) : Decimal, ROUND_HALF_UP to 4dp; floats first converted via str().
- Decimals(18,6) : Decimal, ROUND_HALF_UP to 6dp.
- Booleans       : True/False/None only — no implicit 0→False coercion; None preserved.
- run_id         : always int; never None (required field).

Validation rules (validate_legacy_row)
---------------------------------------
Hard errors (row skipped during insert):
  - AAH_Product_Code is None or empty string
  - Inference_Date is None
  - Forecast_Week is None
  - Model is None or empty string
  - Model_Details is None or empty string
  - run_id is None

Warnings (row included, logged):
  - Forecast is None
  - Is_Best_Model is None
  - MAPE is None
  - Model_Details not in known Vertex variants
  - Any string value was truncated to fit column width

Configuration (via .env):
    LEGACY_OUTPUT_ENABLED       — enable the export step at all (default: false)
    LEGACY_OUTPUT_SAFE_REPLACE  — also promote staging → live table (default: false)
    LEGACY_OUTPUT_TARGET_DB     — MySQL database containing the legacy tables
    LEGACY_OUTPUT_STAGING_TABLE — staging table name
    LEGACY_OUTPUT_LIVE_TABLE    — live table name consumers read from

Public pure functions (unit-testable, no DB dependency):
    map_forecast_result_to_legacy_row(...)
    validate_legacy_row(row)
    build_legacy_export_dataframe(rows, run_id)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

import pandas as pd
from sqlalchemy import MetaData, Table, Column, BigInteger, Boolean, Date, DateTime, Numeric, String, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.forecast_mysql_models import ForecastResultWeekly

logger = logging.getLogger(__name__)

_BATCH_SIZE = 2000

# ---------------------------------------------------------------------------
# Constants — column limits and known model identifiers
# ---------------------------------------------------------------------------

_COL_LIMITS: dict[str, int] = {
    "AAH_Product_Code": 50,
    "Product_Name":     255,
    "Model":            100,
    "Model_Details":    100,
    "warehouse_code":   50,
}

# Exact Model_Details values produced by the Vertex pipeline.
# Rows with other values are written but trigger a validation warning.
_KNOWN_MODEL_DETAILS: frozenset[str] = frozenset({
    "Prophet_with_outliers",
    "Prophet_without_outliers",
    "XGBoost_with_outliers",
    "XGBoost_without_outliers",
})

# Composite key fields used by the legacy table (for duplicate detection)
_LEGACY_KEY = ("AAH_Product_Code", "Inference_Date", "Forecast_Week", "Model_Details")

# Required fields — a row is invalid and will be skipped if any are None/empty
_REQUIRED_FIELDS = ("AAH_Product_Code", "Inference_Date", "Forecast_Week", "Model", "Model_Details")


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

@dataclass
class RowValidation:
    """Result of validate_legacy_row(). Immutable once returned."""
    is_valid:  bool
    warnings:  list[str] = field(default_factory=list)
    errors:    list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure conversion helpers
# ---------------------------------------------------------------------------

def _truncate(value: str, col: str) -> tuple[str, bool]:
    """
    Truncate a string value to the column's VARCHAR limit.
    Returns (possibly-truncated string, was_truncated).
    """
    limit = _COL_LIMITS.get(col)
    if limit is None or len(value) <= limit:
        return value, False
    return value[:limit], True


def _to_str(v: Any, col: str) -> tuple[str | None, bool]:
    """
    Coerce to string, strip whitespace, apply column truncation.
    Returns (value_or_None, was_truncated).
    """
    if v is None:
        return None, False
    s = str(v).strip()
    if not s:
        return None, False
    return _truncate(s, col)


def _to_date(v: Any) -> date | None:
    """
    Normalize a value to datetime.date.
    Accepts: date, datetime, str (YYYY-MM-DD).  Returns None for None/invalid.
    """
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except (ValueError, TypeError):
        return None


def _to_decimal4(v: Any) -> Decimal | None:
    """
    Convert a numeric value to Decimal with 4 decimal places (ROUND_HALF_UP).
    Safe for DECIMAL(18, 4) columns.
    """
    if v is None:
        return None
    try:
        return Decimal(str(v)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return None


def _to_decimal6(v: Any) -> Decimal | None:
    """
    Convert a numeric value to Decimal with 6 decimal places (ROUND_HALF_UP).
    Safe for DECIMAL(18, 6) columns.
    """
    if v is None:
        return None
    try:
        return Decimal(str(v)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return None


def _to_bool(v: Any) -> bool | None:
    """
    Coerce a value to True / False / None.
    - None / SQL NULL → None (preserved)
    - 1 / True / "1" / "true" / "True" → True
    - 0 / False / "0" / "false" / "False" → False
    - Anything else → None (not coerced silently)
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        if v == 1:
            return True
        if v == 0:
            return False
        return None
    sv = str(v).strip().lower()
    if sv in ("1", "true"):
        return True
    if sv in ("0", "false"):
        return False
    return None


# ---------------------------------------------------------------------------
# Pure mapping function — accepts primitives, no ORM dependency
# ---------------------------------------------------------------------------

def map_forecast_result_to_legacy_row(
    *,
    product_code:             Any,
    product_name:             Any,
    inference_date:           Any,
    forecast_week:            Any,
    actual_units:             Any,
    interpolated_units:       Any,
    forecast_units:           Any,
    model_name:               Any,
    model_details:            Any,
    mape:                     Any,
    mae:                      Any,
    is_best_model:            Any,
    outlier_flag:             Any,
    predicted_best_model_bool: Any,
    run_id:                   Any,
    warehouse_code:           Any = None,
) -> dict[str, Any]:
    """
    Map individual forecast result values to the legacy output column dict.

    All inputs accept raw values from any source (ORM, dict, test fixture).
    Conversion follows the rules documented at the top of this module.

    Returns a dict keyed by legacy column names, ready for MySQL bulk insert.
    This function never raises — invalid values are converted to None.
    """
    pc,  pc_trunc  = _to_str(product_code,   "AAH_Product_Code")
    pn,  pn_trunc  = _to_str(product_name,   "Product_Name")
    mn,  mn_trunc  = _to_str(model_name,     "Model")
    md,  md_trunc  = _to_str(model_details,  "Model_Details")
    wh,  wh_trunc  = _to_str(warehouse_code, "warehouse_code")

    return {
        "AAH_Product_Code":               pc,
        "Product_Name":                   pn,
        "Inference_Date":                 _to_date(inference_date),
        "Forecast_Week":                  _to_date(forecast_week),
        "Actual":                         _to_decimal4(actual_units),
        "Interpolated_Values":            _to_decimal4(interpolated_units),
        "Forecast":                       _to_decimal4(forecast_units),
        "Model":                          mn,
        "Model_Details":                  md,
        "Mean_Absolute_Percentage_Error": _to_decimal6(mape),
        "Mean_Absolute_Error":            _to_decimal6(mae),
        "Is_Best_Model":                  _to_bool(is_best_model),
        "Outlier":                        _to_bool(outlier_flag),
        "Predicted_Best_Model_Bool":      _to_bool(predicted_best_model_bool),
        "run_id":                         int(run_id) if run_id is not None else None,
        "warehouse_code":                 wh,
        # Truncation flags for validate_legacy_row (stripped before insert)
        "_truncated": [
            f"AAH_Product_Code" if pc_trunc else "",
            f"Product_Name"     if pn_trunc else "",
            f"Model"            if mn_trunc else "",
            f"Model_Details"    if md_trunc else "",
            f"warehouse_code"   if wh_trunc else "",
        ],
    }


# ---------------------------------------------------------------------------
# Validation function — pure, no DB dependency
# ---------------------------------------------------------------------------

def validate_legacy_row(row: dict[str, Any]) -> RowValidation:
    """
    Validate a legacy output row dict produced by map_forecast_result_to_legacy_row.

    Returns RowValidation with:
      is_valid  — False if any hard-error condition is met (row should be skipped)
      warnings  — non-fatal issues logged but row still exported
      errors    — fatal issues that cause the row to be skipped
    """
    errors:   list[str] = []
    warnings: list[str] = []

    # Hard-error checks (required fields)
    for col in _REQUIRED_FIELDS:
        v = row.get(col)
        if v is None or (isinstance(v, str) and not v.strip()):
            errors.append(f"Required field '{col}' is null or empty")

    # run_id required
    if row.get("run_id") is None:
        errors.append("run_id is None")

    # Truncation warnings
    for col in (row.get("_truncated") or []):
        if col:
            warnings.append(f"'{col}' was truncated to fit VARCHAR limit")

    # Known model_details check
    md = row.get("Model_Details")
    if md and md not in _KNOWN_MODEL_DETAILS:
        warnings.append(
            f"Model_Details='{md}' is not a standard Vertex variant "
            f"({sorted(_KNOWN_MODEL_DETAILS)})"
        )

    # Suspect null warnings
    if row.get("Forecast") is None:
        warnings.append("Forecast is NULL (expected for future weeks but verify)")
    if row.get("Is_Best_Model") is None:
        warnings.append("Is_Best_Model is NULL")
    if row.get("Mean_Absolute_Percentage_Error") is None:
        warnings.append("MAPE is NULL")

    return RowValidation(
        is_valid=len(errors) == 0,
        warnings=warnings,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Batch DataFrame builder — pure except for ORM field access
# ---------------------------------------------------------------------------

def build_legacy_export_dataframe(
    rows: list[ForecastResultWeekly],
    run_id: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Map a list of ForecastResultWeekly ORM rows to a legacy-shaped DataFrame,
    applying full validation and duplicate-key detection within the batch.

    Returns
    -------
    df       : DataFrame with legacy column names (no internal _truncated column).
               Contains only valid, deduplicated rows ready for MySQL insert.
    summary  : {
        total_input     : int,
        valid_rows      : int,
        skipped_rows    : int,
        duplicate_keys  : int,
        warning_count   : int,
        error_count     : int,
        skipped_details : list[dict]  (up to 50 examples of skipped rows)
    }
    """
    mapped: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen_keys: set[tuple[Any, ...]] = set()
    total_warnings = 0
    total_errors   = 0
    dup_count      = 0

    for r in rows:
        row = map_forecast_result_to_legacy_row(
            product_code             = r.product_code,
            product_name             = r.product_name,
            inference_date           = r.inference_date,
            forecast_week            = r.forecast_week,
            actual_units             = r.actual_units,
            interpolated_units       = r.interpolated_units,
            forecast_units           = r.forecast_units,
            model_name               = r.model_name,
            model_details            = r.model_details,
            mape                     = r.mape,
            mae                      = r.mae,
            is_best_model            = r.is_best_model,
            outlier_flag             = r.outlier_flag,
            predicted_best_model_bool= r.predicted_best_model_bool,
            run_id                   = run_id,
            warehouse_code           = r.warehouse_code,
        )

        validation = validate_legacy_row(row)
        total_warnings += len(validation.warnings)
        total_errors   += len(validation.errors)

        if not validation.is_valid:
            skipped.append({
                "product_code": str(r.product_code),
                "forecast_week": str(r.forecast_week),
                "model_details": str(r.model_details),
                "errors": validation.errors,
            })
            continue

        # Duplicate-key check within this export batch
        legacy_key = tuple(row.get(k) for k in _LEGACY_KEY)
        if legacy_key in seen_keys:
            dup_count += 1
            logger.warning(
                "build_legacy_export_dataframe: duplicate key skipped: %s", legacy_key
            )
            skipped.append({
                "product_code": str(r.product_code),
                "forecast_week": str(r.forecast_week),
                "model_details": str(r.model_details),
                "errors": ["Duplicate legacy key within export batch"],
            })
            continue
        seen_keys.add(legacy_key)

        # Strip internal _truncated flag before storing
        row.pop("_truncated", None)
        mapped.append(row)

    df = pd.DataFrame(mapped) if mapped else pd.DataFrame(
        columns=[
            "AAH_Product_Code", "Product_Name", "Inference_Date", "Forecast_Week",
            "Actual", "Interpolated_Values", "Forecast", "Model", "Model_Details",
            "Mean_Absolute_Percentage_Error", "Mean_Absolute_Error",
            "Is_Best_Model", "Outlier", "Predicted_Best_Model_Bool",
            "run_id", "warehouse_code",
        ]
    )

    summary = {
        "total_input":    len(rows),
        "valid_rows":     len(mapped),
        "skipped_rows":   len(skipped),
        "duplicate_keys": dup_count,
        "warning_count":  total_warnings,
        "error_count":    total_errors,
        "skipped_details": skipped[:50],
    }

    if skipped:
        logger.warning(
            "build_legacy_export_dataframe: %d/%d rows skipped "
            "(errors=%d, duplicates=%d)",
            len(skipped), len(rows), total_errors, dup_count,
        )

    return df, summary


# ---------------------------------------------------------------------------
# Internal ORM-to-dict helper used by LegacyOutputExporter (keeps batch loop clean)
# ---------------------------------------------------------------------------

def _map_orm_row(r: ForecastResultWeekly, run_id: int) -> dict[str, Any]:
    """
    Extract values from an ORM row, pass through the pure mapper, strip internals.
    Used by LegacyOutputExporter when writing directly without a full DataFrame pass.
    """
    row = map_forecast_result_to_legacy_row(
        product_code              = r.product_code,
        product_name              = r.product_name,
        inference_date            = r.inference_date,
        forecast_week             = r.forecast_week,
        actual_units              = r.actual_units,
        interpolated_units        = r.interpolated_units,
        forecast_units            = r.forecast_units,
        model_name                = r.model_name,
        model_details             = r.model_details,
        mape                      = r.mape,
        mae                       = r.mae,
        is_best_model             = r.is_best_model,
        outlier_flag              = r.outlier_flag,
        predicted_best_model_bool = r.predicted_best_model_bool,
        run_id                    = run_id,
        warehouse_code            = r.warehouse_code,
    )
    row.pop("_truncated", None)
    return row


# ---------------------------------------------------------------------------
# SQLAlchemy core Table definition for the legacy staging table.
# Uses a MetaData() without a Base so it doesn't interfere with ORM models.
# ---------------------------------------------------------------------------
_legacy_meta = MetaData()


def _make_legacy_table(table_name: str) -> Table:
    return Table(
        table_name,
        _legacy_meta,
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("AAH_Product_Code", String(50), nullable=False),
        Column("Product_Name", String(255), nullable=True),
        Column("Inference_Date", Date, nullable=False),
        Column("Forecast_Week", Date, nullable=False),
        Column("Actual", Numeric(18, 4), nullable=True),
        Column("Interpolated_Values", Numeric(18, 4), nullable=True),
        Column("Forecast", Numeric(18, 4), nullable=True),
        Column("Model", String(100), nullable=False),
        Column("Model_Details", String(100), nullable=False),
        Column("Mean_Absolute_Percentage_Error", Numeric(18, 6), nullable=True),
        Column("Mean_Absolute_Error", Numeric(18, 6), nullable=True),
        Column("Is_Best_Model", Boolean, nullable=True),
        Column("Outlier", Boolean, nullable=True),
        Column("Predicted_Best_Model_Bool", Boolean, nullable=True),
        Column("run_id", BigInteger, nullable=False),
        Column("warehouse_code", String(50), nullable=True),
        Column("created_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
        extend_existing=True,
    )


# ---------------------------------------------------------------------------
# Engine factory — delegates to LegacyOutputRepository (single pool).
# ---------------------------------------------------------------------------

def _get_reports_engine() -> Engine:
    """Alias kept for backward compatibility — delegates to the repository engine."""
    from app.services.forecasting.legacy_output_repository import _get_legacy_engine
    return _get_legacy_engine()


# ---------------------------------------------------------------------------
# LegacyOutputExporter
# ---------------------------------------------------------------------------

class LegacyOutputExporter:
    """
    Exports a completed forecast run into the legacy Vertex output table shape.

    Safe-replace flow:
        1. Write all rows for run_id into the staging table.
        2. Validate: staging count == forecast_results_weekly count.
        3. If safe_replace=True:
               TRUNCATE live_table;
               INSERT INTO live_table SELECT ... FROM staging WHERE run_id = :run_id;
        4. Return ExportResult with counts and validation outcome.

    Every batch is passed through map_forecast_result_to_legacy_row and
    validate_legacy_row before insert. Invalid rows are skipped and counted;
    duplicate legacy-key rows within the batch are also skipped. A full
    validation_summary is included in the return dict.
    """

    def __init__(
        self,
        staging_table: str | None = None,
        live_table: str | None = None,
    ) -> None:
        from app.config import settings

        self.staging_table = staging_table or getattr(
            settings, "legacy_output_staging_table",
            "aymes_demand_planning_forecast_by_model_new",
        )
        self.live_table = live_table or getattr(
            settings, "legacy_output_live_table",
            "aymes_demand_planning_forecast_by_model",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export_run(
        self,
        forecast_db: Session,
        run_id: int,
        *,
        safe_replace: bool | None = None,
    ) -> dict[str, Any]:
        """
        Export all forecast_results_weekly rows for run_id to the legacy table.

        Parameters
        ----------
        forecast_db   : MySQL forecast session (source of truth).
        run_id        : The run to export.
        safe_replace  : Override LEGACY_OUTPUT_SAFE_REPLACE for this call.

        Returns a dict with:
            rows_read, rows_written, rows_skipped, staging_count,
            valid, swapped, validation_summary, errors
        """
        from app.config import settings

        do_replace = safe_replace if safe_replace is not None else bool(
            getattr(settings, "legacy_output_safe_replace", False)
        )

        errors: list[str] = []
        rows_read    = 0
        rows_written = 0
        rows_skipped = 0
        staging_count = 0
        swapped = False
        seen_keys: set[tuple[Any, ...]] = set()
        combined_summary: dict[str, Any] = {
            "total_input": 0, "valid_rows": 0, "skipped_rows": 0,
            "duplicate_keys": 0, "warning_count": 0, "error_count": 0,
            "skipped_details": [],
        }

        engine = _get_reports_engine()
        staging_tbl = _make_legacy_table(self.staging_table)

        logger.info("LegacyOutputExporter: exporting run_id=%d → %s", run_id, self.staging_table)
        try:
            offset = 0
            with engine.begin() as conn:
                while True:
                    batch = self._read_batch(forecast_db, run_id, offset, _BATCH_SIZE)
                    if not batch:
                        break

                    valid_rows: list[dict[str, Any]] = []
                    for r in batch:
                        row = map_forecast_result_to_legacy_row(
                            product_code              = r.product_code,
                            product_name              = r.product_name,
                            inference_date            = r.inference_date,
                            forecast_week             = r.forecast_week,
                            actual_units              = r.actual_units,
                            interpolated_units        = r.interpolated_units,
                            forecast_units            = r.forecast_units,
                            model_name                = r.model_name,
                            model_details             = r.model_details,
                            mape                      = r.mape,
                            mae                       = r.mae,
                            is_best_model             = r.is_best_model,
                            outlier_flag              = r.outlier_flag,
                            predicted_best_model_bool = r.predicted_best_model_bool,
                            run_id                    = run_id,
                            warehouse_code            = r.warehouse_code,
                        )
                        validation = validate_legacy_row(row)

                        # Accumulate summary stats
                        combined_summary["total_input"] += 1
                        combined_summary["warning_count"] += len(validation.warnings)
                        combined_summary["error_count"]   += len(validation.errors)

                        if not validation.is_valid:
                            rows_skipped += 1
                            combined_summary["skipped_rows"] += 1
                            if len(combined_summary["skipped_details"]) < 50:
                                combined_summary["skipped_details"].append({
                                    "product_code":  str(r.product_code),
                                    "forecast_week": str(r.forecast_week),
                                    "model_details": str(r.model_details),
                                    "errors": validation.errors,
                                })
                            continue

                        # Duplicate key check across all batches
                        legacy_key = tuple(row.get(k) for k in _LEGACY_KEY)
                        if legacy_key in seen_keys:
                            rows_skipped += 1
                            combined_summary["skipped_rows"] += 1
                            combined_summary["duplicate_keys"] += 1
                            logger.warning(
                                "LegacyOutputExporter: duplicate legacy key skipped: %s", legacy_key
                            )
                            continue
                        seen_keys.add(legacy_key)

                        row.pop("_truncated", None)
                        valid_rows.append(row)

                    if valid_rows:
                        conn.execute(staging_tbl.insert(), valid_rows)
                        rows_written += len(valid_rows)

                    rows_read += len(batch)
                    offset += _BATCH_SIZE
                    logger.debug(
                        "LegacyOutputExporter: batch offset=%d read=%d written=%d skipped=%d",
                        offset, len(batch), rows_written, rows_skipped,
                    )

        except Exception as exc:
            msg = f"Failed writing to staging table: {exc}"
            logger.exception(msg)
            errors.append(msg)
            return {
                "rows_read": rows_read,
                "rows_written": rows_written,
                "rows_skipped": rows_skipped,
                "staging_count": 0,
                "valid": False,
                "swapped": False,
                "validation_summary": combined_summary,
                "errors": errors,
            }

        combined_summary["valid_rows"] = rows_written

        # Validate: staging count must match rows written
        try:
            with engine.connect() as conn:
                result = conn.execute(
                    text(f"SELECT COUNT(*) FROM {self.staging_table} WHERE run_id = :run_id"),  # noqa: S608
                    {"run_id": run_id},
                )
                staging_count = int(result.scalar() or 0)
        except Exception as exc:
            errors.append(f"Staging count validation failed: {exc}")

        valid = staging_count == rows_written and rows_written > 0
        if not valid:
            errors.append(
                f"Row count mismatch: staged={staging_count}, written={rows_written}. "
                "Safe-replace skipped."
            )

        # Safe-replace (optional, disabled by default)
        if do_replace and valid:
            try:
                swapped = self._promote_to_live(engine, run_id)
            except Exception as exc:
                msg = f"Safe-replace failed: {exc}"
                logger.exception(msg)
                errors.append(msg)

        logger.info(
            "LegacyOutputExporter: run_id=%d read=%d written=%d skipped=%d "
            "valid=%s swapped=%s warnings=%d errors_in_rows=%d",
            run_id, rows_read, rows_written, rows_skipped,
            valid, swapped,
            combined_summary["warning_count"],
            combined_summary["error_count"],
        )
        return {
            "rows_read":          rows_read,
            "rows_written":       rows_written,
            "rows_skipped":       rows_skipped,
            "staging_count":      staging_count,
            "valid":              valid,
            "swapped":            swapped,
            "validation_summary": combined_summary,
            "errors":             errors,
        }

    def ensure_schema(self) -> None:
        """Create the staging (and live) tables if they don't exist yet."""
        engine = _get_reports_engine()
        with engine.begin() as conn:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {self.staging_table} (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    AAH_Product_Code VARCHAR(50) NOT NULL,
                    Product_Name VARCHAR(255) NULL,
                    Inference_Date DATE NOT NULL,
                    Forecast_Week DATE NOT NULL,
                    Actual DECIMAL(18,4) NULL,
                    Interpolated_Values DECIMAL(18,4) NULL,
                    Forecast DECIMAL(18,4) NULL,
                    Model VARCHAR(100) NOT NULL,
                    Model_Details VARCHAR(100) NOT NULL,
                    Mean_Absolute_Percentage_Error DECIMAL(18,6) NULL,
                    Mean_Absolute_Error DECIMAL(18,6) NULL,
                    Is_Best_Model BOOLEAN NULL,
                    Outlier BOOLEAN NULL,
                    Predicted_Best_Model_Bool BOOLEAN NULL,
                    run_id BIGINT NOT NULL,
                    warehouse_code VARCHAR(50) NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    KEY idx_lcn_product_week (AAH_Product_Code, Forecast_Week),
                    KEY idx_lcn_run (run_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))  # noqa: S608
        logger.info("LegacyOutputExporter: ensured schema for %s", self.staging_table)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_batch(
        forecast_db: Session, run_id: int, offset: int, limit: int
    ) -> list[ForecastResultWeekly]:
        return (
            forecast_db.query(ForecastResultWeekly)
            .filter(ForecastResultWeekly.run_id == run_id)
            .order_by(
                ForecastResultWeekly.product_code,
                ForecastResultWeekly.forecast_week,
                ForecastResultWeekly.model_details,
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

    def _promote_to_live(self, engine: Engine, run_id: int) -> bool:
        """
        Promote rows from staging to the live table (TRUNCATE + INSERT SELECT).
        Matches the original Vertex pipeline's overwrite-per-inference behavior.
        """
        staging = self.staging_table
        live = self.live_table
        cols = (
            "AAH_Product_Code, Product_Name, Inference_Date, Forecast_Week, "
            "Actual, Interpolated_Values, Forecast, Model, Model_Details, "
            "Mean_Absolute_Percentage_Error, Mean_Absolute_Error, "
            "Is_Best_Model, Outlier, Predicted_Best_Model_Bool, "
            "run_id, warehouse_code"
        )
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {live}"))  # noqa: S608
            result = conn.execute(
                text(  # noqa: S608
                    f"INSERT INTO {live} ({cols}) "
                    f"SELECT {cols} FROM {staging} WHERE run_id = :run_id"
                ),
                {"run_id": run_id},
            )
            rows_promoted = result.rowcount
        logger.info(
            "LegacyOutputExporter: promoted %d rows from %s → %s",
            rows_promoted, staging, live,
        )
        return True
