"""Seed backbone schema: calendar_weeks, warehouses, products, suppliers, warehouse_products, supplier_products, demo stock/demand."""
from __future__ import annotations
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.calendar_weeks import ensure_calendar_week, week_start_end
from app.database import SessionLocal
from app.models import (
    CalendarWeek,
    DemandWeekly,
    DemandSourceEnum,
    Product,
    StockPositionWeekly,
    StockSourceEnum,
    Supplier,
    SupplierProduct,
    Warehouse,
    WarehouseProduct,
    SafetyStockModeEnum,
)

logger = logging.getLogger(__name__)


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def iso_year_week(d: date) -> tuple[int, int]:
    iso = d.isocalendar()
    return iso.year, iso.week


def seed_backbone() -> None:
    db = SessionLocal()
    try:
        # Calendar weeks: 2025-W01 through 2025-W52 + a bit of 2026
        for y in (2024, 2025, 2026):
            for w in range(1, 53):
                if db.query(CalendarWeek).filter(CalendarWeek.iso_year == y, CalendarWeek.iso_week == w).first():
                    continue
                start, end = week_start_end(y, w)
                db.add(CalendarWeek(iso_year=y, iso_week=w, week_start_date=start, week_end_date=end))
        db.commit()
        db.flush()

        # Warehouses (ensure new columns; existing rows get defaults from migration)
        for code, name in [("WH1", "Warehouse 1"), ("WH2", "Warehouse 2")]:
            if not db.query(Warehouse).filter(Warehouse.code == code).first():
                db.add(Warehouse(code=code, name=name, timezone="Europe/London", active=True))
        db.flush()
        wh1 = db.query(Warehouse).filter(Warehouse.code == "WH1").first()
        wh2 = db.query(Warehouse).filter(Warehouse.code == "WH2").first()

        # Products
        for sku, name in [("SKU001", "Product A"), ("SKU002", "Product B"), ("SKU003", "Product C")]:
            if not db.query(Product).filter(Product.sku == sku).first():
                db.add(Product(sku=sku, name=name, uom="units", active=True))
        db.flush()
        p1 = db.query(Product).filter(Product.sku == "SKU001").first()
        p2 = db.query(Product).filter(Product.sku == "SKU002").first()
        p3 = db.query(Product).filter(Product.sku == "SKU003").first()

        # Suppliers
        if not db.query(Supplier).filter(Supplier.code == "SUP1").first():
            db.add(Supplier(code="SUP1", name="Supplier 1", active=True))
        db.flush()
        sup1 = db.query(Supplier).filter(Supplier.code == "SUP1").first()

        if not wh1 or not p1 or not p2 or not p3 or not sup1:
            logger.warning("Missing wh1/p1/p2/p3/sup1; skip warehouse_products/supplier_products")
        else:
            # WarehouseProduct: WH1 + each product
            for wh, prod in [(wh1, p1), (wh1, p2), (wh1, p3), (wh2, p1), (wh2, p2)]:
                if not db.query(WarehouseProduct).filter(
                    WarehouseProduct.warehouse_id == wh.id,
                    WarehouseProduct.product_id == prod.id,
                ).first():
                    db.add(
                        WarehouseProduct(
                            warehouse_id=wh.id,
                            product_id=prod.id,
                            safety_stock_mode=SafetyStockModeEnum.FIXED_UNITS,
                            safety_stock_units=50,
                            haulage_buffer_weeks=0,
                            stocking_buffer_weeks=0,
                            reorder_review_weeks=1,
                            active=True,
                        )
                    )
            # SupplierProduct: SUP1 supplies all
            for prod in (p1, p2, p3):
                if not db.query(SupplierProduct).filter(
                    SupplierProduct.supplier_id == sup1.id,
                    SupplierProduct.product_id == prod.id,
                ).first():
                    db.add(
                        SupplierProduct(
                            supplier_id=sup1.id,
                            product_id=prod.id,
                            lead_time_weeks=2,
                            moq_units=100,
                            pack_size_units=10,
                            active=True,
                        )
                    )
        db.flush()

        # Demo stock: current ISO week, WH1, SKU001=200, SKU002=150, SKU003=80
        today = date.today()
        y, w = iso_year_week(monday(today))
        cw = ensure_calendar_week(db, y, w)
        if wh1 and p1 and p2 and p3:
            for prod, qty in [(p1, 200), (p2, 150), (p3, 80)]:
                if not db.query(StockPositionWeekly).filter(
                    StockPositionWeekly.warehouse_id == wh1.id,
                    StockPositionWeekly.product_id == prod.id,
                    StockPositionWeekly.calendar_week_id == cw.id,
                ).first():
                    db.add(
                        StockPositionWeekly(
                            warehouse_id=wh1.id,
                            product_id=prod.id,
                            calendar_week_id=cw.id,
                            on_hand_units=qty,
                            source=StockSourceEnum.IMPORT,
                        )
                    )
        db.flush()

        # Demo demand: same week and next 3 weeks, WH1, SKU001=30/wk, SKU002=20, SKU003=15
        for i in range(4):
            wy, ww = y, w + i
            if ww > 52:
                ww -= 52
                wy += 1
            cwd = ensure_calendar_week(db, wy, ww)
            if wh1 and p1 and p2 and p3:
                for prod, qty in [(p1, 30), (p2, 20), (p3, 15)]:
                    if not db.query(DemandWeekly).filter(
                        DemandWeekly.warehouse_id == wh1.id,
                        DemandWeekly.product_id == prod.id,
                        DemandWeekly.calendar_week_id == cwd.id,
                    ).first():
                        db.add(
                            DemandWeekly(
                                warehouse_id=wh1.id,
                                product_id=prod.id,
                                calendar_week_id=cwd.id,
                                demand_units=qty,
                                source=DemandSourceEnum.IMPORT,
                            )
                        )
        db.commit()
        logger.info("Backbone seed done: calendar_weeks, warehouses, products, suppliers, warehouse_products, supplier_products, demo stock/demand")
    finally:
        db.close()


if __name__ == "__main__":
    seed_backbone()
