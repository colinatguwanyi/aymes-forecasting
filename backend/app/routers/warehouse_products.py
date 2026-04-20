"""Backbone: warehouse_products planning parameters by warehouse."""
from __future__ import annotations
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.auth import require_any_auth
from app.models import WarehouseProduct as WarehouseProductModel, Warehouse, Product
from app.schemas import WarehouseProduct, WarehouseProductCreate, WarehouseProductUpdate

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_any_auth)])


@router.get("", response_model=list[WarehouseProduct])
@router.get("/", response_model=list[WarehouseProduct])
def list_warehouse_products(
    warehouse_id: int = Query(..., description="Filter by warehouse"),
    db: Session = Depends(get_db),
) -> list[WarehouseProductModel]:
    if not db.query(Warehouse).filter(Warehouse.id == warehouse_id).first():
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return (
        db.query(WarehouseProductModel)
        .filter(WarehouseProductModel.warehouse_id == warehouse_id)
        .order_by(WarehouseProductModel.product_id)
        .all()
    )


@router.post("", response_model=WarehouseProduct)
@router.post("/", response_model=WarehouseProduct)
def create_warehouse_product(
    body: WarehouseProductCreate,
    db: Session = Depends(get_db),
) -> WarehouseProductModel:
    if not db.query(Warehouse).filter(Warehouse.id == body.warehouse_id).first():
        raise HTTPException(status_code=404, detail="Warehouse not found")
    if not db.query(Product).filter(Product.id == body.product_id).first():
        raise HTTPException(status_code=404, detail="Product not found")
    existing = (
        db.query(WarehouseProductModel)
        .filter(
            WarehouseProductModel.warehouse_id == body.warehouse_id,
            WarehouseProductModel.product_id == body.product_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Warehouse-product already exists")
    data = body.model_dump()
    data["safety_stock_weeks"] = Decimal(str(data["safety_stock_weeks"])) if data.get("safety_stock_weeks") is not None else None
    obj = WarehouseProductModel(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{warehouse_product_id}", response_model=WarehouseProduct)
def get_warehouse_product(
    warehouse_product_id: int,
    db: Session = Depends(get_db),
) -> WarehouseProductModel:
    obj = db.query(WarehouseProductModel).filter(WarehouseProductModel.id == warehouse_product_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Warehouse-product not found")
    return obj


@router.put("/{warehouse_product_id}", response_model=WarehouseProduct)
def update_warehouse_product(
    warehouse_product_id: int,
    body: WarehouseProductUpdate,
    db: Session = Depends(get_db),
) -> WarehouseProductModel:
    obj = db.query(WarehouseProductModel).filter(WarehouseProductModel.id == warehouse_product_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Warehouse-product not found")
    data = body.model_dump(exclude_unset=True)
    if "safety_stock_weeks" in data and data["safety_stock_weeks"] is not None:
        data["safety_stock_weeks"] = Decimal(str(data["safety_stock_weeks"]))
    for k, v in data.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{warehouse_product_id}")
def delete_warehouse_product(
    warehouse_product_id: int,
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    obj = db.query(WarehouseProductModel).filter(WarehouseProductModel.id == warehouse_product_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Warehouse-product not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}
