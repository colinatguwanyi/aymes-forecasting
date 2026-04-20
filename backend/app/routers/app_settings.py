"""Admin app settings: sample_sales_soh_warehouses and other key-value config."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.auth import require_admin
from app.services.app_settings import set_setting

router = APIRouter(dependencies=[Depends(require_admin)])


class SampleSalesSohWarehousesBody(BaseModel):
    warehouse_codes: list[str]


@router.get("/sample-sales-soh-warehouses")
def get_sample_sales_soh_warehouses(db: Session = Depends(get_db)) -> dict:
    """Get warehouse codes used for sample sales SOH filter. Default ['BLP']."""
    from app.services.app_settings import get_sample_sales_soh_warehouses

    return {"warehouse_codes": get_sample_sales_soh_warehouses(db)}


@router.put("/sample-sales-soh-warehouses")
def put_sample_sales_soh_warehouses(
    body: SampleSalesSohWarehousesBody,
    db: Session = Depends(get_db),
) -> dict:
    """Set warehouse codes for sample sales SOH filter. Must be list of non-empty strings."""
    codes = [str(c).strip() for c in body.warehouse_codes if str(c).strip()]
    if not codes:
        raise HTTPException(
            status_code=400,
            detail="At least one warehouse code required",
        )
    set_setting(db, "sample_sales_soh_warehouses", codes)
    db.commit()
    return {"warehouse_codes": codes}
