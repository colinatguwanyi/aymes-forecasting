from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Lane as LaneModel
from app.schemas import Lane, LaneCreate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=list[Lane])
def list_lanes(db: Session = Depends(get_db)) -> list[LaneModel]:
    return db.query(LaneModel).all()


@router.post("/", response_model=Lane)
def create_lane(l: LaneCreate, db: Session = Depends(get_db)) -> LaneModel:
    obj = LaneModel(**l.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{lane_id}", response_model=Lane)
def get_lane(lane_id: int, db: Session = Depends(get_db)) -> LaneModel:
    obj = db.query(LaneModel).filter(LaneModel.id == lane_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Lane not found")
    return obj


@router.delete("/{lane_id}")
def delete_lane(lane_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    obj = db.query(LaneModel).filter(LaneModel.id == lane_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Lane not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}
