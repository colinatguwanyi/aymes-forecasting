"""Sales reports: grid from demand_facts_weekly (CUSTOMER = Sales Out)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DemandFactsWeekly, DemandType, Product
from app.security.auth import require_any_auth

router = APIRouter(dependencies=[Depends(require_any_auth)])


def _parse_date(s: str | None) -> date | None:
    if not s or not str(s).strip():
        return None
    try:
        return datetime.strptime(str(s).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _week_starts_for_anchor(anchor: date, n: int) -> list[date]:
    """Generate n week_starts ending at anchor, most-recent first (anchor, anchor-7, ...)."""
    return [anchor - timedelta(weeks=i) for i in range(n)]


def _parse_demand_type(s: str | None) -> DemandType:
    """Parse demand_type string; default CUSTOMER."""
    if not s or not str(s).strip():
        return DemandType.CUSTOMER
    u = str(s).strip().upper()
    if u == "CUSTOMER":
        return DemandType.CUSTOMER
    if u == "SAMPLES":
        return DemandType.SAMPLES
    if u == "ADJUSTMENT":
        return DemandType.ADJUSTMENT
    return DemandType.CUSTOMER


@router.get("/grid")
def sales_grid(
    warehouse_code: str = Query(..., description="Warehouse (e.g. AAH)"),
    weeks: int = Query(12, ge=1, le=26, description="Number of weeks to include"),
    anchor_week_start: str | None = Query(None, description="YYYY-MM-DD; if omitted, use latest available"),
    q: str | None = Query(None, description="Search SKU or name"),
    limit: int = Query(50, ge=1, le=200, description="Rows per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    active_only: bool = Query(True, description="Only include active products"),
    demand_type: str | None = Query(None, description="CUSTOMER (default), SAMPLES, ADJUSTMENT"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """All-products sales grid from demand_facts_weekly. Rows = products, columns = week_starts, values = qty.
    Sales = demand_type CUSTOMER. week_starts ordered most-recent first. Missing weeks return 0."""
    wh = warehouse_code.strip().upper()
    if not wh:
        raise HTTPException(status_code=400, detail="warehouse_code is required")

    dt_enum = _parse_demand_type(demand_type)

    # Resolve anchor week
    anchor: date | None = None
    if anchor_week_start:
        anchor = _parse_date(anchor_week_start)
        if anchor is None:
            raise HTTPException(status_code=400, detail="anchor_week_start must be YYYY-MM-DD")
    if anchor is None:
        max_row = (
            db.query(func.max(DemandFactsWeekly.week_start))
            .filter(
                func.upper(DemandFactsWeekly.warehouse_code) == wh,
                DemandFactsWeekly.demand_type == dt_enum,
            )
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

    # Products page (SKUs with filters)
    products_q = db.query(Product.sku, Product.name).filter(Product.active == active_only)
    if q and q.strip():
        q_lower = f"%{q.strip().lower()}%"
        products_q = products_q.filter(
            or_(
                func.lower(Product.sku).like(q_lower),
                func.lower(func.coalesce(Product.name, "")).like(q_lower),
            )
        )
    total_products = products_q.count()
    products_q = products_q.order_by(Product.sku).offset(offset).limit(limit)
    product_rows = products_q.all()

    if not product_rows:
        return {
            "warehouse_code": wh,
            "anchor_week_start": anchor.isoformat(),
            "week_starts": [d.isoformat() for d in week_starts],
            "total_products": total_products,
            "rows": [],
        }

    sku_list = [r.sku for r in product_rows]

    # Facts for those SKUs and weeks
    facts = (
        db.query(DemandFactsWeekly.sku, DemandFactsWeekly.week_start, func.sum(DemandFactsWeekly.qty).label("qty_sum"))
        .filter(
            func.upper(DemandFactsWeekly.warehouse_code) == wh,
            DemandFactsWeekly.demand_type == dt_enum,
            DemandFactsWeekly.week_start.in_(week_starts),
            DemandFactsWeekly.sku.in_(sku_list),
        )
        .group_by(DemandFactsWeekly.sku, DemandFactsWeekly.week_start)
        .all()
    )

    fact_map: dict[tuple[str, date], float] = {}
    for r in facts:
        qty = float(r.qty_sum) if isinstance(r.qty_sum, Decimal) else r.qty_sum
        fact_map[(r.sku, r.week_start)] = qty

    rows: list[dict[str, Any]] = []
    for r in product_rows:
        values = [fact_map.get((r.sku, ws), 0) for ws in week_starts]
        latest = values[0] if values else 0
        total = sum(values)
        rows.append({"sku": r.sku, "name": r.name or "", "values": values, "latest": latest, "total": total})

    return {
        "warehouse_code": wh,
        "anchor_week_start": anchor.isoformat(),
        "week_starts": [d.isoformat() for d in week_starts],
        "total_products": total_products,
        "rows": rows,
    }
