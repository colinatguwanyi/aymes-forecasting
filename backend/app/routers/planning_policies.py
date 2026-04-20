from __future__ import annotations
import logging
from decimal import Decimal
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.auth import require_admin_or_planner, require_any_auth
from app.models import PlanningPolicy as PlanningPolicyModel, Product
from app.schemas import PlanningPolicy, PlanningPolicyCreate

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_any_auth)])


@router.get("", response_model=list[PlanningPolicy])
@router.get("/", response_model=list[PlanningPolicy])
def list_planning_policies(
    sku: str | None = Query(None),
    warehouse_code: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[PlanningPolicyModel]:
    q = db.query(PlanningPolicyModel)
    if sku:
        q = q.filter(PlanningPolicyModel.sku == sku)
    if warehouse_code:
        q = q.filter(PlanningPolicyModel.warehouse_code == warehouse_code)
    return q.all()


@router.post("", response_model=PlanningPolicy)
@router.post("/", response_model=PlanningPolicy)
def create_planning_policy(p: PlanningPolicyCreate, db: Session = Depends(get_db)) -> PlanningPolicyModel:
    existing = (
        db.query(PlanningPolicyModel)
        .filter(
            PlanningPolicyModel.sku == p.sku,
            PlanningPolicyModel.warehouse_code == p.warehouse_code,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Policy for this SKU/warehouse already exists")
    obj = PlanningPolicyModel(**p.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{policy_id}", response_model=PlanningPolicy)
def get_planning_policy(policy_id: int, db: Session = Depends(get_db)) -> PlanningPolicyModel:
    obj = db.query(PlanningPolicyModel).filter(PlanningPolicyModel.id == policy_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Planning policy not found")
    return obj


@router.put("/{policy_id}", response_model=PlanningPolicy)
def update_planning_policy(policy_id: int, p: PlanningPolicyCreate, db: Session = Depends(get_db)) -> PlanningPolicyModel:
    obj = db.query(PlanningPolicyModel).filter(PlanningPolicyModel.id == policy_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Planning policy not found")
    for k, v in p.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{policy_id}")
def delete_planning_policy(policy_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    obj = db.query(PlanningPolicyModel).filter(PlanningPolicyModel.id == policy_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Planning policy not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.post("/generate-defaults", dependencies=[Depends(require_admin_or_planner)])
def generate_default_policies(
    warehouse_code: str = Query(..., description="Warehouse code (e.g. AAH)"),
    default_target_weeks: float = Query(4, ge=0, le=52),
    default_safety_stock_weeks: float = Query(1, ge=0, le=52),
    default_lead_time_weeks: float = Query(2, ge=0, le=52),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """Create default planning policies for every active product that has no policy for the warehouse."""
    wh = warehouse_code.strip().upper()
    if not wh:
        raise HTTPException(status_code=400, detail="warehouse_code is required")
    existing = {
        (cast(str, p.sku), cast(str, p.warehouse_code))
        for p in db.query(PlanningPolicyModel).filter(PlanningPolicyModel.warehouse_code == wh).all()
    }
    products = db.query(Product).filter(Product.active.is_(True)).all()
    created = 0
    for p in products:
        sku = cast(str, p.sku)
        if (sku, wh) in existing:
            continue
        db.add(
            PlanningPolicyModel(
                sku=sku,
                warehouse_code=wh,
                target_weeks=Decimal(str(default_target_weeks)),
                safety_stock_weeks=Decimal(str(default_safety_stock_weeks)),
                lead_time_production_weeks=Decimal(str(default_lead_time_weeks)),
                lead_time_slot_wait_weeks=Decimal("0"),
                lead_time_haulage_weeks=Decimal("0"),
                lead_time_putaway_weeks=Decimal("0"),
                lead_time_padding_weeks=Decimal("0"),
            )
        )
        created += 1
        existing.add((sku, wh))
    db.commit()
    return {"created": created}
