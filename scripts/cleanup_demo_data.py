#!/usr/bin/env python3
"""Cleanup demo/seed data: remove demo SKUs and related rows.
Run: python scripts/cleanup_demo_data.py (from project root) or cd backend && python ../scripts/cleanup_demo_data.py
Use --dry-run to preview without deleting."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Run from project root: python scripts/cleanup_demo_data.py  OR  cd backend && python ../scripts/cleanup_demo_data.py
_backend = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_backend))
# Ensure .env is loaded from backend/ when run from project root
if (_backend / ".env").exists() and not Path.cwd().joinpath(".env").exists():
    import os
    os.chdir(_backend)

from sqlalchemy import text

from app.database import SessionLocal, engine
from app.models import (
    DemandActual,
    DemandOverrideWeekly,
    InventorySnapshotDaily,
    InventorySnapshotWeekly,
    PlannedOrder,
    PlannedOrderOverrideWeekly,
    PlanningPolicy,
    PlanRun,
    PlanRunDemandInputWeekly,
    PlanRunEvent,
    PlanRunFreezeEvent,
    Product,
    ProjectedInventory,
    Receipt,
    StockOnHandStage,
)


DEMO_SKUS = {"SKU1", "SKU2", "SKU3", "SKU4", "SKU001", "SKU002", "SKU003", "SKU004"}
DEMO_SKU_REGEX = re.compile(r"^SKU(0+)?[0-9]+$", re.IGNORECASE)


def _collect_demo_skus(db) -> set[str]:
    """Products matching DEMO_SKUS or regex ^SKU(0+)?[0-9]+$ (case-insensitive)."""
    all_products = db.query(Product.sku).all()
    skus = set()
    for (sku,) in all_products:
        if sku and (sku in DEMO_SKUS or DEMO_SKU_REGEX.match(sku)):
            skus.add(sku)
    return skus


def _print_safety_banner(db) -> None:
    """Print database name and host so user confirms correct DB."""
    url = engine.url
    db_name = url.database or "?"
    host = url.host or "?"
    port = url.port or ""
    host_port = f"{host}:{port}" if port else host
    try:
        row = db.execute(text("SELECT current_database(), inet_server_addr()::text")).fetchone()
        db_actual = row[0] if row else "?"
        addr = row[1] if row and len(row) > 1 else "?"
        print(f"\n=== CLEANUP DEMO DATA ===")
        print(f"Database (from URL): {db_name} @ {host_port}")
        print(f"Database (from SQL):  {db_actual} @ {addr}")
        print("=" * 40)
    except Exception as e:
        print(f"\n=== CLEANUP DEMO DATA ===")
        print(f"Database (from URL): {db_name} @ {host_port}")
        print(f"(Could not run SELECT: {e})")
        print("=" * 40)


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove demo SKU data")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, do not delete")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        _print_safety_banner(db)

        # Collect demo SKUs: explicit set + regex match
        demo_skus = _collect_demo_skus(db)
        if not demo_skus:
            print("No demo products found (DEMO_SKUS or regex ^SKU(0+)?[0-9]+$).")
            return

        skus_sorted = sorted(demo_skus)
        print(f"Demo SKUs to remove ({len(skus_sorted)}):")
        print(f"  Explicit: {[s for s in skus_sorted if s in DEMO_SKUS]}")
        regex_only = [s for s in skus_sorted if s not in DEMO_SKUS]
        if regex_only:
            print(f"  Regex match: {regex_only}")
        print()

        # Plan run IDs that contain demo SKUs
        plan_run_ids = set()
        for row in db.query(ProjectedInventory.plan_run_id).filter(
            ProjectedInventory.sku.in_(skus_sorted)
        ).distinct().all():
            if row[0]:
                plan_run_ids.add(row[0])
        for row in db.query(PlannedOrder.plan_run_id).filter(
            PlannedOrder.sku.in_(skus_sorted)
        ).distinct().all():
            if row[0]:
                plan_run_ids.add(row[0])
        plan_run_ids = sorted(plan_run_ids)

        # Counts per table
        counts: dict[str, int] = {}
        tables = [
            (DemandActual, "demand_actuals", "sku"),
            (InventorySnapshotWeekly, "inventory_snapshots_weekly", "sku"),
            (PlanningPolicy, "planning_policies", "sku"),
            (Receipt, "receipts", "sku"),
            (PlanRunDemandInputWeekly, "plan_run_demand_inputs_weekly", "sku"),
            (ProjectedInventory, "projected_inventory", "sku"),
            (PlannedOrder, "planned_orders", "sku"),
        ]
        for model, name, col in tables:
            if hasattr(model, col):
                counts[name] = db.query(model).filter(getattr(model, col).in_(skus_sorted)).count()
            else:
                counts[name] = 0

        # Plan-run child tables (by plan_run_id)
        if plan_run_ids:
            counts["plan_run_events"] = db.query(PlanRunEvent).filter(
                PlanRunEvent.plan_run_id.in_(plan_run_ids)
            ).count()
            counts["plan_run_freeze_events"] = db.query(PlanRunFreezeEvent).filter(
                PlanRunFreezeEvent.plan_run_id.in_(plan_run_ids)
            ).count()
            counts["demand_overrides_weekly"] = db.query(DemandOverrideWeekly).filter(
                DemandOverrideWeekly.plan_run_id.in_(plan_run_ids)
            ).count()
            counts["planned_order_overrides_weekly"] = db.query(PlannedOrderOverrideWeekly).filter(
                PlannedOrderOverrideWeekly.plan_run_id.in_(plan_run_ids)
            ).count()
        else:
            counts["plan_run_events"] = 0
            counts["plan_run_freeze_events"] = 0
            counts["demand_overrides_weekly"] = 0
            counts["planned_order_overrides_weekly"] = 0

        counts["plan_runs"] = len(plan_run_ids)

        # Optional: stock_on_hand_stage, inventory_snapshots_daily
        try:
            counts["stock_on_hand_stage"] = db.query(StockOnHandStage).filter(
                StockOnHandStage.aah_code_raw.in_(skus_sorted)
            ).count()
        except Exception:
            counts["stock_on_hand_stage"] = -1  # model/table may not exist

        try:
            counts["inventory_snapshots_daily"] = db.query(InventorySnapshotDaily).filter(
                InventorySnapshotDaily.sku.in_(skus_sorted)
            ).count()
        except Exception:
            counts["inventory_snapshots_daily"] = -1

        # Products
        counts["products"] = len(skus_sorted)

        # Print counts
        print("Rows to delete:")
        for name, n in counts.items():
            if n == -1:
                print(f"  {name}: (skipped - model/table not available)")
            elif n > 0:
                print(f"  {name}: {n}")
        if plan_run_ids:
            print(f"\nPlan run IDs to delete: {plan_run_ids}")
        print()

        if args.dry_run:
            print("[DRY RUN] No changes made. Run without --dry-run to delete.")
            return

        # Execute deletions in a transaction
        try:
            # 1) Plan run children (FK-safe order)
            if plan_run_ids:
                db.query(PlanRunDemandInputWeekly).filter(
                    PlanRunDemandInputWeekly.plan_run_id.in_(plan_run_ids)
                ).delete(synchronize_session=False)
                db.query(ProjectedInventory).filter(
                    ProjectedInventory.plan_run_id.in_(plan_run_ids)
                ).delete(synchronize_session=False)
                db.query(PlannedOrder).filter(
                    PlannedOrder.plan_run_id.in_(plan_run_ids)
                ).delete(synchronize_session=False)
                db.query(DemandOverrideWeekly).filter(
                    DemandOverrideWeekly.plan_run_id.in_(plan_run_ids)
                ).delete(synchronize_session=False)
                db.query(PlannedOrderOverrideWeekly).filter(
                    PlannedOrderOverrideWeekly.plan_run_id.in_(plan_run_ids)
                ).delete(synchronize_session=False)
                db.query(PlanRunEvent).filter(
                    PlanRunEvent.plan_run_id.in_(plan_run_ids)
                ).delete(synchronize_session=False)
                db.query(PlanRunFreezeEvent).filter(
                    PlanRunFreezeEvent.plan_run_id.in_(plan_run_ids)
                ).delete(synchronize_session=False)
                db.query(PlanRun).filter(PlanRun.id.in_(plan_run_ids)).delete(synchronize_session=False)

            # 2) Also delete any remaining orphaned projected/planned by sku (runs we didn't touch)
            db.query(PlanRunDemandInputWeekly).filter(
                PlanRunDemandInputWeekly.sku.in_(skus_sorted)
            ).delete(synchronize_session=False)
            db.query(ProjectedInventory).filter(
                ProjectedInventory.sku.in_(skus_sorted)
            ).delete(synchronize_session=False)
            db.query(PlannedOrder).filter(
                PlannedOrder.sku.in_(skus_sorted)
            ).delete(synchronize_session=False)

            # 3) Source tables
            db.query(DemandActual).filter(DemandActual.sku.in_(skus_sorted)).delete(synchronize_session=False)
            db.query(InventorySnapshotWeekly).filter(
                InventorySnapshotWeekly.sku.in_(skus_sorted)
            ).delete(synchronize_session=False)
            db.query(PlanningPolicy).filter(PlanningPolicy.sku.in_(skus_sorted)).delete(synchronize_session=False)
            db.query(Receipt).filter(Receipt.sku.in_(skus_sorted)).delete(synchronize_session=False)

            # 4) Optional tables
            if counts.get("stock_on_hand_stage", 0) > 0:
                db.query(StockOnHandStage).filter(
                    StockOnHandStage.aah_code_raw.in_(skus_sorted)
                ).delete(synchronize_session=False)
            if counts.get("inventory_snapshots_daily", 0) > 0:
                db.query(InventorySnapshotDaily).filter(
                    InventorySnapshotDaily.sku.in_(skus_sorted)
                ).delete(synchronize_session=False)

            # 5) Products
            db.query(Product).filter(Product.sku.in_(skus_sorted)).delete(synchronize_session=False)

            db.commit()
            print("Demo data removed successfully.")
        except Exception as e:
            db.rollback()
            print(f"\nERROR: {e}")
            print("Transaction rolled back. No changes applied.")
            raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
