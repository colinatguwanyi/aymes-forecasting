#!/usr/bin/env python3
"""Cleanup demo/seed data: remove demo SKUs and related rows.
Run: python scripts/cleanup_demo_data.py (from project root) or cd backend && python ../scripts/cleanup_demo_data.py
Use --dry-run to preview without deleting."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Run from project root: python scripts/cleanup_demo_data.py  OR  cd backend && python ../scripts/cleanup_demo_data.py
_backend = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_backend))

from app.database import SessionLocal
from app.models import (
    DemandActual,
    InventorySnapshotWeekly,
    PlannedOrder,
    PlanningPolicy,
    PlanRunDemandInputWeekly,
    Product,
    ProjectedInventory,
    Receipt,
)


DEMO_SKUS = {"SKU1", "SKU2", "SKU3", "SKU4", "SKU001", "SKU002", "SKU003", "SKU004"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove demo SKU data")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, do not delete")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        products_to_delete = db.query(Product).filter(Product.sku.in_(DEMO_SKUS)).all()
        if not products_to_delete:
            print("No demo products (SKU1-4, SKU001-004) found.")
            return

        skus = [p.sku for p in products_to_delete]
        print(f"Demo SKUs to remove: {skus}")

        # Count related rows
        tables = [
            (DemandActual, "demand_actuals"),
            (InventorySnapshotWeekly, "inventory_snapshots_weekly"),
            (PlanningPolicy, "planning_policies"),
            (Receipt, "receipts"),
        ]
        for model, name in tables:
            if hasattr(model, "sku"):
                count = db.query(model).filter(model.sku.in_(skus)).count()
            else:
                count = 0
            if count:
                print(f"  {name}: {count} rows")

        # Projected inventory and planned orders (by plan_run that has demo SKUs)
        proj_count = db.query(ProjectedInventory).filter(ProjectedInventory.sku.in_(skus)).count()
        plan_count = db.query(PlannedOrder).filter(PlannedOrder.sku.in_(skus)).count()
        if proj_count:
            print(f"  projected_inventory: {proj_count} rows")
        if plan_count:
            print(f"  planned_orders: {plan_count} rows")

        if args.dry_run:
            print("\n[DRY RUN] No changes made. Run without --dry-run to delete.")
            return

        # Delete in order (respect FKs): demand inputs, projections, orders, then source tables, then products
        db.query(PlanRunDemandInputWeekly).filter(PlanRunDemandInputWeekly.sku.in_(skus)).delete(synchronize_session=False)
        db.query(ProjectedInventory).filter(ProjectedInventory.sku.in_(skus)).delete(synchronize_session=False)
        db.query(PlannedOrder).filter(PlannedOrder.sku.in_(skus)).delete(synchronize_session=False)
        for model, _ in tables:
            if hasattr(model, "sku"):
                db.query(model).filter(model.sku.in_(skus)).delete(synchronize_session=False)

        for p in products_to_delete:
            db.delete(p)

        db.commit()
        print("\nDemo data removed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
