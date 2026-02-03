"""Seed database with sample products, warehouses, policies, inventory, receipts, demand."""
from __future__ import annotations
import logging
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

# Ensure app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models import (
    DemandActual,
    DemandType,
    InventorySnapshotWeekly,
    Lane,
    PlanningMode,
    PlanningPolicy,
    Product,
    Receipt,
    SafetyStockMethod,
    Supplier,
    Warehouse,
)

logger = logging.getLogger(__name__)


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def seed() -> None:
    db = SessionLocal()
    try:
        # Products
        for sku, name in [("SKU001", "Product A"), ("SKU002", "Product B"), ("SKU003", "Product C")]:
            if not db.query(Product).filter(Product.sku == sku).first():
                db.add(Product(sku=sku, name=name))
        db.flush()

        # Warehouses
        wh_codes = [("WH1", "Warehouse 1"), ("WH2", "Warehouse 2")]
        for code, name in wh_codes:
            if not db.query(Warehouse).filter(Warehouse.code == code).first():
                db.add(Warehouse(code=code, name=name))
        db.flush()
        wh1 = db.query(Warehouse).filter(Warehouse.code == "WH1").first()
        wh2 = db.query(Warehouse).filter(Warehouse.code == "WH2").first()

        # Suppliers & lanes
        if not db.query(Supplier).filter(Supplier.code == "SUP1").first():
            s = Supplier(code="SUP1", name="Supplier 1")
            db.add(s)
            db.flush()
            if wh1:
                db.add(Lane(supplier_id=s.id, warehouse_id=wh1.id, code="SUP1-WH1"))
        db.flush()

        # Planning policies
        for sku in ["SKU001", "SKU002", "SKU003"]:
            for wcode in ["WH1", "WH2"]:
                if not db.query(PlanningPolicy).filter(PlanningPolicy.sku == sku, PlanningPolicy.warehouse_code == wcode).first():
                    db.add(
                        PlanningPolicy(
                            sku=sku,
                            warehouse_code=wcode,
                            mode=PlanningMode.WOS_TARGET,
                            target_weeks=Decimal("4"),
                            safety_stock_method=SafetyStockMethod.WEEKS,
                            safety_stock_weeks=Decimal("1"),
                            forecast_window_weeks=8,
                            lead_time_production_weeks=Decimal("2"),
                            lead_time_haulage_weeks=Decimal("1"),
                        )
                    )

        # Inventory snapshots (last week = Monday)
        base = monday(date.today()) - timedelta(days=7)
        for sku in ["SKU001", "SKU002", "SKU003"]:
            for wcode in ["WH1", "WH2"]:
                if not db.query(InventorySnapshotWeekly).filter(
                    InventorySnapshotWeekly.week_start == base,
                    InventorySnapshotWeekly.sku == sku,
                    InventorySnapshotWeekly.warehouse_code == wcode,
                ).first():
                    db.add(
                        InventorySnapshotWeekly(
                            week_start=base,
                            sku=sku,
                            warehouse_code=wcode,
                            on_hand_qty=Decimal("100"),
                        )
                    )

        # Receipts (next 2 weeks)
        for i in range(1, 3):
            w = base + timedelta(days=7 * i)
            for sku in ["SKU001", "SKU002"]:
                if not db.query(Receipt).filter(Receipt.week_start == w, Receipt.sku == sku, Receipt.warehouse_code == "WH1").first():
                    db.add(
                        Receipt(
                            week_start=w,
                            sku=sku,
                            warehouse_code="WH1",
                            qty=Decimal("50"),
                            source_type="PO",
                        )
                    )

        # Demand actuals (past 8 weeks: CUSTOMER + SAMPLES)
        for i in range(8, 0, -1):
            w = base - timedelta(days=7 * i)
            for sku in ["SKU001", "SKU002", "SKU003"]:
                for wcode in ["WH1", "WH2"]:
                    if not db.query(DemandActual).filter(
                        DemandActual.week_start == w,
                        DemandActual.sku == sku,
                        DemandActual.warehouse_code == wcode,
                        DemandActual.demand_type == DemandType.CUSTOMER,
                    ).first():
                        db.add(
                            DemandActual(
                                week_start=w,
                                sku=sku,
                                warehouse_code=wcode,
                                demand_type=DemandType.CUSTOMER,
                                qty=Decimal("20"),
                            )
                        )
                    if not db.query(DemandActual).filter(
                        DemandActual.week_start == w,
                        DemandActual.sku == sku,
                        DemandActual.warehouse_code == wcode,
                        DemandActual.demand_type == DemandType.SAMPLES,
                    ).first():
                        db.add(
                            DemandActual(
                                week_start=w,
                                sku=sku,
                                warehouse_code=wcode,
                                demand_type=DemandType.SAMPLES,
                                qty=Decimal("2"),
                            )
                        )

        db.commit()
        print("Seed completed.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
