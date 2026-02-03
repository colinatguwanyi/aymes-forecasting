from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product as ProductModel
from app.schemas import Product, ProductCreate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=list[Product])
def list_products(db: Session = Depends(get_db)) -> list[ProductModel]:
    return db.query(ProductModel).all()


@router.post("/", response_model=Product)
def create_product(p: ProductCreate, db: Session = Depends(get_db)) -> ProductModel:
    existing = db.query(ProductModel).filter(ProductModel.sku == p.sku).first()
    if existing:
        raise HTTPException(status_code=400, detail="SKU already exists")
    obj = ProductModel(**p.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{product_id}", response_model=Product)
def get_product(product_id: int, db: Session = Depends(get_db)) -> ProductModel:
    obj = db.query(ProductModel).filter(ProductModel.id == product_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Product not found")
    return obj


@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    obj = db.query(ProductModel).filter(ProductModel.id == product_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}
