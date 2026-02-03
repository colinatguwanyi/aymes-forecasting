from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Warehouse as WarehouseModel
from app.schemas import Warehouse, WarehouseCreate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=list[Warehouse])
def list_warehouses(db: Session = Depends(get_db)) -> list[WarehouseModel]:
    return db.query(WarehouseModel).all()


@router.post("/", response_model=Warehouse)
def create_warehouse(w: WarehouseCreate, db: Session = Depends(get_db)) -> WarehouseModel:
    existing = db.query(WarehouseModel).filter(WarehouseModel.code == w.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Warehouse code already exists")
    obj = WarehouseModel(**w.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{warehouse_id}", response_model=Warehouse)
def get_warehouse(warehouse_id: int, db: Session = Depends(get_db)) -> WarehouseModel:
    obj = db.query(WarehouseModel).filter(WarehouseModel.id == warehouse_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return obj


@router.delete("/{warehouse_id}")
def delete_warehouse(warehouse_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    obj = db.query(WarehouseModel).filter(WarehouseModel.id == warehouse_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}
