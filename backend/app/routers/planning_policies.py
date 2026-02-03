from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PlanningPolicy as PlanningPolicyModel
from app.schemas import PlanningPolicy, PlanningPolicyCreate

logger = logging.getLogger(__name__)
router = APIRouter()


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
