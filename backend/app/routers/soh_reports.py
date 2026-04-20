"""SOH History reports: series, summary, and grid from inventory_snapshots_weekly."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import InventorySnapshotWeekly, Product
from app.security.auth import require_any_auth

router = APIRouter(dependencies=[Depends(require_any_auth)])


def _parse_date(s: str | None) -> date | None:
    if not s or not str(s).strip():
        return None
    try:
        return datetime.strptime(str(s).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


@router.get("/series")
def soh_series(
    warehouse_code: str = Query(..., description="Warehouse (e.g. AAH)"),
    sku: str = Query(..., description="SKU (required to avoid huge datasets)"),
    week_start_from: str | None = Query(None, description="YYYY-MM-DD (inclusive)"),
    week_start_to: str | None = Query(None, description="YYYY-MM-DD (inclusive)"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Time series of on_hand_units by week_start for a given warehouse and SKU.
    Matches inventory by product.sku or product.aah_code (AAH SOH imports use aah_code)."""
    wh = warehouse_code.strip().upper()
    sku_clean = sku.strip()
    if not sku_clean:
        raise HTTPException(status_code=400, detail="sku is required")
    # Resolve: inventory may store aah_code; include both sku and aah_code for lookup
    inv_keys = [sku_clean]
    product = db.query(Product.aah_code).filter(Product.sku == sku_clean).first()
    if product and product.aah_code and str(product.aah_code).strip():
        inv_keys.append(str(product.aah_code).strip())
    q = (
        db.query(InventorySnapshotWeekly)
        .filter(
            func.upper(InventorySnapshotWeekly.warehouse_code) == wh,
            InventorySnapshotWeekly.sku.in_(inv_keys),
        )
    )
    d_from = _parse_date(week_start_from)
    d_to = _parse_date(week_start_to)
    if d_from is not None:
        q = q.filter(InventorySnapshotWeekly.week_start >= d_from)
    if d_to is not None:
        q = q.filter(InventorySnapshotWeekly.week_start <= d_to)
    rows = q.order_by(InventorySnapshotWeekly.week_start.asc()).all()
    out = []
    for r in rows:
        qty = r.on_hand_qty
        if isinstance(qty, Decimal):
            qty = float(qty)
        out.append({
            "week_start": r.week_start.isoformat() if r.week_start else None,
            "on_hand_units": qty,
            "on_order_units": None,  # weekly table has no on_order
        })
    return out


@router.get("/summary")
def soh_summary(
    warehouse_code: str = Query(...),
    week_start_from: str | None = Query(None),
    week_start_to: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Top SKUs by latest on_hand_units and biggest week-over-week deltas in range."""
    wh = warehouse_code.strip().upper()
    q = db.query(InventorySnapshotWeekly).filter(
        func.upper(InventorySnapshotWeekly.warehouse_code) == wh,
    )
    d_from = _parse_date(week_start_from)
    d_to = _parse_date(week_start_to)
    if d_from is not None:
        q = q.filter(InventorySnapshotWeekly.week_start >= d_from)
    if d_to is not None:
        q = q.filter(InventorySnapshotWeekly.week_start <= d_to)
    rows = q.order_by(InventorySnapshotWeekly.week_start.asc()).all()
    # (sku, week_start) -> on_hand_qty
    by_sku_week: dict[str, list[tuple[date, float]]] = {}
    for r in rows:
        sku = r.sku
        ws = r.week_start
        qty = float(r.on_hand_qty) if isinstance(r.on_hand_qty, Decimal) else r.on_hand_qty
        if sku not in by_sku_week:
            by_sku_week[sku] = []
        by_sku_week[sku].append((ws, qty))
    # Latest on_hand per SKU (last week in range)
    top_by_latest: list[dict[str, Any]] = []
    for sku, points in by_sku_week.items():
        if not points:
            continue
        points_sorted = sorted(points, key=lambda x: x[0])
        last_week, last_qty = points_sorted[-1]
        top_by_latest.append({"sku": sku, "week_start": last_week.isoformat(), "on_hand_units": last_qty})
    top_by_latest.sort(key=lambda x: x["on_hand_units"], reverse=True)
    top_by_latest = top_by_latest[:limit]
    # Biggest deltas (week-over-week change)
    top_by_delta: list[dict[str, Any]] = []
    for sku, points in by_sku_week.items():
        points_sorted = sorted(points, key=lambda x: x[0])
        for i in range(1, len(points_sorted)):
            prev_week, prev_qty = points_sorted[i - 1]
            curr_week, curr_qty = points_sorted[i]
            delta = curr_qty - prev_qty
            top_by_delta.append({
                "sku": sku,
                "week_start": curr_week.isoformat(),
                "on_hand_units": curr_qty,
                "delta": delta,
            })
    top_by_delta.sort(key=lambda x: abs(x["delta"]), reverse=True)
    top_by_delta = top_by_delta[:limit]
    return {
        "top_by_latest": top_by_latest,
        "top_by_delta": top_by_delta,
    }


def _week_starts_for_anchor(anchor: date, n: int) -> list[date]:
    """Generate n week_starts ending at anchor, most-recent first (anchor, anchor-7, ...)."""
    return [anchor - timedelta(weeks=i) for i in range(n)]


@router.get("/grid")
def soh_grid(
    warehouse_code: str = Query(..., description="Warehouse (e.g. AAH)"),
    weeks: int = Query(12, ge=1, le=26, description="Number of weeks to include"),
    anchor_week_start: str | None = Query(None, description="YYYY-MM-DD; if omitted, use latest available"),
    q: str | None = Query(None, description="Search SKU or name"),
    limit: int = Query(50, ge=1, le=200, description="Rows per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    active_only: bool = Query(True, description="Only include active products"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """All-products SOH history grid: rows = products, columns = week_starts, values = on_hand_qty.
    week_starts ordered most-recent first. Missing weeks return 0."""
    wh = warehouse_code.strip().upper()
    if not wh:
        raise HTTPException(status_code=400, detail="warehouse_code is required")

    # Resolve anchor week
    anchor: date | None = None
    if anchor_week_start:
        anchor = _parse_date(anchor_week_start)
        if anchor is None:
            raise HTTPException(status_code=400, detail="anchor_week_start must be YYYY-MM-DD")
    if anchor is None:
        max_row = (
            db.query(func.max(InventorySnapshotWeekly.week_start))
            .filter(func.upper(InventorySnapshotWeekly.warehouse_code) == wh)
            .scalar()
        )
        anchor = max_row

    if anchor is None:
        return {
            "warehouse_code": wh,
            "anchor_week_start": None,
            "week_starts": [],
            "total_products": 0,
            "rows": [],
        }

    week_starts = _week_starts_for_anchor(anchor, weeks)

    # Step A: products page (SKUs with filters); include aah_code for inventory lookup
    products_q = db.query(Product.sku, Product.name, Product.aah_code).filter(Product.active == active_only)
    if q and q.strip():
        q_lower = f"%{q.strip().lower()}%"
        products_q = products_q.filter(
            or_(
                func.lower(Product.sku).like(q_lower),
                func.lower(func.coalesce(Product.name, "")).like(q_lower),
            )
        )
    # Count total for pagination
    total_products = products_q.count()
    # Page
    products_q = products_q.order_by(Product.sku).offset(offset).limit(limit)
    product_rows = products_q.all()

    # Build lookup: inventory.sku (AAH code or canonical) -> product.sku for our page
    inv_sku_to_product_sku: dict[str, str] = {}
    inv_lookup_keys: set[str] = set()
    for r in product_rows:
        inv_lookup_keys.add(r.sku)
        inv_sku_to_product_sku[r.sku] = r.sku
        aah = (r.aah_code or "").strip() if r.aah_code else ""
        if aah:
            inv_lookup_keys.add(aah)
            inv_sku_to_product_sku[aah] = r.sku

    if not product_rows:
        return {
            "warehouse_code": wh,
            "anchor_week_start": anchor.isoformat(),
            "week_starts": [d.isoformat() for d in week_starts],
            "total_products": total_products,
            "rows": [],
        }

    # Step B: facts for inventory SKUs that match our products (by sku or aah_code) + week_starts
    facts = (
        db.query(InventorySnapshotWeekly.sku, InventorySnapshotWeekly.week_start, InventorySnapshotWeekly.on_hand_qty)
        .filter(
            func.upper(InventorySnapshotWeekly.warehouse_code) == wh,
            InventorySnapshotWeekly.week_start.in_(week_starts),
            InventorySnapshotWeekly.sku.in_(inv_lookup_keys),
        )
        .all()
    )

    # Build (product_sku, week_start) -> qty; map inventory sku (AAH or canonical) to product sku
    fact_map: dict[tuple[str, date], float] = {}
    for r in facts:
        product_sku = inv_sku_to_product_sku.get(r.sku)
        if product_sku is not None:
            qty = float(r.on_hand_qty) if isinstance(r.on_hand_qty, Decimal) else r.on_hand_qty
            fact_map[(product_sku, r.week_start)] = qty

    # Build rows aligned with week_starts (most-recent first)
    rows: list[dict[str, Any]] = []
    for r in product_rows:
        values = [fact_map.get((r.sku, ws), 0) for ws in week_starts]
        rows.append({"sku": r.sku, "name": r.name or "", "values": values})

    return {
        "warehouse_code": wh,
        "anchor_week_start": anchor.isoformat(),
        "week_starts": [d.isoformat() for d in week_starts],
        "total_products": total_products,
        "rows": rows,
    }
