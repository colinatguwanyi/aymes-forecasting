from __future__ import annotations
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Receipt as ReceiptModel
from app.schemas import Receipt

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=list[Receipt])
def list_receipts(
    week_start: str | None = Query(None),
    sku: str | None = Query(None),
    warehouse_code: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[ReceiptModel]:
    q = db.query(ReceiptModel)
    if week_start:
        q = q.filter(ReceiptModel.week_start == datetime.fromisoformat(week_start).date())
    if sku:
        q = q.filter(ReceiptModel.sku == sku)
    if warehouse_code:
        q = q.filter(ReceiptModel.warehouse_code == warehouse_code)
    return q.order_by(ReceiptModel.week_start, ReceiptModel.sku).all()
