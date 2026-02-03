# Forecasting Platform — Functional Spec & Implementation Order

This document is the single source of truth for extending the supply planning system into a full forecasting platform. The app already has:

- **UI:** Enterprise layout (AppShell, LeftNav, MainColumn, TopBar, RightPanel); standardised colours, typography, tables.
- **Backend:** Plan runs, projected inventory, planned orders, trailing-mean forecast, WOS_TARGET/ROP ordering, lead time ceil.
- **Data:** Products, warehouses, suppliers, lanes, planning policies, inventory snapshots, receipts, demand actuals.

Below: required user workflows, explainability, calculation contract, data model extensions, UI screens, reporting, and implementation order.

---

## 1. Core User Workflows (Must Work End-to-End)

### A. Weekly Planning (Main Planner)
- User selects week range (e.g. next 26/52 weeks).
- Filters: warehouse, supplier, brand, category, status (OOS, low cover, expiring).
- SKU-by-week forecast and inventory plan.
- User can: override demand for specific weeks; override lead times / safety stock / MOQ / pack; create/adjust POs or planned orders; approve a plan version and export.

### B. Exception Management (Daily Use)
- "What needs attention": projected stockout within X weeks, late inbound risk, demand spike anomaly, supplier constraint breaches, negative inventory / missing data.
- Each exception has one-click drill-down into SKU explanation.

### C. Scenario Planning
- Scenarios: Base / Conservative / Aggressive / Promo uplift.
- Scenario changes do not overwrite baseline.
- Comparison view: baseline vs scenario deltas (stockouts avoided, cost, inventory).

### D. Calendar View (Per SKU + Portfolio)
- Timeline: inbound arrivals (POs, planned receipts), stockout weeks (red bands), reorder points / recommended order dates, production events, promos/seasonality flags.
- Clicking an event opens RightPanel with calculations + actions.

---

## 2. "Explain the Forecast" (Non-Negotiable)

For every SKU-week, provide an explainability panel showing:

**Demand**
- Baseline forecast method (e.g. moving average, seasonal index).
- Historical weekly demand (last 52 weeks) and math inputs.
- Adjustments applied (manual, promo, outlier removal).

**Supply**
- Current on-hand.
- Open POs / planned orders.
- Lead time components: supplier, haulage, receiving/put-away.
- Safety stock logic: target service level or weeks of cover, demand variability / fixed buffer.
- Constraints: MOQ, pack size, supplier capacity (if available).

**Outputs (per week)**
- Forecast demand, projected ending inventory, weeks of cover, stockout date (if any), recommended order qty/date and why.

Must be visible in UI and exportable (CSV + "SKU explanation report").

---

## 3. Calculation Engine (Deterministic + Testable)

- **Inputs (by SKU, warehouse):** on_hand, inbound_orders, demand_history, lead_time_days, safety_stock_policy, order_policy, constraints (MOQ, pack).
- **Outputs (by SKU-week):** forecast_demand, projected_inventory_end/start, recommended_order_date/qty, stockout_week flag, explanation payload.
- All calculations: pure-function style, versioned (plan_run_id), reproducible from stored inputs.

---

## 4. Data Model (Current + Extensions)

**Current:** products, warehouses, suppliers, lanes, planning_policies, inventory_snapshots_weekly, receipts, demand_actuals, plan_runs, projected_inventory, planned_orders.

**To add (as needed):**
- supplier_sku (lead times, MOQ, pack size).
- forecast_runs / forecast_values (method, horizon, overrides).
- policy_overrides (sku/warehouse overrides).
- plan_versions (baseline/scenario, status, approved_by).
- change_log (audit who changed what).

---

## 5. UI Screens to Implement

| Screen | Purpose |
|--------|--------|
| Portfolio Dashboard | OOS now and projected OOS 4/8/12 weeks; service level proxy; top at-risk SKUs. |
| Weekly Planning Grid | SKU × Week, sticky headers; red/amber/green; inline forecast override; "Create planned order", "View explanation". |
| SKU Detail Page | Tabs: Timeline, Explanation, Parameters, History (demand + inventory chart), Orders. |
| Admin Tuning | Global defaults; per-supplier/warehouse parameters; forecast method per category. |
| Imports/Exports | Already partially there; add exception list export, SKU explanation report export. |

---

## 6. Reporting & Visuals

- Demand history vs forecast (per SKU).
- Inventory projection (on-hand + inbound - demand).
- Weeks of cover trend.
- Stockout timeline (gantt-like bands).
- Exceptions over time; supplier performance (late vs ETA); forecast accuracy (MAPE/bias) if actuals exist.
- Charts: filter by warehouse, supplier, category; export image + data.

---

## 7. Implementation Order

| Phase | Deliverables |
|-------|--------------|
| **Phase 1** | Data ingestion + calculation engine + **SKU-week explanation payload** (API + RightPanel drill-down). |
| **Phase 2** | Weekly planning grid (SKU × Week) + SKU detail page + calendar timeline. |
| **Phase 3** | Exceptions queue + scenario versions + exports (exception list, explanation report). |
| **Phase 4** | Reporting suite + accuracy metrics + optional AI summaries. |

**Default methods (if not already set):**
- Baseline: seasonal moving average (weekly).
- Outlier handling: clamp extreme spikes.
- Safety stock: weeks-of-cover target per category.
- Ordering: reorder point + lot sizing (MOQ/pack).

---

## 8. Definition of Done (Reality Check)

- A planner can open the weekly grid and see **why** each SKU is projected to stock out.
- They can change parameters (lead time, safety stock, overrides) and see impact immediately.
- They can create a planned order file and send it to procurement.
- Exec dashboard shows OOS and risk forward view with drill-down.

If the explainability panel per SKU-week is missing, the system will still get stockouts because nobody will trust or tune the forecast. The UI must make the math visible and editable.
