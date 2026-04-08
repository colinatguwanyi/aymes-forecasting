# Imports Page — Current Implementation Inventory

**Purpose:** Audit of existing imports page components, routes, endpoints, and widgets before warehouse-first refactor.

---

## 1. Routes & Components

| Route | Component | Notes |
|-------|-----------|-------|
| `/imports` | `ImportsView.vue` | Single monolithic view (~650 lines) |
| `/admin/warehouse-product-codes` | `AdminWarehouseProductCodesTab.vue` | BLP code mapping (linked from Imports) |
| `/admin/import-formats` | `AdminImportFormatsTab.vue` | Admin reference for file formats |

---

## 2. Current Import Widgets/Sections on `/imports`

| Section | Widget Type | Purpose |
|---------|-------------|---------|
| **Core imports (2x2 grid)** | 4 cards | Backbone stock positions, inbound orders, demand weekly; product master (legacy) |
| **Ingestion pipeline** | Entity dropdown + file + weekly/historical | Generic demand, product_master, forecast_output, sales_out, stock_on_hand |
| **Sales Out** | Dedicated section | AAH Sales Out CSV/XLSX → demand_actuals (W-TUE) |
| **Stock On Hand (SOH)** | Dedicated section | AAH or BLP format; warehouse selector; weekly/historical |
| **Templates** | Collapsible list | Links to `/api/templates/*` |
| **Ingestion runs table** | DataTable | List runs, Details drawer, Execute pending |

---

## 3. Endpoints Used by Imports Page

### 3.1 Legacy imports (imports_router)

| Endpoint | Method | Used by | Purpose |
|----------|--------|---------|---------|
| `/api/import/inventory-snapshots` | POST | Core import cards | Dry run + confirm CSV |
| `/api/import/receipts` | POST | Core import cards | Dry run + confirm CSV |
| `/api/import/demand-actuals` | POST | Core import cards | Dry run + confirm CSV |
| `/api/import/samples-withdrawals` | POST | Core import cards | Dry run + confirm CSV |
| `/api/import/products` | POST | Core import cards | Dry run + confirm CSV |

### 3.2 Backbone imports

| Endpoint | Method | Used by | Purpose |
|----------|--------|---------|---------|
| `/api/backbone/import/stock-positions` | POST | Core import cards | Direct CSV import |
| `/api/backbone/import/inbound-orders` | POST | Core import cards | Direct CSV import |
| `/api/backbone/import/demand-weekly` | POST | Core import cards | Direct CSV import |

### 3.3 Ingestion pipeline (staging + execute)

| Endpoint | Method | Used by | Purpose |
|----------|--------|---------|---------|
| `/api/ingestion/upload` | POST | Ingestion pipeline | Entity: demand, product_master, forecast_output, sales_out, stock_on_hand |
| `/api/ingestion/sales-out/upload` | POST | Sales Out section | Sales Out upload (mode, date_from, date_to) |
| `/api/ingestion/stock-on-hand/upload` | POST | SOH section | SOH upload (mode, warehouse_code, snapshot_date) |
| `/api/ingestion/forecast-output/upload` | POST | Ingestion pipeline | Forecast output |

### 3.4 Execute / transform

| Endpoint | Method | Used by | Purpose |
|----------|--------|---------|---------|
| `/api/ingestion/runs/{run_id}/execute` | POST | Ingestion pipeline | demand → build_weekly; product_master; forecast_output |
| `/api/ingestion/sales-out/{run_id}/build-weekly` | POST | Sales Out, pipeline | Staged Sales Out → demand_actuals |
| `/api/ingestion/stock-on-hand/{run_id}/execute` | POST | SOH section | Stage → daily → weekly canonical |
| `/api/ingestion/runs/{run_id}/confirm` | POST | All | Confirm historical backfill |

### 3.5 List / detail

| Endpoint | Method | Used by | Purpose |
|----------|--------|---------|---------|
| `/api/ingestion/runs` | GET | Ingestion runs table | List runs (params: status, entity, limit) |
| `/api/ingestion/runs/{run_id}` | GET | Run drawer | Run detail + rejections sample |

### 3.6 Templates

| Endpoint | Method | Used by | Purpose |
|----------|--------|---------|---------|
| `/api/templates/stock-on-hand` | GET | SOH section | Download SOH template |
| `/api/templates/inventory-snapshots` | GET | Templates list | — |
| `/api/templates/receipts` | GET | Templates list | — |
| `/api/templates/demand-actuals` | GET | Templates list | — |
| `/api/templates/samples-withdrawals` | GET | Templates list | — |
| `/api/templates/products` | GET | Templates list | — |
| `/api/templates/sku-code-map` | GET | Templates list | — |
| `/api/templates/demand-weekly` | GET | Templates list | — |
| `/api/templates/demand-daily` | GET | Templates list | — |
| `/api/templates/product-master` | GET | Templates list | — |

### 3.7 Admin / warehouses

| Endpoint | Method | Used by | Purpose |
|----------|--------|---------|---------|
| `/api/warehouses` | GET | SOH warehouse dropdown | Active warehouses for selector |

---

## 4. Entity → Warehouse Mapping (Current)

| Entity | Target warehouse | Notes |
|--------|------------------|-------|
| `sales_out` | AAH (fixed) | AAH_Product_Code → demand_actuals for AAH |
| `stock_on_hand` | AAH or BLP | AAH format → AAH; BLP-AYMES → warehouse_code param |
| `demand` | Any (from CSV) | warehouse_code in each row |
| `product_master` | N/A | Shared products |
| `forecast_output` | AAH | AAH_Product_Code |

---

## 5. IngestionRun Model — No warehouse_code

`IngestionRun` has: id, entity, file_name, status, row_count, inserted_count, rejected_count, mode, date_min, date_max, progress_meta, etc. **No warehouse_code column.**

Warehouse is inferred:
- **sales_out**: always AAH
- **stock_on_hand**: AAH format → AAH; BLP format → from upload param (stored in progress_meta for BLP)
- **demand**: from demand_stage_weekly rows

---

## 6. Historical Backfill Support

| Entity | Historical supported | Notes |
|--------|----------------------|-------|
| sales_out | Yes | date_from, date_to; requires_confirm |
| stock_on_hand | Yes | AAH and BLP; date span from Stock at column |
| demand | Yes | date span from week_start |

**BLP SOH historical:** Supported in backend (same flow as AAH). "BLP SOH history not loaded yet" in UX spec = show disabled state when BLP has no SOH data yet (readiness), not that backend rejects it.

---

## 7. Import Format Config (importFormats.ts)

| id | Title | Warehouse |
|----|-------|-----------|
| soh-standard | SOH Standard (AAH) | AAH |
| soh-blp | SOH BLP-AYMES | BLP |
| sales-out | Sales Out | AAH |
| product-master | Product Master | Shared |
| demand-weekly | Demand weekly | Any |
| forecast-output | Forecast Output | AAH |
| backbone-* | Backbone formats | Any (warehouse in CSV) |

---

## 8. Gaps for Refactor

1. **No GET /api/ingestion/runs/latest?entity=...&warehouse_code=...** — Need to add for "Last run" per card. Can filter existing `/api/ingestion/runs` by entity and infer warehouse from progress_meta/entity (sales_out=AAH, stock_on_hand=from progress_meta or new column).
2. **IngestionRun.warehouse_code** — Not present. For "latest by entity+warehouse" we can: (a) add column (migration), or (b) infer from entity + progress_meta (sales_out→AAH, stock_on_hand BLP→progress_meta.warehouse_code).
3. **Demand (pipeline)** for AAH — Generic demand CSV; user selects warehouse in CSV. For "Demand (pipeline)" card we'd pass warehouse context for display only.
4. **BLP Sales (direct) / Samples** — Use same demand entity with warehouse_code=BLP, demand_type=CUSTOMER or SAMPLES. Same endpoint: `/api/ingestion/upload` with entity=demand.
