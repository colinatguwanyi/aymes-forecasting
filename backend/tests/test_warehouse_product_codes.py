"""Tests: Warehouse Product Codes API — bulk upload upsert, unmapped aggregation."""
from __future__ import annotations

import csv
import io
from datetime import date
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.database import SessionLocal
from app.models import (
    IngestionEntity,
    IngestionRejection,
    IngestionRun,
    IngestionSourceType,
    IngestionStatus,
    Product,
    WarehouseProductCode,
)
from app.routers.warehouse_product_codes import _fetch_unmapped_codes
from app.services.soh_ingestion import stage_blp_soh


def _warehouse_product_codes_available() -> bool:
    """True if migration 020 (warehouse_product_codes) is applied."""
    from sqlalchemy import inspect, text
    try:
        from app.database import engine
        with engine.connect() as conn:
            insp = inspect(conn)
            return "warehouse_product_codes" in insp.get_table_names()
    except Exception:
        return False


@pytest.mark.skipif(not _warehouse_product_codes_available(), reason="Migration 020 not applied")
def test_bulk_upload_upsert() -> None:
    """Bulk upload creates new mappings and updates existing ones (upsert on warehouse_code+external_code)."""
    db = SessionLocal()
    try:
        if not db.query(Product).filter(Product.sku == "BULK-SKU-A").first():
            db.add(Product(sku="BULK-SKU-A", name="A", uom="units", active=True))
        if not db.query(Product).filter(Product.sku == "BULK-SKU-B").first():
            db.add(Product(sku="BULK-SKU-B", name="B", uom="units", active=True))
        db.commit()
        # Create initial mapping
        existing = db.query(WarehouseProductCode).filter(
            WarehouseProductCode.warehouse_code == "BLP",
            WarehouseProductCode.external_code == "EXT-1",
        ).first()
        if not existing:
            db.add(WarehouseProductCode(
                warehouse_code="BLP",
                external_code="EXT-1",
                sku="BULK-SKU-A",
                active=True,
            ))
            db.commit()
        # Bulk CSV: EXT-1 -> BULK-SKU-B (update), EXT-2 -> BULK-SKU-B (create)
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=["external_code", "sku", "external_name", "hs_code"])
        w.writeheader()
        w.writerow({"external_code": "EXT-1", "sku": "BULK-SKU-B", "external_name": "Updated", "hs_code": "123"})
        w.writerow({"external_code": "EXT-2", "sku": "BULK-SKU-B", "external_name": "New", "hs_code": ""})
        buf.seek(0)
        content = buf.getvalue().encode("utf-8")
        from fastapi.testclient import TestClient
        from app.main import app
        import json
        headers = {"X-Dev-User": json.dumps({"email": "admin@test.com", "name": "Admin", "roles": ["Admin"]})}
        tc = TestClient(app)
        r = tc.post(
            "/api/admin/warehouse-product-codes/bulk",
            params={"warehouse_code": "BLP"},
            files={"file": ("bulk.csv", content, "text/csv")},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["created"] == 1
        assert data["updated"] == 1
        # Verify DB state
        m1 = db.query(WarehouseProductCode).filter(
            WarehouseProductCode.warehouse_code == "BLP",
            WarehouseProductCode.external_code == "EXT-1",
        ).first()
        assert m1 is not None
        assert m1.sku == "BULK-SKU-B"
        assert m1.external_name == "Updated"
        m2 = db.query(WarehouseProductCode).filter(
            WarehouseProductCode.warehouse_code == "BLP",
            WarehouseProductCode.external_code == "EXT-2",
        ).first()
        assert m2 is not None
        assert m2.sku == "BULK-SKU-B"
    finally:
        db.query(WarehouseProductCode).filter(
            WarehouseProductCode.warehouse_code == "BLP",
            WarehouseProductCode.external_code.in_(["EXT-1", "EXT-2"]),
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.skipif(not _warehouse_product_codes_available(), reason="Migration 020 not applied")
def test_unmapped_aggregation() -> None:
    """Unmapped endpoint aggregates product_not_found rejections by external_code."""
    db = SessionLocal()
    run_id = uuid4()
    try:
        if not db.query(Product).filter(Product.sku == "UNM-SKU").first():
            db.add(Product(sku="UNM-SKU", name="U", uom="units", active=True))
            db.commit()
        run = IngestionRun(
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.STOCK_ON_HAND,
            file_name="blp.csv",
            file_sha256="unm-test",
            status=IngestionStatus.SUCCESS,
            row_count=0,
        )
        db.add(run)
        db.flush()
        run_id = cast(UUID, run.id)
        # Create product_not_found rejections (same code twice, different code once)
        for row_num, code, qty in [(2, "MISS-A", 10), (3, "MISS-A", 20), (4, "MISS-B", 5)]:
            db.add(IngestionRejection(
                ingestion_run_id=run_id,
                row_number=row_num,
                raw_payload={"Code": code, "Balance": str(qty), "Description": f"Desc {code} HSCODE:99999"},
                reason="product_not_found",
            ))
        db.commit()
        result = _fetch_unmapped_codes(db, "BLP", run_id)
        assert result["import_run_id"] == str(run_id)
        assert result["warehouse_code"] == "BLP"
        unmapped = result["unmapped"]
        assert len(unmapped) == 2  # MISS-A and MISS-B aggregated
        by_code = {u["external_code"]: u for u in unmapped}
        assert by_code["MISS-A"]["qty_sum"] == 30
        assert by_code["MISS-A"]["sample_rows"] == 2
        assert by_code["MISS-B"]["qty_sum"] == 5
        assert by_code["MISS-B"]["sample_rows"] == 1
        assert by_code["MISS-A"]["hs_code_guess"] == "99999"
    finally:
        db.query(IngestionRejection).filter(IngestionRejection.ingestion_run_id == run_id).delete(synchronize_session=False)
        db.query(IngestionRun).filter(IngestionRun.id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()
