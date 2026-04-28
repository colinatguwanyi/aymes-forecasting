"""
Product Master ingestion: parse CSV into products, suppliers, supplier_products, product_master_attributes.
Idempotent upserts by sku/code/(supplier_id, product_id). Rejections captured at stage time.

Canonical SKU: products.sku = TRIM(row["SKU code"]), case preserved. Never use AAH code as key.
AAH code: reference only (nullable). Never used for joins. NULL if blank/NA/N/A/-/null (case-insensitive).
"""
from __future__ import annotations

import re
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, cast
from uuid import UUID

from sqlalchemy.orm import Session

from app.ingestion_progress import merge_ingest_progress
from app.models import (
    IngestionRun,
    Product,
    ProductMasterAttributes,
    ProductMasterStage,
    Supplier,
    SupplierProduct,
)

logger = logging.getLogger(__name__)

# Values that must be treated as NULL for aah_code (case-insensitive). Do NOT use aah_code for joins.
_AAH_NULL_VALUES = frozenset({"na", "n/a", "-", "null", ""})


def _normalize_aah_code(value: str | None) -> str | None:
    """
    AAH code: reference field only. Returns None if blank or in NA/N/A/-/null (case-insensitive).
    Otherwise returns trimmed value with case preserved. Never use for joins.
    """
    if value is None:
        return None
    v = str(value).strip()
    if not v or v.lower() in _AAH_NULL_VALUES:
        return None
    return v


def _get_sku_code(row: dict[str, Any]) -> str:
    """Canonical SKU from row: TRIM(SKU code), case preserved. Reject if blank after trim."""
    for k in ("SKU code", "sku_code", "SKU", "sku"):
        if k in row:
            v = row[k]
            if v is None:
                return ""
            return str(v).strip()
    return ""


# CSV column name variants (first match wins); for non-SKU fields
def _get(row: dict[str, Any], *keys: str) -> str:
    for k in keys:
        if k in row and row[k] is not None:
            v = str(row[k]).strip()
            if v and v.upper() not in ("NA", "N/A", ""):
                return v
    return ""


def _get_optional(row: dict[str, Any], *keys: str) -> str | None:
    v = _get(row, *keys)
    return v if v else None


def _parse_decimal(s: str) -> tuple[bool, Decimal | None, str]:
    s = (s or "").strip()
    if not s or s.upper() in ("NA", "N/A"):
        return True, None, ""
    try:
        return True, Decimal(s), ""
    except (InvalidOperation, ValueError):
        return False, None, f"Invalid number: {s!r}"


def _parse_int(s: str) -> tuple[bool, int | None, str]:
    s = (s or "").strip()
    if not s or s.upper() in ("NA", "N/A"):
        return True, None, ""
    try:
        return True, int(Decimal(s)), ""
    except (InvalidOperation, ValueError):
        return False, None, f"Invalid integer: {s!r}"


_LEADTIME_RE = re.compile(r"^\s*(\d+)\s*(?:weeks?)?\s*$", re.IGNORECASE)


def _parse_leadtime_weeks(s: str) -> tuple[bool, int | None, str]:
    s = (s or "").strip()
    if not s or s.upper() in ("NA", "N/A"):
        return True, None, ""
    m = _LEADTIME_RE.match(s)
    if m:
        return True, int(m.group(1)), ""
    return False, None, f"Leadtime not parseable (e.g. '8 weeks'): {s!r}"


def _is_recipe_yes(s: str) -> bool:
    return (s or "").strip().upper() in ("Y", "YES", "1", "TRUE")


def _detect_content_uom(header_content: str, selling_unit: str) -> str:
    """Infer content UOM from 'Single Unit Content (g/ml)' header or selling unit text."""
    if "g/ml" in (header_content or "").lower() or "g" in (header_content or "").lower():
        if "ml" in (selling_unit or "").lower():
            return "ml"
        return "g"
    if "ml" in (selling_unit or "").lower():
        return "ml"
    return "g"


def validate_and_stage_row(
    db: Session,
    run_id: UUID,
    row: dict[str, Any],
    row_number: int,
) -> tuple[bool, str]:
    """
    Validate one product master row. If valid, add to product_master_stage; else add to ingestion_rejections.
    Returns (staged, reason). reason empty if staged.
    """
    from app.models import IngestionRejection

    errs: list[str] = []
    supplier = _get(row, "Supplier", "supplier")
    sku_code = _get_sku_code(row)  # TRIM only; preserve case; reject if blank
    description = _get(row, "Description", "description", "name")
    if not sku_code:
        errs.append("SKU code required (use column 'SKU code', 'sku_code', 'SKU', or 'sku')")
    if not description:
        errs.append("Description required (use column 'Description', 'description', or 'name')")
    # Supplier optional: if missing, import_from_stage uses 'DEFAULT'
    if errs:
        db.add(
            IngestionRejection(
                ingestion_run_id=run_id,
                row_number=row_number,
                raw_payload=dict(row),
                reason="; ".join(errs),
            )
        )
        return False, "; ".join(errs)

    # Optional numerics: reject only if present and unparseable
    single_content_str = _get(row, "Single Unit Content (g/ml)", "Single Unit Content (g/ml)")
    if single_content_str:
        ok, _, msg = _parse_decimal(single_content_str)
        if not ok:
            errs.append(msg)
    moq_str = _get(row, "Single Units_MOQ", "Single Units_MOQ")
    if moq_str:
        ok, _, msg = _parse_int(moq_str)
        if not ok:
            errs.append(msg)
    incr_str = _get(row, "Incremental Qty (Single Units)", "Incremental Qty (Single Units)")
    if incr_str:
        ok, _, msg = _parse_int(incr_str)
        if not ok:
            errs.append(msg)
    lt_str = _get(row, "Supplier Leadtime", "Supplier Leadtime")
    if lt_str:
        ok, _, msg = _parse_leadtime_weeks(lt_str)
        if not ok:
            errs.append(msg)
    if errs:
        db.add(
            IngestionRejection(
                ingestion_run_id=run_id,
                row_number=row_number,
                raw_payload=dict(row),
                reason="; ".join(errs),
            )
        )
        return False, "; ".join(errs)

    db.add(
        ProductMasterStage(
            ingestion_run_id=run_id,
            row_number=row_number,
            payload=dict(row),
        )
    )
    return True, ""


def import_from_stage(db: Session, run_id: UUID) -> tuple[int, int]:
    """
    Read product_master_stage for run_id; upsert suppliers, products, supplier_products, product_master_attributes.
    Returns (inserted_count, updated_count) for reporting.
    """
    _run = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
    if _run:
        merge_ingest_progress(
            db,
            _run,
            import_phase="product_master",
            import_message="Writing product master to catalog tables…",
        )
    rows = (
        db.query(ProductMasterStage)
        .filter(ProductMasterStage.ingestion_run_id == run_id)
        .order_by(ProductMasterStage.row_number)
        .all()
    )
    inserted = 0
    updated = 0
    for stage_row in rows:
        row = cast(dict[str, Any], stage_row.payload)
        supplier_code = (_get(row, "Supplier", "supplier") or "DEFAULT").strip()
        sku_code = _get_sku_code(row)  # Canonical SKU: TRIM(SKU code), case preserved. Never from AAH.
        description = _get(row, "Description", "description", "name").strip()
        if not sku_code:
            continue

        # A) Upsert supplier
        supplier = db.query(Supplier).filter(Supplier.code == supplier_code).first()
        if not supplier:
            supplier = Supplier(code=supplier_code, name=supplier_code, active=True)
            db.add(supplier)
            db.flush()
            inserted += 1
        # else: existing, no update count for supplier

        # B) Upsert product
        product = db.query(Product).filter(Product.sku == sku_code).first()
        # AAH code: reference only (nullable). Never use for joins. NULL if blank/NA/N/A/-/null (case-insensitive).
        aah_raw = row.get("AAH code") or row.get("aah_code") or ""
        aah_code = _normalize_aah_code(aah_raw)
        selling_unit_text = _get_optional(row, "Selling Unit", "Selling Unit")
        single_content_str = _get(row, "Single Unit Content (g/ml)", "Single Unit Content (g/ml)")
        single_unit_content, content_uom = None, None
        if single_content_str:
            ok, dec, _ = _parse_decimal(single_content_str)
            if ok and dec is not None:
                single_unit_content = dec
                content_uom = _detect_content_uom(
                    row.get("Single Unit Content (g/ml)", ""),
                    selling_unit_text or "",
                )
        brand = _get_optional(row, "Brand", "Brand")
        product_family = _get_optional(row, "Product Family", "Product Family")
        recipe_str = _get(row, "AYMES Recipe (Y/N)", "AYMES Recipe (Y/N)")
        is_recipe = _is_recipe_yes(recipe_str)

        if not product:
            product = Product(
                sku=sku_code,
                name=description,
                description=description,
                uom="units",
                active=True,
                aah_code=aah_code,
                brand=brand,
                product_family=product_family,
                selling_unit_text=selling_unit_text,
                single_unit_content=single_unit_content,
                content_uom=content_uom,
                is_recipe=is_recipe,
            )
            db.add(product)
            db.flush()
            inserted += 1
        else:
            product.name = description
            product.description = description
            product.aah_code = aah_code
            product.brand = brand
            product.product_family = product_family
            product.selling_unit_text = selling_unit_text
            product.single_unit_content = single_unit_content
            product.content_uom = content_uom
            product.is_recipe = is_recipe
            updated += 1

        # C) Upsert supplier_products
        link = (
            db.query(SupplierProduct)
            .filter(
                SupplierProduct.supplier_id == supplier.id,
                SupplierProduct.product_id == product.id,
            )
            .first()
        )
        lead_ok, lead_weeks, _ = _parse_leadtime_weeks(_get(row, "Supplier Leadtime", "Supplier Leadtime"))
        moq_ok, moq_units, _ = _parse_int(_get(row, "Single Units_MOQ", "Single Units_MOQ"))
        incr_ok, pack_size, _ = _parse_int(_get(row, "Incremental Qty (Single Units)", "Incremental Qty (Single Units)"))
        if not link:
            link = SupplierProduct(
                supplier_id=supplier.id,
                product_id=product.id,
                lead_time_weeks=lead_weeks if lead_ok and lead_weeks is not None else 0,
                moq_units=moq_units if moq_ok else None,
                pack_size_units=pack_size if incr_ok else None,
                active=True,
            )
            db.add(link)
            inserted += 1
        else:
            if lead_ok and lead_weeks is not None:
                link.lead_time_weeks = lead_weeks
            if moq_ok:
                link.moq_units = moq_units
            if incr_ok:
                link.pack_size_units = pack_size
            updated += 1

        # D) Upsert product_master_attributes
        shelf_life = _get_optional(row, "Shelf Life", "Shelf Life")
        hs_code = _get_optional(row, "HS Code", "HS Code")
        pallet_weight_ok, pallet_weight_kg, _ = _parse_decimal(_get(row, "Pallet weight (Kg)", "Pallet weight (Kg)"))
        pallet_dims = _get_optional(row, "Pallet Dimensions (WxDxH)", "Pallet Dimensions (WxDxH)")
        ti_hi = _get_optional(row, "Ti-Hi", "Ti-Hi")
        price_ok, price_unit, _ = _parse_decimal(_get(row, "Price_Unit", "Price_Unit"))
        cogs_ok, cogs_unit, _ = _parse_decimal(_get(row, "COGs_Unit (Content)", "COGs_Unit (Content)"))
        cogs_sell_ok, cogs_selling_unit, _ = _parse_decimal(_get(row, "COGs_ Selling Unit", "COGs_ Selling Unit"))
        currency = _get_optional(row, "Curr", "Curr")

        attrs = db.query(ProductMasterAttributes).filter(ProductMasterAttributes.sku == sku_code).first()
        if not attrs:
            attrs = ProductMasterAttributes(
                sku=sku_code,
                shelf_life_text=shelf_life,
                hs_code=hs_code,
                pallet_weight_kg=Decimal(str(pallet_weight_kg)) if pallet_weight_ok and pallet_weight_kg is not None else None,
                pallet_dimensions_text=pallet_dims,
                ti_hi=ti_hi,
                price_unit=Decimal(str(price_unit)) if price_ok and price_unit is not None else None,
                cogs_unit=Decimal(str(cogs_unit)) if cogs_ok and cogs_unit is not None else None,
                cogs_selling_unit=Decimal(str(cogs_selling_unit)) if cogs_sell_ok and cogs_selling_unit is not None else None,
                currency=currency,
            )
            db.add(attrs)
            inserted += 1
        else:
            attrs.shelf_life_text = shelf_life
            attrs.hs_code = hs_code
            attrs.pallet_weight_kg = Decimal(str(pallet_weight_kg)) if pallet_weight_ok and pallet_weight_kg is not None else attrs.pallet_weight_kg
            attrs.pallet_dimensions_text = pallet_dims
            attrs.ti_hi = ti_hi
            if price_ok and price_unit is not None:
                attrs.price_unit = Decimal(str(price_unit))
            if cogs_ok and cogs_unit is not None:
                attrs.cogs_unit = Decimal(str(cogs_unit))
            if cogs_sell_ok and cogs_selling_unit is not None:
                attrs.cogs_selling_unit = Decimal(str(cogs_selling_unit))
            attrs.currency = currency
            updated += 1

    return inserted, updated
