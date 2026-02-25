r"""Product resolution for SOH ingestion: map BLP Code to canonical products.sku.

Priority:
  0) warehouse_product_codes lookup by (warehouse_code, external_code) where active=true
  1) exact match: products.sku == Code (case-sensitive)
  2) match: products.aah_code == Code
  3) extract HS code from Description via regex HSCODE:(\d+) and match product_master_attributes.hs_code
  4) if no match: return None (caller adds IngestionRejection)
"""
from __future__ import annotations

import re
from typing import cast

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Product, ProductMasterAttributes, WarehouseProductCode

HSCODE_RE = re.compile(r"HSCODE:(\d+)", re.IGNORECASE)


def resolve_code_to_sku(
    db: Session,
    code: str,
    description: str | None,
    warehouse_code: str | None = None,
) -> tuple[str | None, str]:
    """
    Resolve BLP Code (+ optional Description for HSCODE) to canonical products.sku.
    Returns (sku, resolution_method) or (None, "") if no match.
    resolution_method: "mapping_table" | "sku" | "aah_code" | "hs_code" | ""
    """
    code_clean = (code or "").strip()
    if not code_clean:
        return None, ""

    # 0) warehouse_product_codes lookup by (warehouse_code, external_code) where active=true
    if warehouse_code:
        wh_upper = warehouse_code.strip().upper()
        mapping = (
            db.query(WarehouseProductCode)
            .filter(
                func.upper(WarehouseProductCode.warehouse_code) == wh_upper,
                WarehouseProductCode.external_code == code_clean,
                WarehouseProductCode.active.is_(True),
            )
            .first()
        )
        if mapping:
            return cast(str, mapping.sku), "mapping_table"

    # 1) exact match: products.sku == Code (case-sensitive)
    p = db.query(Product).filter(Product.sku == code_clean).first()
    if p:
        return cast(str, p.sku), "sku"

    # 2) match: products.aah_code == Code (case-sensitive for consistency)
    p = db.query(Product).filter(Product.aah_code == code_clean).first()
    if p:
        return cast(str, p.sku), "aah_code"

    # 3) extract HSCODE from Description and match product_master_attributes.hs_code
    desc = (description or "").strip()
    if desc:
        m = HSCODE_RE.search(desc)
        if m:
            hs_val = m.group(1)
            attrs = (
                db.query(ProductMasterAttributes)
                .filter(ProductMasterAttributes.hs_code == hs_val)
                .first()
            )
            if attrs:
                return cast(str, attrs.sku), "hs_code"

    return None, ""
