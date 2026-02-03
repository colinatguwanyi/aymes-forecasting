from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Supplier as SupplierModel
from app.schemas import Supplier, SupplierCreate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=list[Supplier])
def list_suppliers(db: Session = Depends(get_db)) -> list[SupplierModel]:
    return db.query(SupplierModel).all()


@router.post("/", response_model=Supplier)
def create_supplier(s: SupplierCreate, db: Session = Depends(get_db)) -> SupplierModel:
    existing = db.query(SupplierModel).filter(SupplierModel.code == s.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Supplier code already exists")
    obj = SupplierModel(**s.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{supplier_id}", response_model=Supplier)
def get_supplier(supplier_id: int, db: Session = Depends(get_db)) -> SupplierModel:
    obj = db.query(SupplierModel).filter(SupplierModel.id == supplier_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return obj


@router.delete("/{supplier_id}")
def delete_supplier(supplier_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    obj = db.query(SupplierModel).filter(SupplierModel.id == supplier_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Supplier not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}
