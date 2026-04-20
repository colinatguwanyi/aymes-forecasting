# Current Build, DB Schema, Module List & Screenshots

This document describes the AYMES forecasting / supply planning app as built: stack, database schema, folder structure, and where to add screenshots of key screens.

---

## 1. Current Build

### Stack

| Layer      | Technology |
|-----------|------------|
| Frontend  | Vue 3 (Composition API), TypeScript, Vite 5, Pinia, Vue Router |
| Styling   | Tailwind CSS 4, global layout CSS variables |
| Backend   | FastAPI, Python 3.11+ |
| Database  | PostgreSQL 14+ |
| ORM       | SQLAlchemy 2.x |
| Migrations| Alembic |

### Frontend

- **Package manager:** npm  
- **Scripts:** `npm run dev` (Vite dev server, port 5173), `npm run build` (vue-tsc + vite build), `npm run preview`  
- **Key deps:** vue, vue-router, pinia, axios, chart.js, vue-chartjs, tailwindcss, @tailwindcss/vite  
- **Output:** `frontend/dist/` (static SPA)

### Backend

- **Server:** uvicorn — `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`  
- **API base:** `/api` (e.g. `/api/products`, `/api/plan/runs`, `/api/timeline`)  
- **Docs:** http://127.0.0.1:8000/docs  
- **Key deps:** fastapi, uvicorn, sqlalchemy, alembic, psycopg2-binary, pydantic, pandas  

### Running the app

1. **Database:** Create DB, run `alembic upgrade head`, optionally `python -m app.seed`.  
2. **Backend:** From `backend/`, run uvicorn (see above).  
3. **Frontend:** From `frontend/`, run `npm run dev`.  
4. **Production-style:** Build frontend (`npm run build`), then backend can serve `frontend/dist/` at `/` and API at `/api`.

---

## 2. Database Schema (Table Names + Key Columns)

Tables are defined in `backend/app/models.py`. Key columns only; not every column is listed.

### Core / planning (used by plan runs and projections)

| Table                 | Key columns | Notes |
|-----------------------|------------|--------|
| **products**          | id, sku (unique), name, description, uom, active, aah_code, brand, product_family, selling_unit_text, single_unit_content, content_uom, is_recipe | Master products. **Canonical SKU:** products.sku = TRIM(SKU code), case preserved. **aah_code:** reference only (nullable, non-unique); never used as join key; NULL if blank/NA/N/A/-/null (case-insensitive). |
| **warehouses**        | id, code (unique), name, timezone, active | Warehouses |
| **suppliers**         | id, code (unique), name, active | Suppliers |
| **lanes**             | id, supplier_id (FK), warehouse_id (FK), code | Supplier → warehouse lanes |
| **planning_policies** | id, sku, warehouse_code (unique with sku), mode, target_weeks, safety_stock_*, forecast_window_weeks, lead_time_*_weeks, include_samples | SKU × warehouse planning params |
| **plan_runs**         | id, scenario_name, run_at, created_at, demand_source, freeze_weeks, created_by, notes | Each plan execution; demand_source: 'actuals' \| 'baseline' \| 'blended' (default actuals); freeze_weeks default 4 |
| **plan_run_demand_inputs_weekly** | id, plan_run_id (FK), week_start, sku, warehouse_code, demand_qty, source, source_ref, is_frozen | Materialized demand used by run; unique (plan_run_id, week_start, sku, warehouse_code) |
| **demand_overrides_weekly** | id, plan_run_id (FK), week_start, sku, warehouse_code, override_qty, reason_code, notes, created_at, created_by | Planner demand overrides; unique per run/week/sku/warehouse |
| **planned_order_overrides_weekly** | id, plan_run_id (FK), week_start, sku, warehouse_code, override_order_qty, reason_code, notes, created_at, created_by | Planner order overrides |
| **plan_run_freeze_events** | id, plan_run_id (FK), frozen_at, frozen_by, freeze_weeks, scope ('demand' \| 'orders' \| 'both'), notes | Audit trail for freeze actions |
| **projected_inventory** | id, plan_run_id (FK), week_start, sku, warehouse_code, start_qty, receipts_qty, demand_qty, projected_qty, weeks_of_cover, stockout | Per-week projection per run |
| **planned_orders**   | id, plan_run_id (FK), week_start, sku, warehouse_code, order_qty, is_frozen | Output of plan run; is_frozen for freeze window |

### Weekly time series (snapshots, receipts, demand)

| Table                       | Key columns | Notes |
|----------------------------|------------|--------|
| **inventory_snapshots_weekly** | id, week_start, sku, warehouse_code, on_hand_qty | Unique (week_start, sku, warehouse_code) |
| **receipts**               | id, week_start, sku, warehouse_code, qty, source_type | Inbound receipts |
| **demand_actuals**         | id, week_start, sku, warehouse_code, demand_type (enum), qty | Unique (week_start, sku, warehouse_code, demand_type) |

### Ingestion and canonical weekly (W-TUE bucketing)

| Table                   | Key columns | Notes |
|-------------------------|------------|--------|
| **ingestion_runs**      | id (UUID), source_type, entity, file_name, status, row_count, inserted_count, rejected_count, started_at, finished_at | Per-upload run |
| **ingestion_rejections**| id, ingestion_run_id (FK), row_number, raw_payload, reason | Rejected rows |
| **product_master_stage**| id, ingestion_run_id (FK), row_number, payload (JSONB) | Staged product-master rows before import |
| **sku_code_map**        | id, old_sku, new_sku, effective_from_week_start, effective_to_week_start | SKU mapping for staging → canonical |
| **demand_stage_weekly**  | id, ingestion_run_id (FK), week_start, sku_raw, sku, warehouse_code, demand_type, qty | Staged demand before transform |
| **demand_facts_weekly**  | id, week_start, sku, warehouse_code, demand_type, qty, source_run_id, is_imputed, is_outlier | Canonical weekly demand (single truth for forecasting) |
| **baseline_forecasts_weekly** | id, sku, warehouse_code, week_start, horizon_week_index, forecast_qty, model_name, model_version, train_end_week_start | Baseline forecast output; unique (sku, warehouse_code, week_start, model_name, model_version) |

### Backbone (admin / extended model)

| Table                   | Key columns | Notes |
|-------------------------|------------|--------|
| **supplier_products**   | id, supplier_id (FK), product_id (FK), lead_time_weeks, moq_units, pack_size_units, active | Unique (supplier_id, product_id); product-master sets lead_time_weeks, moq_units, pack_size_units |
| **product_master_attributes** | id, sku (FK products.sku), shelf_life_text, hs_code, pallet_weight_kg, pallet_dimensions_text, ti_hi, price_unit, cogs_unit, cogs_selling_unit, currency, created_at | Optional logistics/cost per SKU; unique (sku) |
| **warehouse_products**   | id, warehouse_id (FK), product_id (FK), safety_stock_mode, safety_stock_units/weeks, haulage_buffer_weeks, stocking_buffer_weeks, reorder_review_weeks, active | Unique (warehouse_id, product_id) |
| **calendar_weeks**       | id, iso_year, iso_week, week_start_date, week_end_date | Unique (iso_year, iso_week) |
| **stock_positions_weekly** | id, warehouse_id, product_id, calendar_week_id, on_hand_units, source | Backbone stock |
| **inbound_orders_weekly**  | id, warehouse_id, product_id, supplier_id, calendar_week_id, inbound_units, source | Backbone inbound |
| **demand_weekly**       | id, warehouse_id, product_id, calendar_week_id, demand_units, source | Backbone demand |
| **projections_weekly**  | id, warehouse_id, product_id, calendar_week_id, opening/inbound/demand/closing_units, weeks_of_supply, breach_status, run_id | Backbone projection output |

---

## 3. Module List / Folder Structure

### Repository root

```
aymes-forecasting/
├── backend/           # FastAPI app
├── frontend/          # Vue 3 SPA
├── docs/               # Specs, setup, this doc
├── data/               # Sample CSVs
├── scripts/            # Build/deploy scripts
├── .cursor/            # Editor rules
├── .gitignore
├── pyrightconfig.json
└── README.md
```

### Backend (`backend/`)

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, CORS, route includes, SPA serve
│   ├── config.py            # Config / env
│   ├── database.py          # SQLAlchemy engine/session
│   ├── models.py            # All SQLAlchemy models (schema above)
│   ├── schemas.py           # Pydantic request/response models
│   ├── calendar_weeks.py    # Calendar week helpers
│   ├── seed.py              # Seed products, warehouses, policies, etc.
│   ├── seed_backbone.py     # Backbone seed if used
│   ├── routers/
│   │   ├── products.py
│   │   ├── warehouses.py
│   │   ├── suppliers.py
│   │   ├── lanes.py
│   │   ├── planning_policies.py
│   │   ├── warehouse_products.py
│   │   ├── supplier_products.py
│   │   ├── inventory.py     # inventory_snapshots_weekly
│   │   ├── receipts.py
│   │   ├── demand.py
│   │   ├── plan_run.py      # Plan run CRUD, demand-inputs, overrides, freeze, explain, recalculate-demand
│   │   ├── projections.py   # Projection API
│   │   ├── timeline.py      # GET /api/timeline (segments + markers)
│   │   ├── ingestion.py     # Upload (demand, product_master), execute, list ingestion runs
│   │   ├── forecast.py      # Baseline forecast runs, GET baseline
│   │   ├── backbone_imports.py
│   │   ├── backbone_reports.py
│   │   ├── imports_router.py
│   │   ├── exports.py       # CSV exports (projected inventory, planned orders)
│   │   └── templates.py    # Downloadable CSV templates (sku_code_map, demand-weekly, product-master, etc.)
│   └── services/
│       ├── planning.py     # Plan run engine; consumes plan_run_demand_inputs_weekly
│       ├── demand_resolver.py  # resolve_demand_for_run → plan_run_demand_inputs_weekly
│       ├── import_product_master.py  # Product Master CSV → products, suppliers, supplier_products, product_master_attributes (idempotent upsert)
│       ├── time_bucketing.py   # W-TUE week_start_for_date, COMPANY_TIMEZONE
│       ├── weekly_series_builder.py  # Stage → demand_facts_weekly transform
│       ├── forecasting/
│       │   └── baseline.py  # seasonal_naive_52 baseline model
│       ├── projection_service.py
│       ├── backbone_import.py
│       └── csv_import.py
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── 002_planning_correctness.py
│       ├── 003_backbone_schema.py
│       ├── 004_ingestion_forecast_backbone.py  # ingestion_*, demand_stage/facts_weekly, baseline_forecasts_weekly
│       ├── 005_plan_run_demand_overrides_freeze.py  # plan_runs cols, demand inputs, overrides, freeze events, planned_orders.is_frozen
│       ├── 006_demand_breakdown_freeze_anchor_metrics_idempotency.py  # demand_breakdown_json, plan_start_week_start, forecast_run_metrics, duplicate_noop
│       ├── 007_product_master_schema.py  # products extended, product_master_attributes, product_master_stage, entity product_master
│       └── 008_products_aah_code_index.py  # non-unique index on products.aah_code (reference only)
├── tests/
│   ├── test_calendar_weeks.py
│   ├── test_projection_service.py
│   ├── test_time_bucketing.py
│   └── test_baseline_forecast.py
├── alembic.ini
├── requirements.txt
├── .env.example
└── pyrightconfig.json
```

### Frontend (`frontend/src/`)

```
frontend/src/
├── main.ts
├── App.vue
├── env.d.ts
├── api/
│   └── client.ts            # Axios instance, all TS interfaces (PlanRun, ProjectedInventory, etc.)
├── assets/
│   └── global-layout.css    # CSS variables + Tailwind import
├── router/
│   └── index.ts             # All routes (Dashboard, Stock/Inventory Projection, Planning Grid, Admin, etc.)
├── stores/
│   ├── admin.ts             # Products, warehouses, suppliers, lanes, policies, CRUD
│   ├── layout.ts            # Nav collapse, right panel
│   └── planning.ts          # Plan runs (runPlan with demand_source/freeze_weeks), freeze, recalculateDemand, fetchExplain, projected inventory, planned orders
├── composables/
│   └── useDebounce.ts
├── components/
│   ├── layout/
│   │   ├── AppShell.vue
│   │   ├── LeftNav.vue
│   │   ├── MainColumn.vue
│   │   ├── TopBar.vue
│   │   └── RightPanel.vue
│   ├── console/             # Shared list/detail UI
│   │   ├── PageHeader.vue
│   │   ├── FilterBar.vue
│   │   ├── DataTable.vue
│   │   └── DrawerForm.vue
│   ├── SkuTimeline.vue
│   └── TimelineBar.vue      # CSS Grid + SVG timeline (lead time, markers)
└── views/
    ├── DashboardView.vue    # Run scenario (demand source, freeze weeks), plan run actions (freeze, recalculate), selectable plan runs table
    ├── StockProjectionView.vue
    ├── InventoryProjectionView.vue
    ├── WeeklyPlanningGridView.vue
    ├── SkuDetailView.vue
    ├── PlannedOrdersView.vue
    ├── ExceptionsView.vue
    ├── AdminView.vue        # Tab shell for Admin
    ├── admin/
    │   ├── AdminProductsTab.vue
    │   ├── AdminProductDetailView.vue
    │   ├── AdminWarehousesTab.vue
    │   ├── AdminWarehouseDetailView.vue
    │   ├── AdminSuppliersTab.vue
    │   ├── AdminSupplierDetailView.vue
    │   ├── AdminLanesTab.vue
    │   ├── AdminLaneDetailView.vue
    │   ├── AdminPoliciesTab.vue
    │   ├── AdminPolicyDetailView.vue
    │   ├── AdminTimelinesView.vue
    │   └── (detail views for each entity)
    ├── ImportsView.vue      # Ingestion pipeline: upload, list runs, execute, rejections drawer
    ├── ReportsView.vue
    └── ExportsView.vue
```

### Docs (`docs/`)

```
docs/
├── FORECASTING_PLATFORM_SPEC.md
├── INGESTION_CONTRACT.md        # Ingestion pipeline, W-TUE bucketing, CSV schemas, SKU mapping
├── POSTGRES_SETUP.md
├── TYPING_STANDARDS.md
└── CURRENT_BUILD_AND_SCHEMA.md  # this file
```

---

## 4. Screenshots: Admin, Forecast & Reports

Screenshots are not generated by the repo. Add your own captures and place them under `docs/screenshots/` (create the folder if needed), then reference them below.

### Suggested filenames and content

| Screenshot file | Screen | What to capture |
|-----------------|--------|------------------|
| **Admin – Products** | `/admin/products` | PageHeader “Products”, FilterBar (search + Active filter), DataTable (SKU, Name, Description, Active), Add/Export buttons, optional DrawerForm open. |
| **Admin – Warehouses** | `/admin/warehouses` | Same pattern: list + filter + table + actions. |
| **Admin – Planning Policies** | `/admin/policies` | Table of SKU × Warehouse policies (mode, target weeks, safety, forecast window, include samples). |
| **Admin – Timelines** | `/admin/timelines` | SKU + Warehouse + Plan run selected; TimelineBar (lead-time segments + markers) and Receipts table. |
| **Forecast – Inventory Projection** | `/inventory-projection` | FilterBar (Plan run 1/2, SKU, Warehouse, Stockout only), two projected-inventory tables (Scenario 1 & 2), optional chart. |
| **Forecast – Planned Orders** | `/planned-orders` | Plan run selector, FilterBar, table of planned orders (week, SKU, warehouse, order qty), Export CSV. |
| **Forecast – Weekly Planning Grid** | `/planning-grid` | Main planning grid view (if different from Inventory Projection). |
| **Reports** | `/reports` | Reports screen: any filters and main content (table or cards). |

### How to add screenshots to this doc

1. Create `docs/screenshots/` and add the image files (e.g. `admin-products.png`, `inventory-projection.png`).
2. In this section, reference them with relative links, for example:

```markdown
### Admin – Products
![Admin Products](screenshots/admin-products.png)

### Admin – Timelines
![Admin Timelines](screenshots/admin-timelines.png)

### Forecast – Inventory Projection
![Inventory Projection](screenshots/inventory-projection.png)

### Forecast – Planned Orders
![Planned Orders](screenshots/planned-orders.png)

### Reports
![Reports](screenshots/reports.png)
```

3. Optionally add one sentence under each image describing what the screen does (e.g. “Products list with search, active filter, and Add product drawer.”).

---

## 5. Demand backbone and plan run behaviour

- **Demand source (per plan run):** `actuals` (default), `baseline`, or `blended`. Resolved by `demand_resolver.resolve_demand_for_run` into `plan_run_demand_inputs_weekly`; planning engine reads only from that table (lazy init if empty).
- **Overrides:** `demand_overrides_weekly` and `planned_order_overrides_weekly` win over computed values; applied when resolving demand and when generating planned orders.
- **Freeze:** First N weeks (default 4) can be frozen via `POST .../freeze`; `plan_run_freeze_events` records each freeze. Frozen demand/order rows are preserved on recalculate; `POST .../unfreeze` clears freeze for a range (admin).
- **Explain:** `GET .../explain?sku=&warehouse_code=&week_start=` returns demand source chain, override info, freeze state, policy params, and why_order_qty summary.
- **APIs:** Plan run create/update accept `demand_source`, `freeze_weeks`; endpoints for demand-inputs, demand-overrides, order-overrides, freeze, unfreeze, recalculate-demand, explain. All backward compatible; existing responses unchanged.

---

*Last updated to reflect: demand backbone (plan_run extensions, demand inputs, overrides, freeze, explain), ingestion pipeline and baseline forecasts, W-TUE canonical weekly series, and Dashboard/Imports UI for plan run actions and ingestion runs.*
