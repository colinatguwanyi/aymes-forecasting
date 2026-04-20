"""Backbone: supplier_products by supplier."""
from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SupplierProduct as SupplierProductModel, Supplier, Product
from app.schemas import SupplierProduct, SupplierProductCreate, SupplierProductUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=list[SupplierProduct])
@router.get("/", response_model=list[SupplierProduct])
def list_supplier_products(
    supplier_id: int = Query(..., description="Filter by supplier"),
    db: Session = Depends(get_db),
) -> list[SupplierProductModel]:
    if not db.query(Supplier).filter(Supplier.id == supplier_id).first():
        raise HTTPException(status_code=404, detail="Supplier not found")
    return (
        db.query(SupplierProductModel)
        .filter(SupplierProductModel.supplier_id == supplier_id)
        .order_by(SupplierProductModel.product_id)
        .all()
    )


@router.post("", response_model=SupplierProduct)
@router.post("/", response_model=SupplierProduct)
def create_supplier_product(
    body: SupplierProductCreate,
    db: Session = Depends(get_db),
) -> SupplierProductModel:
    if not db.query(Supplier).filter(Supplier.id == body.supplier_id).first():
        raise HTTPException(status_code=404, detail="Supplier not found")
    if not db.query(Product).filter(Product.id == body.product_id).first():
        raise HTTPException(status_code=404, detail="Product not found")
    existing = (
        db.query(SupplierProductModel)
        .filter(
            SupplierProductModel.supplier_id == body.supplier_id,
            SupplierProductModel.product_id == body.product_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Supplier-product already exists")
    obj = SupplierProductModel(**body.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{supplier_product_id}", response_model=SupplierProduct)
def get_supplier_product(
    supplier_product_id: int,
    db: Session = Depends(get_db),
) -> SupplierProductModel:
    obj = db.query(SupplierProductModel).filter(SupplierProductModel.id == supplier_product_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Supplier-product not found")
    return obj


@router.put("/{supplier_product_id}", response_model=SupplierProduct)
def update_supplier_product(
    supplier_product_id: int,
    body: SupplierProductUpdate,
    db: Session = Depends(get_db),
) -> SupplierProductModel:
    obj = db.query(SupplierProductModel).filter(SupplierProductModel.id == supplier_product_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Supplier-product not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{supplier_product_id}")
def delete_supplier_product(
    supplier_product_id: int,
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    obj = db.query(SupplierProductModel).filter(SupplierProductModel.id == supplier_product_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Supplier-product not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}
