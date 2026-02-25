"""Tests: SOH product resolution (mapping_table, sku, aah_code, HSCODE in Description)."""
from __future__ import annotations

import pytest

from app.database import SessionLocal
from app.models import Product, ProductMasterAttributes, WarehouseProductCode
from app.ingestion.soh.product_resolution import resolve_code_to_sku


def test_resolve_by_mapping_table() -> None:
    """Mapping table lookup takes precedence when warehouse_code provided."""
    db = SessionLocal()
    try:
        if not db.query(Product).filter(Product.sku == "MAPPED-SKU").first():
            db.add(Product(sku="MAPPED-SKU", name="M", uom="units", active=True))
            db.commit()
        # Also create a product with sku matching external code to ensure mapping wins
        if not db.query(Product).filter(Product.sku == "EXT-CODE").first():
            db.add(Product(sku="EXT-CODE", name="E", uom="units", active=True))
            db.commit()
        existing = db.query(WarehouseProductCode).filter(
            WarehouseProductCode.warehouse_code == "BLP",
            WarehouseProductCode.external_code == "EXT-CODE",
        ).first()
        if not existing:
            db.add(WarehouseProductCode(
                warehouse_code="BLP",
                external_code="EXT-CODE",
                sku="MAPPED-SKU",
                active=True,
            ))
            db.commit()
        sku, method = resolve_code_to_sku(db, "EXT-CODE", "", warehouse_code="BLP")
        assert sku == "MAPPED-SKU"
        assert method == "mapping_table"
        # Without warehouse_code, falls through to sku match
        sku2, method2 = resolve_code_to_sku(db, "EXT-CODE", "", warehouse_code=None)
        assert sku2 == "EXT-CODE"
        assert method2 == "sku"
    finally:
        db.close()


def test_resolve_by_sku() -> None:
    """Code matches products.sku exactly."""
    db = SessionLocal()
    try:
        if not db.query(Product).filter(Product.sku == "RES-SKU").first():
            db.add(Product(sku="RES-SKU", name="R", uom="units", active=True))
            db.commit()
        sku, method = resolve_code_to_sku(db, "RES-SKU", "")
        assert sku == "RES-SKU"
        assert method == "sku"
    finally:
        db.close()


def test_resolve_by_aah_code() -> None:
    """Code matches products.aah_code."""
    db = SessionLocal()
    try:
        if not db.query(Product).filter(Product.aah_code == "AAH-RES").first():
            db.add(Product(sku="CANON-SKU", name="C", uom="units", active=True, aah_code="AAH-RES"))
            db.commit()
        sku, method = resolve_code_to_sku(db, "AAH-RES", "")
        assert sku == "CANON-SKU"
        assert method == "aah_code"
    finally:
        db.close()


def test_resolve_by_hs_code() -> None:
    """Code not found; Description has HSCODE:12345; product_master_attributes.hs_code matches."""
    db = SessionLocal()
    try:
        p = db.query(Product).filter(Product.sku == "HS-SKU").first()
        if not p:
            db.add(Product(sku="HS-SKU", name="H", uom="units", active=True))
            db.commit()
        attrs = db.query(ProductMasterAttributes).filter(ProductMasterAttributes.sku == "HS-SKU").first()
        if not attrs:
            db.add(ProductMasterAttributes(sku="HS-SKU", hs_code="12345"))
            db.commit()
        sku, method = resolve_code_to_sku(db, "UNKNOWN-CODE", "Some desc HSCODE:12345 more text")
        assert sku == "HS-SKU"
        assert method == "hs_code"
    finally:
        db.close()


def test_no_match_returns_none() -> None:
    """Code and Description yield no match."""
    db = SessionLocal()
    try:
        sku, method = resolve_code_to_sku(db, "NONEXISTENT-XYZ", "")
        assert sku is None
        assert method == ""
    finally:
        db.close()
