# Part 0 — Verification Report

## 1) Plan run model includes warehouse_code or not

**Finding:** Plan run model does **NOT** include `warehouse_code` or `warehouses_scope`.

Current `PlanRun` columns: id, scenario_name, run_at, created_at, demand_source, freeze_weeks, plan_start_week_start, created_by, notes, baseline_train_end_week_start, selected_train_end_week_start.

## 2) Planning.run_plan currently loops policies ∩ starting_inv across warehouses

**Finding:** Yes. The loop is:

- `sku_wh_set = set(policy_by_key.keys()) | set(starting_inv.keys())` — union of (sku, warehouse) from policies and starting_inv
- For each `(sku, wh_code)` in `sku_wh_set`:
  - Requires `policy` (from policy_by_key)
  - Requires `start_data` (from starting_inv)
  - If either missing → `continue` (skip)

**Critical:** `starting_inv` is built only from `InventorySnapshotWeekly` where `warehouse_code.in_(soh_warehouses)` — and `soh_warehouses = get_sample_sales_soh_warehouses(db)` defaults to **["BLP"]**. So AAH SOH is never used.

**Policies** are loaded from all warehouses (no filter). **Demand** is loaded from all warehouses (no filter).

## 3) demand_actuals and inventory_snapshots_weekly keyed by warehouse_code

**Finding:** Yes. Both tables have `warehouse_code` as a column and use it in their unique constraints:

- `inventory_snapshots_weekly`: UniqueConstraint("week_start", "sku", "warehouse_code", "source_type")
- `demand_actuals`: UniqueConstraint("week_start", "sku", "warehouse_code", "demand_type")

Data is partitioned by warehouse_code.
