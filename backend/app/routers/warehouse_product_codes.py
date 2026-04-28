"""Admin API: Warehouse Product Codes (external_code → sku mapping per warehouse)."""
from __future__ import annotations

import csv
import io
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import IngestionRejection, Product, WarehouseProductCode
from app.schemas import (
    WarehouseProductCodeCreate,
    WarehouseProductCodeResponse,
    WarehouseProductCodeUpdate,
)
from app.security.auth import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("", response_model=list[WarehouseProductCodeResponse])
def list_warehouse_product_codes(
    warehouse_code: str | None = Query(None, description="Filter by warehouse"),
    q: str | None = Query(None, description="Search external_code or sku"),
    active_only: bool = Query(True, description="Only active mappings"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[WarehouseProductCodeResponse]:
    """List warehouse product code mappings with optional filters."""
    qry = db.query(WarehouseProductCode)
    if warehouse_code:
        qry = qry.filter(func.upper(WarehouseProductCode.warehouse_code) == warehouse_code.strip().upper())
    if active_only:
        qry = qry.filter(WarehouseProductCode.active.is_(True))
    if q:
        q = q.strip()
        qry = qry.filter(
            or_(
                WarehouseProductCode.external_code.ilike(f"%{q}%"),
                WarehouseProductCode.sku.ilike(f"%{q}%"),
                WarehouseProductCode.external_name.ilike(f"%{q}%"),
            )
        )
    qry = qry.order_by(WarehouseProductCode.warehouse_code, WarehouseProductCode.external_code)
    rows = qry.offset(offset).limit(limit).all()
    return [WarehouseProductCodeResponse.model_validate(r) for r in rows]


@router.post("", response_model=WarehouseProductCodeResponse)
def create_warehouse_product_code(
    body: WarehouseProductCodeCreate,
    db: Session = Depends(get_db),
) -> WarehouseProductCodeResponse:
    """Create a new mapping."""
    wh = body.warehouse_code.strip().upper()
    ext = body.external_code.strip()
    sku = body.sku.strip()
    product = db.query(Product).filter(Product.sku == sku).first()
    if not product:
        raise HTTPException(status_code=400, detail=f"Product sku '{sku}' not found")
    existing = (
        db.query(WarehouseProductCode)
        .filter(
            func.upper(WarehouseProductCode.warehouse_code) == wh,
            WarehouseProductCode.external_code == ext,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Mapping already exists for this warehouse_code + external_code")
    row = WarehouseProductCode(
        warehouse_code=wh,
        external_code=ext,
        sku=sku,
        external_name=body.external_name,
        hs_code=body.hs_code,
        active=body.active,
        match_method=body.match_method,
        match_confidence=body.match_confidence,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return WarehouseProductCodeResponse.model_validate(row)


@router.put("/{id}", response_model=WarehouseProductCodeResponse)
def update_warehouse_product_code(
    id: int,
    body: WarehouseProductCodeUpdate,
    db: Session = Depends(get_db),
) -> WarehouseProductCodeResponse:
    """Update a mapping."""
    row = db.query(WarehouseProductCode).filter(WarehouseProductCode.id == id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if body.sku is not None:
        product = db.query(Product).filter(Product.sku == body.sku.strip()).first()
        if not product:
            raise HTTPException(status_code=400, detail=f"Product sku '{body.sku}' not found")
        row.sku = body.sku.strip()
    if body.external_name is not None:
        row.external_name = body.external_name
    if body.hs_code is not None:
        row.hs_code = body.hs_code
    if body.active is not None:
        row.active = body.active
    if body.match_method is not None:
        row.match_method = body.match_method
    if body.match_confidence is not None:
        row.match_confidence = body.match_confidence
    db.commit()
    db.refresh(row)
    return WarehouseProductCodeResponse.model_validate(row)


@router.delete("/{id}")
def delete_warehouse_product_code(
    id: int,
    soft: bool = Query(True, description="Soft delete (active=false) vs hard delete"),
    db: Session = Depends(get_db),
) -> dict:
    """Delete or deactivate a mapping."""
    row = db.query(WarehouseProductCode).filter(WarehouseProductCode.id == id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if soft:
        row.active = False
        db.commit()
        return {"deleted": False, "active": False}
    db.delete(row)
    db.commit()
    return {"deleted": True}


@router.post("/bulk")
def bulk_upload_warehouse_product_codes(
    file: UploadFile,
    warehouse_code: str = Query(..., description="Warehouse for all rows"),
    db: Session = Depends(get_db),
) -> dict:
    """Bulk create/update mappings from CSV. Columns: external_code, sku, external_name, hs_code."""
    wh = warehouse_code.strip().upper()
    content = file.file.read()
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        text = content.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    required = {"external_code", "sku"}
    created = updated = errors = 0
    for i, row in enumerate(reader):
        if not all(row.get(k) for k in required):
            errors += 1
            continue
        ext = str(row["external_code"]).strip()
        sku = str(row["sku"]).strip()
        product = db.query(Product).filter(Product.sku == sku).first()
        if not product:
            errors += 1
            continue
        existing = (
            db.query(WarehouseProductCode)
            .filter(
                WarehouseProductCode.warehouse_code == wh,
                WarehouseProductCode.external_code == ext,
            )
            .first()
        )
        ext_name = (row.get("external_name") or "").strip() or None
        hs = (row.get("hs_code") or "").strip() or None
        if existing:
            existing.sku = sku
            existing.external_name = ext_name
            existing.hs_code = hs
            existing.active = True
            updated += 1
        else:
            db.add(
                WarehouseProductCode(
                    warehouse_code=wh,
                    external_code=ext,
                    sku=sku,
                    external_name=ext_name,
                    hs_code=hs,
                    active=True,
                )
            )
            created += 1
    db.commit()
    return {"created": created, "updated": updated, "errors": errors}


def _fetch_unmapped_codes(
    db: Session,
    warehouse_code: str,
    import_run_id: UUID | None,
) -> dict:
    """Fetch unmapped codes from product_not_found rejections."""
    import re
    from app.models import IngestionEntity, IngestionRun, IngestionStatus

    wh = warehouse_code.strip().upper()
    if import_run_id:
        run = db.query(IngestionRun).filter(IngestionRun.id == import_run_id).first()
    else:
        run = (
            db.query(IngestionRun)
            .filter(
                IngestionRun.entity == IngestionEntity.STOCK_ON_HAND,
                IngestionRun.status.in_([IngestionStatus.SUCCESS, IngestionStatus.PENDING]),
            )
            .order_by(IngestionRun.started_at.desc())
            .first()
        )
    if not run:
        return {"unmapped": [], "import_run_id": None, "warehouse_code": wh}
    rejs = (
        db.query(IngestionRejection)
        .filter(
            IngestionRejection.ingestion_run_id == run.id,
            or_(
                IngestionRejection.reason == "product_not_found",
                IngestionRejection.reason.startswith("Unmapped SKU:"),
            ),
        )
        .all()
    )
    by_code: dict[str, dict[str, Any]] = {}
    for r in rejs:
        payload = r.raw_payload or {}
        code = (payload.get("Code") or payload.get("code") or "").strip()
        if not code:
            continue
        desc = (payload.get("Description") or payload.get("description") or "").strip() or None
        qty = 0
        try:
            qty = int(float(str(payload.get("Balance") or payload.get("balance") or 0)))
        except (ValueError, TypeError):
            pass
        if code not in by_code:
            by_code[code] = {"external_code": code, "description": desc, "qty_sum": 0, "sample_rows": 0}
        by_code[code]["qty_sum"] += qty
        by_code[code]["sample_rows"] += 1
    hscode_re = re.compile(r"HSCODE:(\d+)", re.IGNORECASE)
    for v in by_code.values():
        desc = v.get("description") or ""
        m = hscode_re.search(desc)
        v["hs_code_guess"] = m.group(1) if m else None
    return {
        "import_run_id": str(run.id),
        "warehouse_code": wh,
        "unmapped": list(by_code.values()),
    }


@router.get("/unmapped")
def get_unmapped_codes(
    warehouse_code: str = Query(..., description="Warehouse"),
    import_run_id: UUID | None = Query(None, description="Specific run; else latest SOH run for warehouse"),
    db: Session = Depends(get_db),
) -> dict:
    """Return unmapped external codes from ingestions (product_not_found rejections)."""
    return _fetch_unmapped_codes(db, warehouse_code, import_run_id)


@router.get("/unmapped/csv")
def download_unmapped_codes_csv(
    warehouse_code: str = Query(...),
    import_run_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Download unmapped codes as CSV."""
    data = _fetch_unmapped_codes(db, warehouse_code, import_run_id)
    rows = data.get("unmapped", [])
    buf = io.StringIO()
    w = csv.DictWriter(
        buf,
        fieldnames=["warehouse_code", "external_code", "description", "hs_code_guess", "qty_sum", "sample_rows_count"],
        extrasaction="ignore",
    )
    w.writeheader()
    wh = data.get("warehouse_code", warehouse_code)
    for r in rows:
        w.writerow({
            "warehouse_code": wh,
            "external_code": r.get("external_code", ""),
            "description": r.get("description", ""),
            "hs_code_guess": r.get("hs_code_guess", ""),
            "qty_sum": r.get("qty_sum", 0),
            "sample_rows_count": r.get("sample_rows", 0),
        })
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=unmapped_codes.csv"},
    )
