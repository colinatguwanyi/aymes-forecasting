# Fake Data Root Cause Report

## Summary

**Fake data comes from:** `backend/app/seed.py` and `backend/app/seed_backbone.py` (when run manually), plus `data/demand_actuals_import.csv` and `data/inventory_snapshots_import.csv` (sample imports). **SKU1/SKU2/SKU4** appear in `backend/tests/test_warehouse_scope_planning.py` (test fixtures only).

**No automatic seeding on app startup.** The app does NOT call `seed()` or `seed_backbone()` at startup. They run only when invoked explicitly: `python -m app.seed` or `python -m app.seed_backbone`.

---

## 1) Seed / Demo Sources (Code Trace)

| File | What it writes | SKUs | Trigger |
|------|----------------|------|---------|
| `backend/app/seed.py` | products, warehouses, suppliers, lanes, planning_policies, inventory_snapshots_weekly, receipts, demand_actuals | SKU001, SKU002, SKU003 | `python -m app.seed` |
| `backend/app/seed_backbone.py` | calendar_weeks, warehouses, products, suppliers, warehouse_products, supplier_products, stock_positions_weekly, demand_weekly | SKU001, SKU002, SKU003 | `python -m app.seed_backbone` |
| `data/demand_actuals_import.csv` | demand_actuals (via Imports) | SKU001–SKU004 | User imports via UI |
| `data/inventory_snapshots_import.csv` | inventory_snapshots_weekly (via Imports) | SKU-A-*, SKU-AG*, etc. | User imports via UI |
| `backend/tests/test_warehouse_scope_planning.py` | Test DB only | SKU1, SKU2, SKU3, SKU4 | pytest |

---

## 2) Planning Engine — No Fallback Generators

- **`backend/app/services/planning.py`**: No "if empty, generate demo rows". It only projects for (sku, warehouse) present in both `policy_by_key` and `starting_inv`. Missing data → warehouse skipped with blockers.
- **`backend/app/services/demand_resolver.py`**: Resolves demand from actuals/forecast; no fabrication.

---

## 3) Root Cause Statement

**"Fake data comes from `backend/app/seed.py` and `backend/app/seed_backbone.py`. They write products, planning_policies, inventory_snapshots_weekly, demand_actuals (seed.py) and backbone tables (seed_backbone). They trigger when the user runs `python -m app.seed` or `python -m app.seed_backbone` (e.g. per README/POSTGRES_SETUP)."**

**SKU1/SKU2/SKU4** (without leading zeros) appear only in `test_warehouse_scope_planning.py`. If these show in production, they likely came from:
- A test run against the same DB, or
- A product import / mapping that created products with those SKUs.

---

## 4) SQL Trace (Phase A)

Run `scripts/trace_plan_run_33.sql` to confirm:
- Which SKUs are in projected_inventory and planned_orders for plan_run_id=33
- Counts of demand_actuals and inventory_snapshots_weekly for AAH
- Whether SKU1/SKU2/SKU3/SKU4 or SKU001/SKU002/etc. exist in products

---

## 5) Fixes Applied (Phase B)

- **ALLOW_DEMO_DATA=false** by default; seed scripts exit early when false
- **run_plan() guards**: Assert all SKUs/warehouses in outputs exist in products/warehouses; fail with clear error if demo data detected
- **Cleanup script**: `scripts/cleanup_demo_data.py` to remove demo SKUs and related rows
- **Frontend**: Banner for "Demo data disabled" and "planning_inputs_missing" errors
