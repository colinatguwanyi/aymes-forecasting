# Imports UI — Location-First Design

**Route:** `/imports`

**Query params:** `?warehouse=<location_code>` (persisted in localStorage)

---

## 1. Top-Level Selectors

1. **Data location:** active locations from Admin → Warehouses
   - Persisted in query string and localStorage
   - Drives the location code passed to Sales Out and SOH uploads
   - If no active locations exist, location-specific imports are unavailable

2. **Data type:** Import cards for Product Master plus location-specific Sales Out, SOH and Demand

---

## 2. Weekly Import Flow

| Data type | Format | Endpoint | Notes |
|-----------|--------|----------|-------|
| **Sales Out** | Sales Out (CSV/XLSX) | POST /ingestion/sales-out/upload | AAH_Product_Code, Business_Processed_Date, Invoiced_Qty. Stage → Execute build-weekly → demand_actuals for selected location |
| **Stock on Hand (SOH)** | SOH (CSV/XLSX) | POST /ingestion/stock-on-hand/upload | Stock at/snapshot date, product code, stock quantity. Stage → Execute → inventory_snapshots_daily → inventory_snapshots_weekly for selected location |
| **Demand (pipeline)** | Demand weekly (CSV) | POST /ingestion/upload (entity=demand) | week_start, sku, warehouse_code, demand_type, qty. Selected location is sent with the upload |
| **Product Master** | Product Master (CSV) | POST /ingestion/upload (entity=product_master) | SKU code, Description. Shared across locations |

**Historical backfill:** Supported for Sales Out, SOH, Demand. Use "Upload historical backfill" and set date range.

---

## 3. Location Flow

All active Admin locations can be selected. The UI no longer provides built-in AAH/BLP options. Location-specific uploads use the selected location code.

---

## 4. Per-Card Display

Each import card shows:

- **Format name**
- **Required columns** (short list)
- **Target location** (from selection)
- **Last run** summary: status, inserted/rejected counts, date
- **Upload** and **Template** (or link) actions
- **Weekly** vs **Historical** (when supported)

---

## 5. Endpoints

| Endpoint | Purpose |
|----------|---------|
| GET /api/ingestion/runs/latest?entity=&warehouse_code= | Latest run for entity+location (for "Last run" panel) |
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

`frontend/src/config/importCards.ts` — creates import cards for the selected Admin location.
