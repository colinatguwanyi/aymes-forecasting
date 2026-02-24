"""Sales Out ingestion: stage CSV/XLSX -> canonical weekly demand (demand_actuals, W-TUE)."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import (
    DemandActual,
    DemandFactsWeekly,
    DemandType,
    IngestionMode,
    IngestionRejection,
    IngestionRun,
    IngestionStatus,
    Product,
    SalesOutStage,
)
from app.services.csv_import import parse_date_ddmmyyyy
from app.services.time_bucketing import week_start_for_date

logger = logging.getLogger(__name__)

SALES_OUT_WAREHOUSE = "AAH"
HISTORICAL_BATCH_WEEKS = 8

# Column name variants (strip and case-insensitive match)
def _get(row: dict[str, Any], *keys: str) -> Any:
    row_lower = {str(k).strip().lower(): v for k, v in row.items()}
    for k in keys:
        k_lower = k.strip().lower()
        if k_lower in row_lower and row_lower[k_lower] not in (None, ""):
            return row_lower[k_lower]
    return None


def _decimal_val(s: Any) -> Decimal | None:
    if s is None or s == "":
        return None
    try:
        return Decimal(str(s).strip())
    except Exception:
        return None


def _int_val(s: Any) -> int | None:
    if s is None or s == "":
        return None
    try:
        return int(float(str(s).strip()))
    except Exception:
        return None


def validate_and_stage_sales_out_row(
    db: Session,
    run_id: UUID,
    row: dict[str, Any],
    row_number: int,
) -> tuple[bool, str | None]:
    """Parse one row, insert into sales_out_stage or ingestion_rejections. Return (staged_ok, reason_if_rejected)."""
    aah = _get(row, "AAH_Product_Code", "aah_product_code")
    if not aah or not str(aah).strip():
        return False, "AAH_Product_Code required"
    aah_str = str(aah).strip()

    date_ok, date_val = parse_date_ddmmyyyy(str(_get(row, "Business_Processed_Date", "business_processed_date") or ""))
    if not date_ok:
        return False, str(date_val)

    processed_date = cast(date, date_val)
    raw_json = dict(row) if row else None

    db.add(
        SalesOutStage(
            ingestion_run_id=run_id,
            aah_product_code=aah_str,
            account_code=str(_get(row, "Account_Code", "account_code") or "").strip() or None,
            customer_name=str(_get(row, "Delivery_Address_Line_1", "delivery_address_line_1") or "").strip() or None,
            postcode=str(_get(row, "Delivery_Address_Postcode", "delivery_address_postcode") or "").strip() or None,
            customer_sector=str(_get(row, "Customer_Business_Sector_Name", "customer_business_sector_name") or "").strip() or None,
            pip_code=str(_get(row, "PIP_Code", "pip_code") or "").strip() or None,
            product_name=str(_get(row, "Product_Name", "product_name") or "").strip() or None,
            item_size=str(_get(row, "Item_Size", "item_size") or "").strip() or None,
            invoiced_qty=_decimal_val(_get(row, "Invoiced_Qty", "invoiced_qty")),
            servings_qty=_decimal_val(_get(row, "Servings_Qty", "servings_qty")),
            net_sales_value=_decimal_val(_get(row, "Net_Sales_Value", "net_sales_value")),
            processed_date=processed_date,
            processed_year=_int_val(_get(row, "Business_Processed_Year", "business_processed_year")),
            print_branch=str(_get(row, "Print_Branch", "print_branch") or "").strip() or None,
            branch=str(_get(row, "Branch", "branch") or "").strip() or None,
            raw_json=raw_json,
        )
    )
    return True, None


def build_demand_from_sales_out(db: Session, run_id: UUID) -> tuple[int, int, int]:
    """
    Transform sales_out_stage for run_id into demand_actuals (W-TUE weekly, warehouse=AAH, demand_type=CUSTOMER).
    - Join stage to products on products.aah_code = stage.aah_product_code; reject unknown_aah_code.
    - Week bucket processed_date via week_start_for_date.
    - Idempotent: delete from demand_actuals the (week_start, sku, AAH, CUSTOMER) keys we are about to write, then insert.
    Returns (rows_staged, weeks_written, rows_rejected).
    """
    run = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
    if not run:
        raise ValueError(f"Ingestion run not found: {run_id}")
    if getattr(run, "entity", None) and getattr(run.entity, "value", None) != "sales_out":
        raise ValueError(f"Run entity is {getattr(run.entity, 'value', run.entity)}, expected sales_out")

    run.status = IngestionStatus.RUNNING
    db.flush()

    stage_rows = (
        db.query(SalesOutStage)
        .filter(SalesOutStage.ingestion_run_id == run_id)
        .all()
    )

    # aah_code -> sku (products)
    aah_to_sku: dict[str, str] = {}
    for p in db.query(Product).filter(Product.aah_code.isnot(None)).all():
        ac = (getattr(p, "aah_code", None) or "").strip()
        if ac:
            aah_to_sku[ac] = cast(str, p.sku)

    # Aggregate: (week_start, sku) -> (sum invoiced_qty, sum servings_qty, sum net_sales_value, count)
    aggregated: dict[tuple[date, str], tuple[Decimal, Decimal, Decimal, int]] = defaultdict(
        lambda: (Decimal("0"), Decimal("0"), Decimal("0"), 0)
    )
    rejected = 0

    for row in stage_rows:
        aah = (getattr(row, "aah_product_code", None) or "").strip()
        sku = aah_to_sku.get(aah)
        if not sku:
            db.add(
                IngestionRejection(
                    ingestion_run_id=run_id,
                    row_number=cast(int, row.id),
                    raw_payload={"aah_product_code": aah, "processed_date": str(cast(date, row.processed_date))},
                    reason="unknown_aah_code",
                )
            )
            rejected += 1
            continue
        week_start = week_start_for_date(cast(date, row.processed_date))
        _inv = getattr(row, "invoiced_qty", None)
        _serv = getattr(row, "servings_qty", None)
        _net = getattr(row, "net_sales_value", None)
        inv_qty = cast(Decimal, _inv) if _inv is not None else Decimal("0")
        serv_qty = cast(Decimal, _serv) if _serv is not None else Decimal("0")
        net_val = cast(Decimal, _net) if _net is not None else Decimal("0")
        key = (week_start, sku)
        prev_inv, prev_serv, prev_net, prev_cnt = aggregated[key]
        aggregated[key] = (
            prev_inv + inv_qty,
            prev_serv + serv_qty,
            prev_net + net_val,
            prev_cnt + 1,
        )

    # Group by week for batch processing (historical mode)
    weeks_sorted = sorted({k[0] for k in aggregated.keys()})
    mode = getattr(run, "mode", None)
    is_historical = mode == IngestionMode.HISTORICAL

    weeks_written = 0
    if is_historical and len(weeks_sorted) > HISTORICAL_BATCH_WEEKS:
        # Chunked: process batches of weeks, commit each batch
        progress: dict[str, int | str] = {"batches_done": 0, "weeks_done": 0}
        for i in range(0, len(weeks_sorted), HISTORICAL_BATCH_WEEKS):
            batch_weeks = weeks_sorted[i : i + HISTORICAL_BATCH_WEEKS]
            batch_keys = [(w, s) for (w, s) in aggregated.keys() if w in batch_weeks]
            for (week_start, sku) in batch_keys:
                db.query(DemandActual).filter(
                    DemandActual.week_start == week_start,
                    DemandActual.sku == sku,
                    DemandActual.warehouse_code == SALES_OUT_WAREHOUSE,
                    DemandActual.demand_type == DemandType.CUSTOMER,
                ).delete(synchronize_session=False)
                db.query(DemandFactsWeekly).filter(
                    DemandFactsWeekly.week_start == week_start,
                    DemandFactsWeekly.sku == sku,
                    DemandFactsWeekly.warehouse_code == SALES_OUT_WAREHOUSE,
                    DemandFactsWeekly.demand_type == DemandType.CUSTOMER,
                ).delete(synchronize_session=False)
            for (week_start, sku) in batch_keys:
                inv_qty = aggregated[(week_start, sku)][0]
                db.add(
                    DemandActual(
                        week_start=week_start,
                        sku=sku,
                        warehouse_code=SALES_OUT_WAREHOUSE,
                        demand_type=DemandType.CUSTOMER,
                        qty=inv_qty,
                    )
                )
                db.add(
                    DemandFactsWeekly(
                        week_start=week_start,
                        sku=sku,
                        warehouse_code=SALES_OUT_WAREHOUSE,
                        demand_type=DemandType.CUSTOMER,
                        qty=inv_qty,
                        source_run_id=run_id,
                        is_imputed=False,
                        is_outlier=False,
                    )
                )
                weeks_written += 1
            db.flush()
            progress["batches_done"] = (i // HISTORICAL_BATCH_WEEKS) + 1
            progress["weeks_done"] = weeks_written
            run.progress_meta = {**(run.progress_meta or {}), **progress}
    else:
        # Weekly mode or small historical: single transaction
        keys_to_write = list(aggregated.keys())
        for (week_start, sku) in keys_to_write:
            db.query(DemandActual).filter(
                DemandActual.week_start == week_start,
                DemandActual.sku == sku,
                DemandActual.warehouse_code == SALES_OUT_WAREHOUSE,
                DemandActual.demand_type == DemandType.CUSTOMER,
            ).delete(synchronize_session=False)
            db.query(DemandFactsWeekly).filter(
                DemandFactsWeekly.week_start == week_start,
                DemandFactsWeekly.sku == sku,
                DemandFactsWeekly.warehouse_code == SALES_OUT_WAREHOUSE,
                DemandFactsWeekly.demand_type == DemandType.CUSTOMER,
            ).delete(synchronize_session=False)
        for (week_start, sku), (inv_qty, _serv, _net, _cnt) in aggregated.items():
            db.add(
                DemandActual(
                    week_start=week_start,
                    sku=sku,
                    warehouse_code=SALES_OUT_WAREHOUSE,
                    demand_type=DemandType.CUSTOMER,
                    qty=inv_qty,
                )
            )
            db.add(
                DemandFactsWeekly(
                    week_start=week_start,
                    sku=sku,
                    warehouse_code=SALES_OUT_WAREHOUSE,
                    demand_type=DemandType.CUSTOMER,
                    qty=inv_qty,
                    source_run_id=run_id,
                    is_imputed=False,
                    is_outlier=False,
                )
            )
            weeks_written += 1

    run.inserted_count = weeks_written
    run.updated_count = 0
    run.rejected_count = rejected
    run.status = IngestionStatus.SUCCESS
    run.error_summary = None
    run.finished_at = datetime.now(timezone.utc)
    run.row_count = len(stage_rows)
    db.flush()
    logger.info(
        "build_demand_from_sales_out: run_id=%s staged=%s weeks_written=%s rejected=%s",
        run_id, len(stage_rows), weeks_written, rejected,
    )
    return len(stage_rows), weeks_written, rejected
