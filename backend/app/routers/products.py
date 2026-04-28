from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.auth import require_any_auth
from app.models import Product as ProductModel
from app.schemas import Product, ProductCreate

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_any_auth)])


@router.get("", response_model=list[Product])
@router.get("/", response_model=list[Product])
def list_products(db: Session = Depends(get_db)) -> list[ProductModel]:
    return db.query(ProductModel).all()


@router.post("", response_model=Product)
@router.post("/", response_model=Product)
def create_product(_p: ProductCreate, _db: Session = Depends(get_db)) -> ProductModel:
    raise HTTPException(
        status_code=403,
        detail=(
            "Direct product creation is disabled. Add or update SKUs via product master ingestion "
            "(ingestion upload with entity=product_master)."
        ),
    )


@router.get("/{product_id}", response_model=Product)
def get_product(product_id: int, db: Session = Depends(get_db)) -> ProductModel:
    obj = db.query(ProductModel).filter(ProductModel.id == product_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Product not found")
    return obj


@router.put("/{product_id}", response_model=Product)
def update_product(product_id: int, p: ProductCreate, db: Session = Depends(get_db)) -> ProductModel:
    obj = db.query(ProductModel).filter(ProductModel.id == product_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Product not found")
    for k, v in p.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    obj = db.query(ProductModel).filter(ProductModel.id == product_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}
