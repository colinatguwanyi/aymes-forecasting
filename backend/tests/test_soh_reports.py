"""Tests: SOH History report API (series endpoint)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.database import SessionLocal
from app.models import InventorySnapshotWeekly, Product


def _soh_weekly_available() -> bool:
    """True if inventory_snapshots_weekly exists."""
    from sqlalchemy import inspect
    try:
        from app.database import engine
        with engine.connect() as conn:
            return "inventory_snapshots_weekly" in inspect(conn).get_table_names()
    except Exception:
        return False


@pytest.mark.skipif(not _soh_weekly_available(), reason="inventory_snapshots_weekly not available")
def test_soh_series_endpoint() -> None:
    """GET /api/v1/reports/stock-on-hand/series returns ordered series for warehouse+sku."""
    db = SessionLocal()
    try:
        if not db.query(Product).filter(Product.sku == "SOH-TEST-SKU").first():
            db.add(Product(sku="SOH-TEST-SKU", name="Test", uom="units", active=True))
            db.commit()
        # Insert weekly snapshots
        weeks = [
            (date(2025, 1, 7), 100),
            (date(2025, 1, 14), 150),
            (date(2025, 1, 21), 120),
        ]
        for ws, qty in weeks:
            existing = db.query(InventorySnapshotWeekly).filter(
                InventorySnapshotWeekly.week_start == ws,
                InventorySnapshotWeekly.sku == "SOH-TEST-SKU",
                InventorySnapshotWeekly.warehouse_code == "AAH",
            ).first()
            if not existing:
                db.add(InventorySnapshotWeekly(
                    week_start=ws,
                    sku="SOH-TEST-SKU",
                    warehouse_code="AAH",
                    on_hand_qty=Decimal(str(qty)),
                    source_type="soh",
                ))
        db.commit()
        from fastapi.testclient import TestClient
        from app.main import app
        import json
        headers = {"X-Dev-User": json.dumps({"email": "u@test.com", "name": "User", "roles": ["Admin"]})}
        tc = TestClient(app)
        r = tc.get(
            "/api/v1/reports/stock-on-hand/series",
            params={"warehouse_code": "AAH", "sku": "SOH-TEST-SKU"},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 3
        assert data[0]["week_start"] == "2025-01-07"
        assert data[0]["on_hand_units"] == 100
        assert data[1]["on_hand_units"] == 150
        assert data[2]["on_hand_units"] == 120
    finally:
        db.query(InventorySnapshotWeekly).filter(
            InventorySnapshotWeekly.sku == "SOH-TEST-SKU",
            InventorySnapshotWeekly.warehouse_code == "AAH",
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.skipif(not _soh_weekly_available(), reason="inventory_snapshots_weekly not available")
def test_soh_series_empty_requires_sku() -> None:
    """Series endpoint returns 400 when sku is empty."""
    from fastapi.testclient import TestClient
    from app.main import app
    import json
    headers = {"X-Dev-User": json.dumps({"email": "u@test.com", "name": "User", "roles": ["Admin"]})}
    tc = TestClient(app)
    r = tc.get(
        "/api/v1/reports/stock-on-hand/series",
        params={"warehouse_code": "AAH", "sku": "   "},
        headers=headers,
    )
    assert r.status_code == 400


# --- Grid endpoint tests ---


@pytest.mark.skipif(not _soh_weekly_available(), reason="inventory_snapshots_weekly not available")
def test_soh_grid_week_starts_length() -> None:
    """Grid endpoint returns correct week_starts length."""
    from fastapi.testclient import TestClient
    from app.main import app
    import json
    headers = {"X-Dev-User": json.dumps({"email": "u@test.com", "name": "User", "roles": ["Admin"]})}
    tc = TestClient(app)
    r = tc.get(
        "/api/v1/reports/stock-on-hand/grid",
        params={
            "warehouse_code": "AAH",
            "weeks": 8,
            # Without snapshots, anchor would be None and week_starts empty; pin anchor for column shape.
            "anchor_week_start": "2025-01-07",
        },
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert "week_starts" in data
    assert len(data["week_starts"]) == 8
    assert data["warehouse_code"] == "AAH"


@pytest.mark.skipif(not _soh_weekly_available(), reason="inventory_snapshots_weekly not available")
def test_soh_grid_missing_values_zero() -> None:
    """Grid endpoint returns 0 for missing week values."""
    db = SessionLocal()
    try:
        if not db.query(Product).filter(Product.sku == "GRID-MISS-SKU").first():
            db.add(Product(sku="GRID-MISS-SKU", name="Grid Missing Test", uom="units", active=True))
            db.commit()
        # Only one week of data
        existing = db.query(InventorySnapshotWeekly).filter(
            InventorySnapshotWeekly.sku == "GRID-MISS-SKU",
            InventorySnapshotWeekly.warehouse_code == "AAH",
        ).first()
        if not existing:
            db.add(InventorySnapshotWeekly(
                week_start=date(2025, 2, 18),
                sku="GRID-MISS-SKU",
                warehouse_code="AAH",
                on_hand_qty=Decimal("99"),
                source_type="legacy",
            ))
            db.commit()
        from fastapi.testclient import TestClient
        from app.main import app
        import json
        headers = {"X-Dev-User": json.dumps({"email": "u@test.com", "name": "User", "roles": ["Admin"]})}
        tc = TestClient(app)
        r = tc.get(
            "/api/v1/reports/stock-on-hand/grid",
            params={"warehouse_code": "AAH", "weeks": 4, "anchor_week_start": "2025-02-18", "limit": 10, "q": "GRID-MISS"},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["rows"]) >= 1
        row = next((r for r in data["rows"] if r["sku"] == "GRID-MISS-SKU"), None)
        assert row is not None
        assert row["values"] == [99, 0, 0, 0]  # first week has data, others 0
    finally:
        db.query(InventorySnapshotWeekly).filter(
            InventorySnapshotWeekly.sku == "GRID-MISS-SKU",
            InventorySnapshotWeekly.warehouse_code == "AAH",
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.skipif(not _soh_weekly_available(), reason="inventory_snapshots_weekly not available")
def test_soh_grid_pagination() -> None:
    """Grid endpoint pagination: total_products correct, limit/offset work."""
    from fastapi.testclient import TestClient
    from app.main import app
    import json
    headers = {"X-Dev-User": json.dumps({"email": "u@test.com", "name": "User", "roles": ["Admin"]})}
    tc = TestClient(app)
    r1 = tc.get(
        "/api/v1/reports/stock-on-hand/grid",
        params={"warehouse_code": "AAH", "limit": 5, "offset": 0},
        headers=headers,
    )
    assert r1.status_code == 200
    d1 = r1.json()
    total = d1["total_products"]
    assert total >= 0
    assert len(d1["rows"]) <= 5
    if total > 5:
        r2 = tc.get(
            "/api/v1/reports/stock-on-hand/grid",
            params={"warehouse_code": "AAH", "limit": 5, "offset": 5},
            headers=headers,
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["total_products"] == total
        assert len(d2["rows"]) <= 5
        # Different SKUs
        skus1 = {r["sku"] for r in d1["rows"]}
        skus2 = {r["sku"] for r in d2["rows"]}
        assert skus1.isdisjoint(skus2)


@pytest.mark.skipif(not _soh_weekly_available(), reason="inventory_snapshots_weekly not available")
def test_soh_grid_q_filter() -> None:
    """Grid endpoint q filter affects results."""
    from fastapi.testclient import TestClient
    from app.main import app
    import json
    headers = {"X-Dev-User": json.dumps({"email": "u@test.com", "name": "User", "roles": ["Admin"]})}
    tc = TestClient(app)
    r_all = tc.get(
        "/api/v1/reports/stock-on-hand/grid",
        params={"warehouse_code": "AAH", "limit": 200},
        headers=headers,
    )
    r_filtered = tc.get(
        "/api/v1/reports/stock-on-hand/grid",
        params={"warehouse_code": "AAH", "limit": 200, "q": "xyznonexistent123"},
        headers=headers,
    )
    assert r_all.status_code == 200
    assert r_filtered.status_code == 200
    d_all = r_all.json()
    d_filtered = r_filtered.json()
    assert d_filtered["total_products"] <= d_all["total_products"]
    for row in d_filtered["rows"]:
        assert "xyznonexistent123" in row["sku"].lower() or "xyznonexistent123" in (row.get("name") or "").lower()


@pytest.mark.skipif(not _soh_weekly_available(), reason="inventory_snapshots_weekly not available")
def test_soh_grid_empty_warehouse() -> None:
    """Grid endpoint returns week_starts=[] and rows=[] when no data for warehouse."""
    from fastapi.testclient import TestClient
    from app.main import app
    import json
    headers = {"X-Dev-User": json.dumps({"email": "u@test.com", "name": "User", "roles": ["Admin"]})}
    tc = TestClient(app)
    r = tc.get(
        "/api/v1/reports/stock-on-hand/grid",
        params={"warehouse_code": "NODATAWH"},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["week_starts"] == []
    assert data["rows"] == []
    assert data["total_products"] == 0
