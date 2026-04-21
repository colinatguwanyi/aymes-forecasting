from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.auth import require_any_auth
from app.models import (
    InventorySnapshotWeekly,
    Lane,
    StockPositionWeekly,
    Warehouse as WarehouseModel,
    WarehouseProduct,
)
from app.schemas import Warehouse, WarehouseCreate

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_any_auth)])


def _warehouse_ids_with_positive_stock(db: Session) -> set[int]:
    rows = (
        db.query(StockPositionWeekly.warehouse_id)
        .filter(StockPositionWeekly.on_hand_units > 0)
        .distinct()
        .all()
    )
    return {int(r[0]) for r in rows}


def _warehouse_codes_with_positive_soh(db: Session) -> set[str]:
    rows = (
        db.query(InventorySnapshotWeekly.warehouse_code)
        .filter(InventorySnapshotWeekly.on_hand_qty > 0)
        .distinct()
        .all()
    )
    return {str(r[0]) for r in rows}


def _has_stock(db: Session, wh: WarehouseModel, ids_stock: set[int], codes_soh: set[str]) -> bool:
    return wh.id in ids_stock or wh.code in codes_soh


def _to_warehouse_schema(wh: WarehouseModel, has_stock: bool) -> Warehouse:
    base = Warehouse.model_validate(wh)
    return base.model_copy(update={"has_stock": has_stock})


@router.get("", response_model=list[Warehouse])
@router.get("/", response_model=list[Warehouse])
def list_warehouses(db: Session = Depends(get_db)) -> list[Warehouse]:
    rows = db.query(WarehouseModel).order_by(WarehouseModel.code).all()
    ids_stock = _warehouse_ids_with_positive_stock(db)
    codes_soh = _warehouse_codes_with_positive_soh(db)
    return [_to_warehouse_schema(wh, _has_stock(db, wh, ids_stock, codes_soh)) for wh in rows]


@router.post("", response_model=Warehouse)
@router.post("/", response_model=Warehouse)
def create_warehouse(w: WarehouseCreate, db: Session = Depends(get_db)) -> Warehouse:
    existing = db.query(WarehouseModel).filter(WarehouseModel.code == w.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Warehouse code already exists")
    obj = WarehouseModel(**w.model_dump(exclude={"has_stock"}, exclude_none=False))
    db.add(obj)
    db.commit()
    db.refresh(obj)
    ids_stock = _warehouse_ids_with_positive_stock(db)
    codes_soh = _warehouse_codes_with_positive_soh(db)
    return _to_warehouse_schema(obj, _has_stock(db, obj, ids_stock, codes_soh))


@router.get("/{warehouse_id}", response_model=Warehouse)
def get_warehouse(warehouse_id: int, db: Session = Depends(get_db)) -> Warehouse:
    obj = db.query(WarehouseModel).filter(WarehouseModel.id == warehouse_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    ids_stock = _warehouse_ids_with_positive_stock(db)
    codes_soh = _warehouse_codes_with_positive_soh(db)
    return _to_warehouse_schema(obj, _has_stock(db, obj, ids_stock, codes_soh))


@router.put("/{warehouse_id}", response_model=Warehouse)
def update_warehouse(warehouse_id: int, w: WarehouseCreate, db: Session = Depends(get_db)) -> Warehouse:
    obj = db.query(WarehouseModel).filter(WarehouseModel.id == warehouse_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    if w.code != obj.code:
        clash = db.query(WarehouseModel).filter(WarehouseModel.code == w.code, WarehouseModel.id != warehouse_id).first()
        if clash:
            raise HTTPException(status_code=400, detail="Warehouse code already exists")
    for k, v in w.model_dump(exclude={"has_stock"}).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    ids_stock = _warehouse_ids_with_positive_stock(db)
    codes_soh = _warehouse_codes_with_positive_soh(db)
    return _to_warehouse_schema(obj, _has_stock(db, obj, ids_stock, codes_soh))


@router.delete("/{warehouse_id}")
def delete_warehouse(warehouse_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    obj = db.query(WarehouseModel).filter(WarehouseModel.id == warehouse_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    if obj.active:
        raise HTTPException(
            status_code=400,
            detail="Warehouse is still active. Set it to inactive first, then delete.",
        )
    ids_stock = _warehouse_ids_with_positive_stock(db)
    codes_soh = _warehouse_codes_with_positive_soh(db)
    if _has_stock(db, obj, ids_stock, codes_soh):
        raise HTTPException(
            status_code=400,
            detail="Cannot delete: inventory snapshots or stock positions still show quantity > 0 for this warehouse.",
        )
    lanes_n = db.query(Lane).filter(Lane.warehouse_id == warehouse_id).count()
    if lanes_n:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete: remove {lanes_n} supplier lane(s) pointing to this warehouse first.",
        )
    whp_n = db.query(WarehouseProduct).filter(WarehouseProduct.warehouse_id == warehouse_id).count()
    if whp_n:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete: remove {whp_n} warehouse–product link(s) first.",
        )
    try:
        db.delete(obj)
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.warning("Warehouse delete blocked by FK: %s", e)
        raise HTTPException(
            status_code=409,
            detail="Cannot delete: warehouse is still referenced by other records (planning data, etc.).",
        ) from e
    return {"ok": True}
