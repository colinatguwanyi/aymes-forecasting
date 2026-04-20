"""Tests: Sales Grid report API."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.database import SessionLocal
from app.models import DemandFactsWeekly, DemandType, Product


def _demand_facts_available() -> bool:
    """True if demand_facts_weekly exists."""
    from sqlalchemy import inspect
    try:
        from app.database import engine
        with engine.connect() as conn:
            return "demand_facts_weekly" in inspect(conn).get_table_names()
    except Exception:
        return False


@pytest.mark.skipif(not _demand_facts_available(), reason="demand_facts_weekly not available")
def test_sales_grid_week_starts_length() -> None:
    """Grid endpoint returns correct week_starts length and ordering (most recent first)."""
    from fastapi.testclient import TestClient
    from app.main import app
    import json
    headers = {"X-Dev-User": json.dumps({"email": "u@test.com", "name": "User", "roles": ["Admin"]})}
    tc = TestClient(app)
    r = tc.get(
        "/api/v1/reports/sales/grid",
        params={"warehouse_code": "AAH", "weeks": 8},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert "week_starts" in data
    assert len(data["week_starts"]) == 8
    assert data["warehouse_code"] == "AAH"
    # Most recent first
    if len(data["week_starts"]) >= 2:
        assert data["week_starts"][0] >= data["week_starts"][1]


@pytest.mark.skipif(not _demand_facts_available(), reason="demand_facts_weekly not available")
def test_sales_grid_missing_values_zero() -> None:
    """Grid endpoint returns 0 for missing week values."""
    db = SessionLocal()
    try:
        if not db.query(Product).filter(Product.sku == "SALES-GRID-MISS").first():
            db.add(Product(sku="SALES-GRID-MISS", name="Sales Grid Missing Test", uom="units", active=True))
            db.commit()
        existing = db.query(DemandFactsWeekly).filter(
            DemandFactsWeekly.sku == "SALES-GRID-MISS",
            DemandFactsWeekly.warehouse_code == "AAH",
            DemandFactsWeekly.demand_type == DemandType.CUSTOMER,
        ).first()
        if not existing:
            db.add(DemandFactsWeekly(
                week_start=date(2025, 2, 18),
                sku="SALES-GRID-MISS",
                warehouse_code="AAH",
                demand_type=DemandType.CUSTOMER,
                qty=Decimal("42"),
            ))
            db.commit()
        from fastapi.testclient import TestClient
        from app.main import app
        import json
        headers = {"X-Dev-User": json.dumps({"email": "u@test.com", "name": "User", "roles": ["Admin"]})}
        tc = TestClient(app)
        r = tc.get(
            "/api/v1/reports/sales/grid",
            params={"warehouse_code": "AAH", "weeks": 4, "anchor_week_start": "2025-02-18", "limit": 10, "q": "SALES-GRID-MISS"},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["rows"]) >= 1
        row = next((r for r in data["rows"] if r["sku"] == "SALES-GRID-MISS"), None)
        assert row is not None
        assert row["values"] == [42, 0, 0, 0]
    finally:
        db.query(DemandFactsWeekly).filter(
            DemandFactsWeekly.sku == "SALES-GRID-MISS",
            DemandFactsWeekly.warehouse_code == "AAH",
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.skipif(not _demand_facts_available(), reason="demand_facts_weekly not available")
def test_sales_grid_pagination() -> None:
    """Grid endpoint pagination: total_products correct, limit/offset work."""
    from fastapi.testclient import TestClient
    from app.main import app
    import json
    headers = {"X-Dev-User": json.dumps({"email": "u@test.com", "name": "User", "roles": ["Admin"]})}
    tc = TestClient(app)
    r1 = tc.get(
        "/api/v1/reports/sales/grid",
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
            "/api/v1/reports/sales/grid",
            params={"warehouse_code": "AAH", "limit": 5, "offset": 5},
            headers=headers,
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["total_products"] == total
        assert len(d2["rows"]) <= 5
        skus1 = {r["sku"] for r in d1["rows"]}
        skus2 = {r["sku"] for r in d2["rows"]}
        assert skus1.isdisjoint(skus2)


@pytest.mark.skipif(not _demand_facts_available(), reason="demand_facts_weekly not available")
def test_sales_grid_q_filter() -> None:
    """Grid endpoint q filter matches sku and product name."""
    from fastapi.testclient import TestClient
    from app.main import app
    import json
    headers = {"X-Dev-User": json.dumps({"email": "u@test.com", "name": "User", "roles": ["Admin"]})}
    tc = TestClient(app)
    r_filtered = tc.get(
        "/api/v1/reports/sales/grid",
        params={"warehouse_code": "AAH", "limit": 200, "q": "xyznonexistent999"},
        headers=headers,
    )
    assert r_filtered.status_code == 200
    d = r_filtered.json()
    for row in d["rows"]:
        assert "xyznonexistent999" in row["sku"].lower() or "xyznonexistent999" in (row.get("name") or "").lower()


@pytest.mark.skipif(not _demand_facts_available(), reason="demand_facts_weekly not available")
def test_sales_grid_aggregation() -> None:
    """Single row per sku/week returned correctly; GROUP BY sum used (defensive for any duplicates)."""
    db = SessionLocal()
    try:
        if not db.query(Product).filter(Product.sku == "SALES-AGG-SKU").first():
            db.add(Product(sku="SALES-AGG-SKU", name="Sales Agg Test", uom="units", active=True))
            db.commit()
        ws = date(2025, 2, 18)
        existing = db.query(DemandFactsWeekly).filter(
            DemandFactsWeekly.sku == "SALES-AGG-SKU",
            DemandFactsWeekly.warehouse_code == "AAH",
            DemandFactsWeekly.week_start == ws,
        ).first()
        if not existing:
            db.add(DemandFactsWeekly(
                week_start=ws,
                sku="SALES-AGG-SKU",
                warehouse_code="AAH",
                demand_type=DemandType.CUSTOMER,
                qty=Decimal("15"),
            ))
            db.commit()
        from fastapi.testclient import TestClient
        from app.main import app
        import json
        headers = {"X-Dev-User": json.dumps({"email": "u@test.com", "name": "User", "roles": ["Admin"]})}
        tc = TestClient(app)
        r = tc.get(
            "/api/v1/reports/sales/grid",
            params={"warehouse_code": "AAH", "weeks": 1, "anchor_week_start": "2025-02-18", "limit": 10, "q": "SALES-AGG"},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()
        row = next((r for r in data["rows"] if r["sku"] == "SALES-AGG-SKU"), None)
        assert row is not None
        assert row["values"][0] == 15
        assert row.get("latest") == 15
        assert row.get("total") == 15
    finally:
        db.query(DemandFactsWeekly).filter(
            DemandFactsWeekly.sku == "SALES-AGG-SKU",
            DemandFactsWeekly.warehouse_code == "AAH",
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.skipif(not _demand_facts_available(), reason="demand_facts_weekly not available")
def test_sales_grid_empty_warehouse() -> None:
    """Grid endpoint returns week_starts=[] and rows=[] when no data for warehouse."""
    from fastapi.testclient import TestClient
    from app.main import app
    import json
    headers = {"X-Dev-User": json.dumps({"email": "u@test.com", "name": "User", "roles": ["Admin"]})}
    tc = TestClient(app)
    r = tc.get(
        "/api/v1/reports/sales/grid",
        params={"warehouse_code": "NODATAWH"},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["week_starts"] == []
    assert data["rows"] == []
    assert data["total_products"] == 0
