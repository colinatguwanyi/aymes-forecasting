# Imports UI — Warehouse-First Design

**Route:** `/imports`

**Query params:** `?warehouse=AAH` or `?warehouse=BLP` (persisted in localStorage)

---

## 1. Top-Level Selectors

1. **Warehouse:** AAH | BLP
   - Persisted in query string and localStorage
   - Drives which data types are shown

2. **Data type:** Dropdown of import types for the selected warehouse

---

## 2. AAH Weekly Flow

| Data type | Format | Endpoint | Notes |
|-----------|--------|----------|-------|
| **Sales Out** | AAH Sales Out (CSV/XLSX) | POST /ingestion/sales-out/upload | AAH_Product_Code, Business_Processed_Date, Invoiced_Qty. Stage → Execute build-weekly → demand_actuals (AAH, W-TUE) |
| **Stock on Hand (SOH)** | AAH SOH (CSV/XLSX) | POST /ingestion/stock-on-hand/upload | Stock at, AAH Code, STOCK, ON ORDER. Stage → Execute → inventory_snapshots_daily → inventory_snapshots_weekly |
| **Demand (pipeline)** | Demand weekly (CSV) | POST /ingestion/upload (entity=demand) | week_start, sku, warehouse_code, demand_type, qty. Use warehouse_code=AAH in CSV |
| **Product Master** | Product Master (CSV) | POST /ingestion/upload (entity=product_master) | SKU code, Description. Shared across warehouses |

**Historical backfill:** Supported for Sales Out, SOH, Demand. Use "Upload historical backfill" and set date range.

---

## 3. BLP Weekly Flow

| Data type | Format | Endpoint | Notes |
|-----------|--------|----------|-------|
| **Sales (direct)** | Demand weekly (CSV) | POST /ingestion/upload (entity=demand) | week_start, sku, warehouse_code=BLP, demand_type=CUSTOMER |
| **Samples** | Demand weekly (CSV) | POST /ingestion/upload (entity=demand) | week_start, sku, warehouse_code=BLP, demand_type=SAMPLES |
| **Stock on Hand (SOH)** | BLP SOH (CSV/XLSX) | POST /ingestion/stock-on-hand/upload | Code, Balance. Select Warehouse=BLP. Requires Warehouse Product Codes mapping first |
| **Product Master** | Product Master (CSV) | POST /ingestion/upload (entity=product_master) | Shared |
| **Warehouse Product Codes** | — | Link to Admin | Map BLP external codes to canonical SKU before BLP SOH import |

**BLP SOH historical:** Disabled with message "BLP SOH history not loaded yet" until BLP SOH is set up.

---

## 4. Per-Card Display

Each import card shows:

- **Format name** (e.g. AAH SOH, BLP SOH)
- **Required columns** (short list)
- **Target warehouse** (from selection)
- **Last run** summary: status, inserted/rejected counts, date
- **Upload** and **Template** (or link) actions
- **Weekly** vs **Historical** (when supported)

---

## 5. Endpoints

| Endpoint | Purpose |
|----------|---------|
| GET /api/ingestion/runs/latest?entity=&warehouse_code= | Latest run for entity+warehouse (for "Last run" panel) |
| GET /api/ingestion/runs | List all runs |
| POST /api/ingestion/sales-out/upload | Sales Out upload |
| POST /api/ingestion/stock-on-hand/upload | SOH upload |
| POST /api/ingestion/upload | Demand, product_master |
| POST /api/ingestion/sales-out/{run_id}/build-weekly | Execute Sales Out |
| POST /api/ingestion/stock-on-hand/{run_id}/execute | Execute SOH |
| POST /api/ingestion/runs/{run_id}/execute | Execute demand/product_master |
| POST /api/ingestion/runs/{run_id}/confirm | Confirm historical backfill |

---

## 6. Config Source

`frontend/src/config/importCards.ts` — single source of truth for warehouse → import cards.
