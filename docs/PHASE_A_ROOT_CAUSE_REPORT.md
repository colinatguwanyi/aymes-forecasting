# Phase A: Root Cause Report — "No Data" Across Key Pages

## Summary

**Pages empty because:** The planning engine uses SOH from `sample_sales_soh_warehouses` (default **BLP**), while Data Health and common imports use **AAH**. If SOH and policies are for AAH but the config expects BLP, the engine produces zero projections.

---

## 1) API Calls and Params (from code trace)

| Page | API | Params | Notes |
|------|-----|--------|-------|
| Stock Position | `GET /api/stock-position/breakdown` | `plan_run_id` (required), `warehouse_code`, `sku`, `product_family`, `breach_only` | No auto-select of plan run (fixed in Phase B) |
| Inventory Projection | `GET /api/plan/runs/{id}/projected-inventory` | `plan_run_id` via path, `sku`, `warehouse_code` | Auto-selects latest run |
| Weekly Planning Grid | Same as above | Same | Auto-selects from query or first run |
| Planned Orders | `GET /api/plan/runs/{id}/planned-orders` | Same | No auto-select (fixed in Phase B) |

All pages require a valid `plan_run_id`. If none is selected, they show "No data" or equivalent.

---

## 2) Plan Run Execution Flow

- **Endpoint:** `POST /api/plan/run` → `run_plan()` in `backend/app/services/planning.py`
- **Writes:** `projected_inventory`, `planned_orders` (and `plan_run_demand_inputs_weekly` via demand resolver)
- **Logic:** For each (sku, warehouse) in `policy_by_key` ∩ `starting_inv`:
  - Requires a **planning policy** for (sku, warehouse)
  - Requires **starting inventory** (SOH) from `inventory_snapshots_weekly` filtered by `sample_sales_soh_warehouses`
- **If either is missing:** That (sku, warehouse) is skipped → no projections.

---

## 3) Most Likely Causes (from code)

### A) **Warehouse mismatch (primary)**

- **Data Health** checks: `demand_actuals` (AAH), `inventory_snapshots_weekly` (AAH)
- **Planning engine** uses: `get_sample_sales_soh_warehouses(db)` → default **["BLP"]**
- **Result:** If SOH is only for AAH, `starting_inv` is empty → no projections.

### B) **Policy vs SOH warehouse mismatch**

- Policies may exist for (sku, AAH)
- Planning expects SOH for BLP
- No overlap → no rows.

### C) **Missing planning policies**

- No policies → `policy_by_key` empty → nothing to project.

### D) **No plan run selected**

- Stock Position and Planned Orders did not auto-select a run → empty until user selects one.

---

## 4) Evidence (code references)

- `backend/app/services/app_settings.py`: `DEFAULT_SAMPLE_SALES_SOH_WAREHOUSES = ["BLP"]`
- `backend/app/routers/data_health.py`: demand/SOH filtered by `warehouse_code == "AAH"`
- `backend/app/services/planning.py` lines 102–106: SOH filtered by `soh_warehouses` (from config)
- `backend/app/services/planning.py` lines 227–233: `if not policy: continue` and `if not start_data: continue`

---

## 5) Recommended Fix

1. **Admin → Settings:** Set `sample_sales_soh_warehouses` to `["AAH"]` if your SOH and demand use AAH.
2. **Policies:** Ensure policies exist for (sku, warehouse) where warehouse is in `sample_sales_soh_warehouses`.
3. **Data Health:** Use it to confirm demand, SOH, and policies align before running a plan.
