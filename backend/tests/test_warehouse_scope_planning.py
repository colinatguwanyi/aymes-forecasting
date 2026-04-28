"""Tests: warehouse-scoped planning — readiness endpoint, run_plan with scope [AAH], [BLP], [AAH,BLP]."""
# pyright: reportMissingImports=false
from datetime import date
from decimal import Decimal
import uuid

import pytest
from sqlalchemy.orm import sessionmaker

from app.database import engine
from app.models import (
    DemandActual,
    DemandType,
    InventorySnapshotWeekly,
    PlanningPolicy,
    Product,
    ProjectedInventory,
    Warehouse,
)
from app.services.planning import AllWarehousesSkippedError, run_plan
from app.services.warehouse_readiness import check_planning_readiness


@pytest.fixture
def db_session():
    """Session for warehouse scope tests. Uses app.database engine."""
    Session = sessionmaker(bind=engine, autoflush=True)
    session = Session()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


def _ensure_aah_blp(db):
    """Ensure AAH and BLP warehouses exist."""
    for code in ["AAH", "BLP"]:
        if not db.query(Warehouse).filter(Warehouse.code == code).first():
            db.add(Warehouse(code=code, name=code, timezone="Europe/London", active=True))
    db.commit()


def _uniq_sku(prefix: str) -> str:
    """Avoid duplicate-key failures when tests run against a shared non-empty MySQL."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _uniq_wh(prefix: str = "WH") -> str:
    """Short unique warehouse code for readiness isolation on shared DB."""
    return f"{prefix}{uuid.uuid4().hex[:6].upper()}"


def _ensure_warehouse(db, code: str) -> None:
    if not db.query(Warehouse).filter(Warehouse.code == code).first():
        db.add(Warehouse(code=code, name=code, timezone="Europe/London", active=True))
        db.commit()


def test_run_plan_raises_when_policy_sku_missing_from_products(db_session) -> None:
    """Every planning_policies.sku must exist in products before a plan run."""
    db = db_session
    wh = _uniq_wh("PX")
    _ensure_warehouse(db, wh)
    good_sku = _uniq_sku("GOOD")
    orphan_sku = _uniq_sku("MISSING")
    db.add(Product(sku=good_sku, name="G", uom="units", active=True))
    db.add(
        PlanningPolicy(
            sku=good_sku,
            warehouse_code=wh,
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    db.add(
        PlanningPolicy(
            sku=orphan_sku,
            warehouse_code=wh,
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    db.add(
        DemandActual(
            week_start=date(2025, 2, 17),
            sku=good_sku,
            warehouse_code=wh,
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("1"),
        )
    )
    db.commit()
    with pytest.raises(ValueError, match="planning_policies.sku"):
        run_plan(
            db,
            "test-orphan-pol",
            demand_source="actuals",
            warehouses_scope=[wh],
            planning_mode="demand_only",
        )


def test_readiness_only_aah_has_data(db_session) -> None:
    """When only AAH has SOH/demand/policies, readiness returns correct flags."""
    _ensure_aah_blp(db_session)
    db = db_session
    sku = _uniq_sku("WSP-1")
    db.add(Product(sku=sku, name="P1", uom="units", active=True))
    db.commit()
    db.add(
        PlanningPolicy(
            sku=sku,
            warehouse_code="AAH",
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    db.add(
        InventorySnapshotWeekly(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code="AAH",
            on_hand_qty=Decimal("100"),
            source_type="soh",
        )
    )
    db.add(
        DemandActual(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code="AAH",
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("10"),
        )
    )
    db.commit()

    readiness = check_planning_readiness(db, demand_source="actuals")
    aa = next((r for r in readiness if r["warehouse_code"] == "AAH"), None)
    bl = next((r for r in readiness if r["warehouse_code"] == "BLP"), None)
    assert aa is not None
    assert aa["ready"] is True
    assert aa["has_soh"] is True
    assert aa["has_demand"] is True
    assert aa["has_policies"] is True
    if bl:
        assert bl["ready"] is False
        assert "No SOH" in str(bl.get("blockers", []))


def test_run_plan_scope_aah_produces_rows(db_session) -> None:
    """run_plan with scope [AAH] produces projected_inventory rows when AAH has data."""
    _ensure_aah_blp(db_session)
    db = db_session
    sku = _uniq_sku("WSP-2")
    db.add(Product(sku=sku, name="P2", uom="units", active=True))
    db.commit()
    db.add(
        PlanningPolicy(
            sku=sku,
            warehouse_code="AAH",
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    db.add(
        InventorySnapshotWeekly(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code="AAH",
            on_hand_qty=Decimal("100"),
            source_type="soh",
        )
    )
    db.add(
        DemandActual(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code="AAH",
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("10"),
        )
    )
    db.commit()

    run = run_plan(db, "baseline", demand_source="actuals", warehouses_scope=["AAH"])
    db.refresh(run)
    proj_count = db.query(ProjectedInventory).filter(ProjectedInventory.plan_run_id == run.id).count()
    assert proj_count > 0
    assert run.progress_meta is not None
    assert "AAH" in (run.progress_meta.get("warehouses_planned") or [])


def test_run_plan_scope_blp_not_ready_returns_400(db_session) -> None:
    """run_plan with scope [BLP] when BLP has no SOH/demand/policies raises AllWarehousesSkippedError."""
    _ensure_aah_blp(db_session)
    db = db_session
    sku = _uniq_sku("WSP-3")
    db.add(Product(sku=sku, name="P3", uom="units", active=True))
    db.commit()
    # No policies, SOH, or demand for BLP

    with pytest.raises(AllWarehousesSkippedError) as exc_info:
        run_plan(db, "baseline", demand_source="actuals", warehouses_scope=["BLP"])
    assert len(exc_info.value.skipped_warehouses) >= 1
    assert any(s["warehouse_code"] == "BLP" for s in exc_info.value.skipped_warehouses)


def test_warehouse_readiness_endpoint(db_session) -> None:
    """GET /api/v1/diagnostics/warehouse-readiness returns per-warehouse readiness."""
    from fastapi.testclient import TestClient
    from app.main import app
    tc = TestClient(app)
    r = tc.get("/api/v1/diagnostics/warehouse-readiness", params={"demand_source": "actuals"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


def test_run_plan_scope_aah_blp_plans_aah_skips_blp(db_session) -> None:
    """run_plan with scope [AAH, BLP]: plans AAH, records BLP skipped."""
    _ensure_aah_blp(db_session)
    db = db_session
    sku = _uniq_sku("WSP-4")
    db.add(Product(sku=sku, name="P4", uom="units", active=True))
    db.commit()
    db.add(
        PlanningPolicy(
            sku=sku,
            warehouse_code="AAH",
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    db.add(
        InventorySnapshotWeekly(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code="AAH",
            on_hand_qty=Decimal("100"),
            source_type="soh",
        )
    )
    db.add(
        DemandActual(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code="AAH",
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("10"),
        )
    )
    db.commit()

    run = run_plan(db, "baseline", demand_source="actuals", warehouses_scope=["AAH", "BLP"])
    db.refresh(run)
    proj_count = db.query(ProjectedInventory).filter(ProjectedInventory.plan_run_id == run.id).count()
    assert proj_count > 0
    assert run.progress_meta is not None
    assert "AAH" in (run.progress_meta.get("warehouses_planned") or [])
    assert "BLP" in (run.progress_meta.get("warehouses_skipped") or [])


def test_run_plan_omitted_planning_mode_defaults_in_progress_meta(db_session) -> None:
    """Omitted planning_mode defaults to stock_aware; synthetic_starting_inventory false."""
    _ensure_aah_blp(db_session)
    db = db_session
    sku = _uniq_sku("WSP-PM-1")
    db.add(Product(sku=sku, name="P", uom="units", active=True))
    db.commit()
    db.add(
        PlanningPolicy(
            sku=sku,
            warehouse_code="AAH",
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    db.add(
        InventorySnapshotWeekly(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code="AAH",
            on_hand_qty=Decimal("100"),
            source_type="soh",
        )
    )
    db.add(
        DemandActual(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code="AAH",
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("10"),
        )
    )
    db.commit()

    run = run_plan(db, "pm-default", demand_source="actuals", warehouses_scope=["AAH"])
    db.refresh(run)
    assert run.progress_meta is not None
    assert run.progress_meta.get("planning_mode") == "stock_aware"
    assert run.progress_meta.get("synthetic_starting_inventory") is False


def test_run_plan_stock_aware_explicit_in_progress_meta(db_session) -> None:
    """planning_mode=stock_aware is persisted like default."""
    _ensure_aah_blp(db_session)
    db = db_session
    sku = _uniq_sku("WSP-PM-2")
    db.add(Product(sku=sku, name="P", uom="units", active=True))
    db.commit()
    db.add(
        PlanningPolicy(
            sku=sku,
            warehouse_code="AAH",
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    db.add(
        InventorySnapshotWeekly(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code="AAH",
            on_hand_qty=Decimal("100"),
            source_type="soh",
        )
    )
    db.add(
        DemandActual(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code="AAH",
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("10"),
        )
    )
    db.commit()

    run = run_plan(
        db,
        "pm-stock-aware",
        demand_source="actuals",
        warehouses_scope=["AAH"],
        planning_mode="stock_aware",
    )
    db.refresh(run)
    assert run.progress_meta is not None
    assert run.progress_meta.get("planning_mode") == "stock_aware"
    assert run.progress_meta.get("synthetic_starting_inventory") is False


def test_run_plan_demand_only_persisted_in_progress_meta(db_session) -> None:
    """demand_only is stored in progress_meta; synthetic false when all planned pairs have SOH (isolated wh)."""
    db = db_session
    wh = _uniq_wh("PM3")
    _ensure_warehouse(db, wh)
    sku = _uniq_sku("WSP-PM-3")
    db.add(Product(sku=sku, name="P", uom="units", active=True))
    db.commit()
    db.add(
        PlanningPolicy(
            sku=sku,
            warehouse_code=wh,
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    db.add(
        InventorySnapshotWeekly(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code=wh,
            on_hand_qty=Decimal("100"),
            source_type="soh",
        )
    )
    db.add(
        DemandActual(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code=wh,
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("10"),
        )
    )
    db.commit()

    run = run_plan(
        db,
        "pm-demand-only",
        demand_source="actuals",
        warehouses_scope=[wh],
        planning_mode="demand_only",
    )
    db.refresh(run)
    assert run.progress_meta is not None
    assert run.progress_meta.get("planning_mode") == "demand_only"
    assert run.progress_meta.get("synthetic_starting_inventory") is False


def test_readiness_stock_aware_requires_soh_even_with_policies_and_demand(db_session) -> None:
    """stock_aware: missing SOH keeps warehouse not ready."""
    db = db_session
    wh = _uniq_wh("SA")
    _ensure_warehouse(db, wh)
    sku = _uniq_sku("WSP-R-SA")
    db.add(Product(sku=sku, name="P", uom="units", active=True))
    db.commit()
    db.add(
        PlanningPolicy(
            sku=sku,
            warehouse_code=wh,
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    db.add(
        DemandActual(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code=wh,
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("10"),
        )
    )
    db.commit()

    readiness = check_planning_readiness(db, demand_source="actuals", planning_mode="stock_aware")
    row = next((r for r in readiness if r["warehouse_code"] == wh), None)
    assert row is not None
    assert row["ready"] is False
    assert row["has_soh"] is False
    assert any("SOH" in b for b in row.get("blockers", []))


def test_readiness_demand_only_passes_without_soh_when_policies_and_demand(db_session) -> None:
    """demand_only: SOH not required when policies and demand (actuals) exist."""
    db = db_session
    wh = _uniq_wh("DO")
    _ensure_warehouse(db, wh)
    sku = _uniq_sku("WSP-R-DO")
    db.add(Product(sku=sku, name="P", uom="units", active=True))
    db.commit()
    db.add(
        PlanningPolicy(
            sku=sku,
            warehouse_code=wh,
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    db.add(
        DemandActual(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code=wh,
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("10"),
        )
    )
    db.commit()

    readiness = check_planning_readiness(db, demand_source="actuals", planning_mode="demand_only")
    row = next((r for r in readiness if r["warehouse_code"] == wh), None)
    assert row is not None
    assert row["ready"] is True
    assert row["has_soh"] is False
    assert not any("SOH" in b for b in row.get("blockers", []))


def test_readiness_demand_only_fails_without_policies(db_session) -> None:
    """demand_only still requires policies."""
    db = db_session
    wh = _uniq_wh("NP")
    _ensure_warehouse(db, wh)
    sku = _uniq_sku("WSP-R-DO-NP")
    db.add(Product(sku=sku, name="P", uom="units", active=True))
    db.commit()
    db.add(
        DemandActual(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code=wh,
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("5"),
        )
    )
    db.commit()

    readiness = check_planning_readiness(db, demand_source="actuals", planning_mode="demand_only")
    row = next((r for r in readiness if r["warehouse_code"] == wh), None)
    assert row is not None
    assert row["has_policies"] is False
    assert row["ready"] is False
    assert any("policies" in b.lower() for b in row.get("blockers", []))


def test_readiness_demand_only_actuals_fails_without_demand(db_session) -> None:
    """demand_only + actuals still requires demand data."""
    db = db_session
    wh = _uniq_wh("ND")
    _ensure_warehouse(db, wh)
    sku = _uniq_sku("WSP-R-DO-ND")
    db.add(Product(sku=sku, name="P", uom="units", active=True))
    db.commit()
    db.add(
        PlanningPolicy(
            sku=sku,
            warehouse_code=wh,
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    db.commit()

    readiness = check_planning_readiness(db, demand_source="actuals", planning_mode="demand_only")
    row = next((r for r in readiness if r["warehouse_code"] == wh), None)
    assert row is not None
    assert row["ready"] is False
    assert any("demand" in b.lower() or "Sales Out" in b for b in row.get("blockers", []))


def test_run_plan_demand_only_no_soh_not_all_warehouses_skipped(db_session) -> None:
    """demand_only: no SOH — synthetic start produces projections; progress_meta flags synthetic."""
    db = db_session
    wh = _uniq_wh("RUN")
    _ensure_warehouse(db, wh)
    sku = _uniq_sku("WSP-R-RUN")
    db.add(Product(sku=sku, name="P", uom="units", active=True))
    db.commit()
    db.add(
        PlanningPolicy(
            sku=sku,
            warehouse_code=wh,
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    db.add(
        DemandActual(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code=wh,
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("10"),
        )
    )
    db.commit()

    run = run_plan(
        db,
        "do-no-soh",
        demand_source="actuals",
        warehouses_scope=[wh],
        planning_mode="demand_only",
    )
    db.refresh(run)
    assert run.progress_meta is not None
    assert run.progress_meta.get("planning_mode") == "demand_only"
    assert run.progress_meta.get("synthetic_starting_inventory") is True
    proj_count = db.query(ProjectedInventory).filter(ProjectedInventory.plan_run_id == run.id).count()
    assert proj_count == 53


def test_run_plan_stock_aware_wh_no_soh_all_warehouses_skipped(db_session) -> None:
    """stock_aware: warehouse without SOH is not ready — same as before (AllWarehousesSkippedError)."""
    db = db_session
    wh = _uniq_wh("SAN")
    _ensure_warehouse(db, wh)
    sku = _uniq_sku("WSP-R-SAN")
    db.add(Product(sku=sku, name="P", uom="units", active=True))
    db.commit()
    db.add(
        PlanningPolicy(
            sku=sku,
            warehouse_code=wh,
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    db.add(
        DemandActual(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code=wh,
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("10"),
        )
    )
    db.commit()

    with pytest.raises(AllWarehousesSkippedError):
        run_plan(
            db,
            "sa-no-soh",
            demand_source="actuals",
            warehouses_scope=[wh],
            planning_mode="stock_aware",
        )


def test_run_plan_stock_aware_skips_sku_without_snapshot_when_wh_has_soh(db_session) -> None:
    """stock_aware: SKU×warehouse with policy but no snapshot row still produces no projections for that pair."""
    db = db_session
    wh = _uniq_wh("MIX")
    _ensure_warehouse(db, wh)
    sku_with_soh = _uniq_sku("WSP-MIX-A")
    sku_no_soh = _uniq_sku("WSP-MIX-B")
    for sku in (sku_with_soh, sku_no_soh):
        db.add(Product(sku=sku, name="P", uom="units", active=True))
    db.commit()
    for sku in (sku_with_soh, sku_no_soh):
        db.add(
            PlanningPolicy(
                sku=sku,
                warehouse_code=wh,
                target_weeks=Decimal("4"),
                safety_stock_weeks=Decimal("1"),
            )
        )
        db.add(
            DemandActual(
                week_start=date(2025, 2, 17),
                sku=sku,
                warehouse_code=wh,
                demand_type=DemandType.CUSTOMER,
                qty=Decimal("10"),
            )
        )
    db.add(
        InventorySnapshotWeekly(
            week_start=date(2025, 2, 17),
            sku=sku_with_soh,
            warehouse_code=wh,
            on_hand_qty=Decimal("100"),
            source_type="soh",
        )
    )
    db.commit()

    run = run_plan(
        db,
        "sa-mix",
        demand_source="actuals",
        warehouses_scope=[wh],
        planning_mode="stock_aware",
    )
    db.refresh(run)
    assert run.progress_meta.get("synthetic_starting_inventory") is False
    skus_proj = {r.sku for r in db.query(ProjectedInventory).filter(ProjectedInventory.plan_run_id == run.id).all()}
    assert skus_proj == {sku_with_soh}
    assert sku_no_soh not in skus_proj


def test_run_plan_stock_aware_inventory_without_policy_not_planned(db_session) -> None:
    """SKU×warehouse present in inventory_snapshots but not in planning_policies is not planned."""
    db = db_session
    wh = _uniq_wh("INVP")
    _ensure_warehouse(db, wh)
    sku_in_policy = _uniq_sku("WSP-PL")
    sku_inv_only = _uniq_sku("WSP-IO")
    for sku in (sku_in_policy, sku_inv_only):
        db.add(Product(sku=sku, name="P", uom="units", active=True))
    db.commit()
    db.add(
        PlanningPolicy(
            sku=sku_in_policy,
            warehouse_code=wh,
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    for sku in (sku_in_policy, sku_inv_only):
        db.add(
            InventorySnapshotWeekly(
                week_start=date(2025, 2, 17),
                sku=sku,
                warehouse_code=wh,
                on_hand_qty=Decimal("50"),
                source_type="soh",
            )
        )
        db.add(
            DemandActual(
                week_start=date(2025, 2, 17),
                sku=sku,
                warehouse_code=wh,
                demand_type=DemandType.CUSTOMER,
                qty=Decimal("10"),
            )
        )
    db.commit()

    run = run_plan(
        db,
        "sa-inv-no-pol",
        demand_source="actuals",
        warehouses_scope=[wh],
        planning_mode="stock_aware",
    )
    db.refresh(run)
    skus_proj = {r.sku for r in db.query(ProjectedInventory).filter(ProjectedInventory.plan_run_id == run.id).all()}
    assert skus_proj == {sku_in_policy}
    assert sku_inv_only not in skus_proj


def test_run_plan_demand_only_no_extra_pairs_from_inventory_or_demand(db_session) -> None:
    """demand_only: only policy pairs are planned; inventory+demand alone do not add SKU×warehouse rows."""
    db = db_session
    wh = _uniq_wh("DOPOL")
    _ensure_warehouse(db, wh)
    sku_in_policy = _uniq_sku("WSP-DO-P")
    sku_inv_only = _uniq_sku("WSP-DO-I")
    for sku in (sku_in_policy, sku_inv_only):
        db.add(Product(sku=sku, name="P", uom="units", active=True))
    db.commit()
    db.add(
        PlanningPolicy(
            sku=sku_in_policy,
            warehouse_code=wh,
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    db.add(
        InventorySnapshotWeekly(
            week_start=date(2025, 2, 17),
            sku=sku_in_policy,
            warehouse_code=wh,
            on_hand_qty=Decimal("40"),
            source_type="soh",
        )
    )
    db.add(
        InventorySnapshotWeekly(
            week_start=date(2025, 2, 17),
            sku=sku_inv_only,
            warehouse_code=wh,
            on_hand_qty=Decimal("99"),
            source_type="soh",
        )
    )
    for sku in (sku_in_policy, sku_inv_only):
        db.add(
            DemandActual(
                week_start=date(2025, 2, 17),
                sku=sku,
                warehouse_code=wh,
                demand_type=DemandType.CUSTOMER,
                qty=Decimal("7"),
            )
        )
    db.commit()

    run = run_plan(
        db,
        "do-inv-extra",
        demand_source="actuals",
        warehouses_scope=[wh],
        planning_mode="demand_only",
    )
    db.refresh(run)
    skus_proj = {r.sku for r in db.query(ProjectedInventory).filter(ProjectedInventory.plan_run_id == run.id).all()}
    assert skus_proj == {sku_in_policy}
    assert sku_inv_only not in skus_proj


def test_run_plan_demand_only_with_soh_synthetic_false(db_session) -> None:
    """demand_only with SOH snapshot uses real start; synthetic_starting_inventory stays false."""
    db = db_session
    wh = _uniq_wh("SOH")
    _ensure_warehouse(db, wh)
    sku = _uniq_sku("WSP-R-SOH")
    db.add(Product(sku=sku, name="P", uom="units", active=True))
    db.commit()
    db.add(
        PlanningPolicy(
            sku=sku,
            warehouse_code=wh,
            target_weeks=Decimal("4"),
            safety_stock_weeks=Decimal("1"),
        )
    )
    db.add(
        InventorySnapshotWeekly(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code=wh,
            on_hand_qty=Decimal("50"),
            source_type="soh",
        )
    )
    db.add(
        DemandActual(
            week_start=date(2025, 2, 17),
            sku=sku,
            warehouse_code=wh,
            demand_type=DemandType.CUSTOMER,
            qty=Decimal("10"),
        )
    )
    db.commit()

    run = run_plan(
        db,
        "do-with-soh",
        demand_source="actuals",
        warehouses_scope=[wh],
        planning_mode="demand_only",
    )
    db.refresh(run)
    assert run.progress_meta.get("synthetic_starting_inventory") is False
    assert db.query(ProjectedInventory).filter(ProjectedInventory.plan_run_id == run.id).count() == 53


def test_run_plan_demand_only_scope_limits_warehouse(db_session) -> None:
    """demand_only: warehouses_scope only plans that warehouse (synthetic), not another with policy+no SOH."""
    db = db_session
    wh_scoped = _uniq_wh("SC1")
    wh_other = _uniq_wh("SC2")
    _ensure_warehouse(db, wh_scoped)
    _ensure_warehouse(db, wh_other)
    sku_a = _uniq_sku("WSP-SC-A")
    sku_b = _uniq_sku("WSP-SC-B")
    for sku in (sku_a, sku_b):
        db.add(Product(sku=sku, name="P", uom="units", active=True))
    db.commit()
    for wh, sku in ((wh_scoped, sku_a), (wh_other, sku_b)):
        db.add(
            PlanningPolicy(
                sku=sku,
                warehouse_code=wh,
                target_weeks=Decimal("4"),
                safety_stock_weeks=Decimal("1"),
            )
        )
        db.add(
            DemandActual(
                week_start=date(2025, 2, 17),
                sku=sku,
                warehouse_code=wh,
                demand_type=DemandType.CUSTOMER,
                qty=Decimal("10"),
            )
        )
    db.commit()

    run = run_plan(
        db,
        "do-scope",
        demand_source="actuals",
        warehouses_scope=[wh_scoped],
        planning_mode="demand_only",
    )
    db.refresh(run)
    whs = {r.warehouse_code for r in db.query(ProjectedInventory).filter(ProjectedInventory.plan_run_id == run.id).all()}
    assert whs == {wh_scoped}
    assert run.progress_meta.get("synthetic_starting_inventory") is True
