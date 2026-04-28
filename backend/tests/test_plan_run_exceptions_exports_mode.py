"""Plan run exceptions and exports: demand_only must not imply physical stockout risk."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import cast

from app.database import SessionLocal
from app.models import PlanRun, PlannedOrder, ProjectedInventory


def _unique_scenario(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _insert_run_with_stockout_row(*, planning_mode: str | None) -> int:
    db = SessionLocal()
    d = date(2026, 1, 5)
    name = _unique_scenario("expm")
    meta = {"planning_mode": planning_mode} if planning_mode else None
    run = PlanRun(
        scenario_name=name,
        run_at=d,
        created_at=d,
        plan_start_week_start=d,
        progress_meta=meta,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    rid = cast(int, run.id)
    db.add(
        ProjectedInventory(
            plan_run_id=rid,
            week_start=d,
            sku=f"SKU-{uuid.uuid4().hex[:8]}",
            warehouse_code="AAH",
            start_qty=Decimal("0"),
            receipts_qty=Decimal("0"),
            demand_qty=Decimal("10"),
            projected_qty=Decimal("-1"),
            weeks_of_cover=Decimal("0"),
            stockout=True,
        )
    )
    db.commit()
    db.close()
    return rid


def _cleanup_run(run_id: int) -> None:
    db = SessionLocal()
    try:
        db.query(PlannedOrder).filter(PlannedOrder.plan_run_id == run_id).delete(synchronize_session=False)
        db.query(ProjectedInventory).filter(ProjectedInventory.plan_run_id == run_id).delete(
            synchronize_session=False
        )
        db.query(PlanRun).filter(PlanRun.id == run_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_get_plan_exceptions_stock_aware_includes_stockout(client, admin_headers) -> None:
    rid = _insert_run_with_stockout_row(planning_mode="stock_aware")
    try:
        r = client.get(f"/api/plan/runs/{rid}/exceptions", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert any(e.get("type") == "stockout" for e in data)
        assert any("stockout" in (e.get("message") or "").lower() for e in data)
    finally:
        _cleanup_run(rid)


def test_get_plan_exceptions_demand_only_empty(client, admin_headers) -> None:
    rid = _insert_run_with_stockout_row(planning_mode="demand_only")
    try:
        r = client.get(f"/api/plan/runs/{rid}/exceptions", headers=admin_headers)
        assert r.status_code == 200
        assert r.json() == []
    finally:
        _cleanup_run(rid)


def test_export_exceptions_stock_aware_has_stockout_row(client, admin_headers) -> None:
    rid = _insert_run_with_stockout_row(planning_mode="stock_aware")
    try:
        r = client.get("/api/exports/exceptions", params={"plan_run_id": rid}, headers=admin_headers)
        assert r.status_code == 200
        disp = r.headers.get("content-disposition", "")
        assert "_demand_only" not in disp
        body = r.text
        assert "stockout" in body.lower()
    finally:
        _cleanup_run(rid)


def test_export_exceptions_demand_only_empty_and_filename(client, admin_headers) -> None:
    rid = _insert_run_with_stockout_row(planning_mode="demand_only")
    try:
        r = client.get("/api/exports/exceptions", params={"plan_run_id": rid}, headers=admin_headers)
        assert r.status_code == 200
        disp = r.headers.get("content-disposition", "")
        assert "_demand_only" in disp
        lines = [ln for ln in r.text.strip().splitlines() if ln]
        assert len(lines) == 1
        assert "type" in lines[0]
    finally:
        _cleanup_run(rid)


def test_export_projected_inventory_filename_distinguishes_mode(client, admin_headers) -> None:
    r_sa = _insert_run_with_stockout_row(planning_mode="stock_aware")
    r_do = _insert_run_with_stockout_row(planning_mode="demand_only")
    try:
        resp_sa = client.get(
            "/api/exports/projected-inventory", params={"plan_run_id": r_sa}, headers=admin_headers
        )
        resp_do = client.get(
            "/api/exports/projected-inventory", params={"plan_run_id": r_do}, headers=admin_headers
        )
        assert resp_sa.status_code == 200
        assert resp_do.status_code == 200
        assert "_demand_only" not in resp_sa.headers.get("content-disposition", "")
        assert "_demand_only" in resp_do.headers.get("content-disposition", "")
    finally:
        _cleanup_run(r_sa)
        _cleanup_run(r_do)


def test_export_planned_orders_filename_distinguishes_mode(client, admin_headers) -> None:
    d = date(2026, 1, 5)

    def _run_with_order(pm: str) -> int:
        db = SessionLocal()
        name = _unique_scenario("po")
        run = PlanRun(
            scenario_name=name,
            run_at=d,
            created_at=d,
            plan_start_week_start=d,
            progress_meta={"planning_mode": pm},
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        rid = cast(int, run.id)
        db.add(
            PlannedOrder(
                plan_run_id=rid,
                week_start=d,
                sku=f"SKU-{uuid.uuid4().hex[:8]}",
                warehouse_code="AAH",
                order_qty=Decimal("5"),
            )
        )
        db.commit()
        db.close()
        return rid

    r_sa = _run_with_order("stock_aware")
    r_do = _run_with_order("demand_only")
    try:
        resp_sa = client.get("/api/exports/planned-orders", params={"plan_run_id": r_sa}, headers=admin_headers)
        resp_do = client.get("/api/exports/planned-orders", params={"plan_run_id": r_do}, headers=admin_headers)
        assert resp_sa.status_code == 200
        assert resp_do.status_code == 200
        assert "_demand_only" not in resp_sa.headers.get("content-disposition", "")
        assert "_demand_only" in resp_do.headers.get("content-disposition", "")
    finally:
        _cleanup_run(r_sa)
        _cleanup_run(r_do)
