"""Timeline view: lead time segments + markers (stockout, receipts, need-by). View-only."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.auth import require_any_auth
from app.models import PlanningPolicy, ProjectedInventory, Receipt
from pydantic import BaseModel

router = APIRouter(dependencies=[Depends(require_any_auth)])


def _week_start(d: date) -> date:
    """Monday as week start."""
    return d - timedelta(days=d.weekday())


def _parse_decimal_weeks(v: Decimal | None) -> float:
    if v is None:
        return 0.0
    return float(v)


class TimelineSegment(BaseModel):
    key: str
    label: str
    start_week_index: int
    duration_weeks: float
    tooltip: str


class TimelineMarker(BaseModel):
    key: str
    label: str
    week_index: int
    type: str  # stockout | receipt | need_by
    tooltip: str
    qty: str | None = None


class TimelineReceiptRow(BaseModel):
    week_start: str
    qty: str
    on_time: bool


class TimelineResponse(BaseModel):
    week_labels: list[str]
    segments: list[TimelineSegment]
    markers: list[TimelineMarker]
    receipts: list[TimelineReceiptRow]


@router.get("", response_model=TimelineResponse)
@router.get("/", response_model=TimelineResponse)
def get_timeline(
    sku: str = Query(..., description="SKU"),
    warehouse_code: str = Query(..., description="Warehouse code"),
    plan_run_id: int | None = Query(None, description="Optional plan run for stockout/projection"),
    horizon_weeks: int = Query(26, ge=1, le=104),
    db: Session = Depends(get_db),
) -> TimelineResponse:
    """Return timeline data: week labels, lead-time segments, markers (stockout, receipts, need-by), receipts table."""
    ref = date.today()
    week_start_ref = _week_start(ref)
    week_labels = [
        (week_start_ref + timedelta(weeks=i)).isoformat()
        for i in range(horizon_weeks)
    ]

    segments: list[TimelineSegment] = []
    policy = (
        db.query(PlanningPolicy)
        .filter(
            PlanningPolicy.sku == sku,
            PlanningPolicy.warehouse_code == warehouse_code,
        )
        .first()
    )
    if policy:
        prod = _parse_decimal_weeks(getattr(policy, "lead_time_production_weeks", None) or Decimal("0"))
        slot = _parse_decimal_weeks(getattr(policy, "lead_time_slot_wait_weeks", None) or Decimal("0"))
        haul = _parse_decimal_weeks(getattr(policy, "lead_time_haulage_weeks", None) or Decimal("0"))
        put = _parse_decimal_weeks(getattr(policy, "lead_time_putaway_weeks", None) or Decimal("0"))
        pad = _parse_decimal_weeks(getattr(policy, "lead_time_padding_weeks", None) or Decimal("0"))
        idx = 0
        if prod > 0:
            segments.append(TimelineSegment(key="production", label="Production", start_week_index=idx, duration_weeks=prod, tooltip=f"Production: {prod} weeks"))
            idx += int(round(prod))
        if slot > 0:
            segments.append(TimelineSegment(key="slot_wait", label="Slot wait", start_week_index=idx, duration_weeks=slot, tooltip=f"Slot wait: {slot} weeks"))
            idx += int(round(slot))
        if haul > 0:
            segments.append(TimelineSegment(key="haulage", label="Haulage", start_week_index=idx, duration_weeks=haul, tooltip=f"Haulage: {haul} weeks"))
            idx += int(round(haul))
        if put > 0:
            segments.append(TimelineSegment(key="putaway", label="Putaway", start_week_index=idx, duration_weeks=put, tooltip=f"Putaway: {put} weeks"))
            idx += int(round(put))
        if pad > 0:
            segments.append(TimelineSegment(key="padding", label="Padding", start_week_index=idx, duration_weeks=pad, tooltip=f"Padding: {pad} weeks"))

    markers: list[TimelineMarker] = []
    receipts_rows: list[TimelineReceiptRow] = []

    if plan_run_id:
        first_stockout = (
            db.query(ProjectedInventory)
            .filter(
                ProjectedInventory.plan_run_id == plan_run_id,
                ProjectedInventory.sku == sku,
                ProjectedInventory.warehouse_code == warehouse_code,
                ProjectedInventory.stockout == True,
            )
            .order_by(ProjectedInventory.week_start)
            .first()
        )
        if first_stockout is not None:
            week_start_val = getattr(first_stockout, "week_start", None)
            if week_start_val is not None:
                ws = week_start_val.isoformat() if hasattr(week_start_val, "isoformat") else str(week_start_val)
                try:
                    wi = week_labels.index(ws)
                    markers.append(TimelineMarker(key="stockout", label="Stockout", week_index=wi, type="stockout", tooltip=f"Projected stockout: {ws}"))
                except ValueError:
                    pass

    receipt_list = (
        db.query(Receipt)
        .filter(Receipt.sku == sku, Receipt.warehouse_code == warehouse_code)
        .order_by(Receipt.week_start)
        .all()
    )
    for r in receipt_list:
        ws = r.week_start.isoformat() if hasattr(r.week_start, "isoformat") else str(r.week_start)
        if ws in week_labels:
            wi = week_labels.index(ws)
            markers.append(TimelineMarker(key=f"receipt-{r.id}", label="Receipt", week_index=wi, type="receipt", tooltip=f"Receipt {r.qty} units, week {ws}", qty=str(r.qty)))
        receipts_rows.append(TimelineReceiptRow(week_start=ws, qty=str(r.qty), on_time=True))

    total_lt_weeks = sum(s.duration_weeks for s in segments)
    need_by_idx = min(int(round(total_lt_weeks)), horizon_weeks - 1)
    if segments:
        markers.append(TimelineMarker(key="need_by", label="Need by", week_index=need_by_idx, type="need_by", tooltip=f"Need-by week (order + {total_lt_weeks:.0f}w lead time)"))

    return TimelineResponse(week_labels=week_labels, segments=segments, markers=markers, receipts=receipts_rows)
