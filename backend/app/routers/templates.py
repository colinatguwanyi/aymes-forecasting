"""CSV template downloads for imports."""
from __future__ import annotations
import csv
import logging
from io import StringIO

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.security.auth import require_any_auth

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_any_auth)])


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


@router.get("/sku-code-map")
def template_sku_code_map() -> StreamingResponse:
    headers = ["old_sku", "new_sku", "effective_from_week_start", "effective_to_week_start", "notes"]
    rows = [
        ["LEGACY-SKU", "SKU001", "2025-01-01", "", "Merged into SKU001"],
    ]
    return _csv_response(headers, rows, "template_sku_code_map.csv")


@router.get("/demand-weekly")
def template_demand_weekly() -> StreamingResponse:
    """Demand weekly (W-TUE week_start); same schema as demand_actuals."""
    headers = ["week_start", "sku", "warehouse_code", "demand_type", "qty"]
    rows = [
        ["2025-02-04", "SKU001", "WH1", "CUSTOMER", "30"],
        ["2025-02-04", "SKU001", "WH1", "SAMPLES", "5"],
        ["2025-02-04", "SKU002", "WH1", "CUSTOMER", "20"],
    ]
    return _csv_response(headers, rows, "template_demand_weekly.csv")


@router.get("/demand-daily")
def template_demand_daily() -> StreamingResponse:
    """Demand daily (event_date); for daily staging if used."""
    headers = ["event_date", "sku", "warehouse_code", "demand_type", "qty", "source"]
    rows = [
        ["2025-02-04", "SKU001", "WH1", "CUSTOMER", "10", "CSV"],
        ["2025-02-05", "SKU001", "WH1", "CUSTOMER", "20", "CSV"],
    ]
    return _csv_response(headers, rows, "template_demand_daily.csv")


@router.get("/stock-on-hand")
def template_stock_on_hand() -> StreamingResponse:
    """SOH extract: Stock at (date), Branch Name, AAH Code, STOCK, ON ORDER. Header only; Branch Name must map to warehouse_code via warehouse_branch_mapping."""
    headers = ["Stock at", "Branch Name", "AAH Code", "STOCK", "ON ORDER", "Description"]
    rows: list[list[str]] = []
    return _csv_response(headers, rows, "template_stock_on_hand.csv")


@router.get("/product-master")
def template_product_master() -> StreamingResponse:
    """Product Master: suppliers, products, supplier_products, optional logistics/cost."""
    headers = [
        "Supplier",
        "SKU code",
        "AAH code",
        "Description",
        "Single Unit Content (g/ml)",
        "Selling Unit",
        "Single/Selling Unit",
        "Selling/Trade Unit",
        "Trade Unit",
        "Selling Unit/Pallet",
        "Single Units_MOQ",
        "Incremental Qty (Single Units)",
        "Supplier Leadtime",
        "Shelf Life",
        "AYMES Recipe (Y/N)",
        "Price_Unit",
        "COGs_Unit (Content)",
        "Curr",
        "COGs_ Selling Unit",
        "Product Family",
        "Pallet weight (Kg)",
        "Pallet Dimensions (WxDxH)",
        "HS Code",
        "Brand",
        "Ti-Hi",
    ]
    rows = [
        [
            "SUP001",
            "SKU001",
            "AAH001",
            "Product A description",
            "500",
            "Case",
            "12",
            "24",
            "Pallet",
            "100",
            "100",
            "12",
            "8 weeks",
            "12 months",
            "N",
            "1.50",
            "0.80",
            "GBP",
            "9.60",
            "Beverages",
            "500",
            "120x80x100",
            "22021000",
            "BrandX",
            "10x5",
        ],
    ]
    return _csv_response(headers, rows, "template_product_master.csv")
