"""CSV template downloads for imports."""
from __future__ import annotations
import csv
import logging
from io import StringIO

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _csv_response(headers: list[str], rows: list[list[str]], filename: str) -> StreamingResponse:
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for row in rows:
        w.writerow(row)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/inventory-snapshots")
def template_inventory_snapshots() -> StreamingResponse:
    headers = ["week_start", "sku", "warehouse_code", "on_hand_qty"]
    rows = [
        ["2025-02-03", "SKU001", "WH1", "100"],
        ["2025-02-03", "SKU002", "WH1", "50"],
    ]
    return _csv_response(headers, rows, "template_inventory_snapshots.csv")


@router.get("/receipts")
def template_receipts() -> StreamingResponse:
    headers = ["week_start", "sku", "warehouse_code", "qty", "source_type"]
    rows = [
        ["2025-02-10", "SKU001", "WH1", "200", "PO"],
        ["2025-02-17", "SKU002", "WH1", "100", "TRANSFER"],
    ]
    return _csv_response(headers, rows, "template_receipts.csv")


@router.get("/demand-actuals")
def template_demand_actuals() -> StreamingResponse:
    headers = ["week_start", "sku", "warehouse_code", "demand_type", "qty"]
    rows = [
        ["2025-02-03", "SKU001", "WH1", "CUSTOMER", "30"],
        ["2025-02-03", "SKU001", "WH1", "SAMPLES", "5"],
        ["2025-02-03", "SKU002", "WH1", "CUSTOMER", "20"],
    ]
    return _csv_response(headers, rows, "template_demand_actuals.csv")


@router.get("/samples-withdrawals")
def template_samples_withdrawals() -> StreamingResponse:
    headers = ["week_start", "sku", "warehouse_code", "qty"]
    rows = [
        ["2025-02-03", "SKU001", "WH1", "5"],
        ["2025-02-10", "SKU002", "WH1", "3"],
    ]
    return _csv_response(headers, rows, "template_samples_withdrawals.csv")


@router.get("/products")
def template_products() -> StreamingResponse:
    headers = ["sku", "name", "description"]
    rows = [
        ["SKU001", "Product A", "Description A"],
        ["SKU002", "Product B", "Description B"],
    ]
    return _csv_response(headers, rows, "template_products.csv")
