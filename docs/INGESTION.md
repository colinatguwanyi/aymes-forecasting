# Ingestion Pipeline Guide

This document describes the full ingestion pipeline in the AYMES forecasting application: entities, flow, API endpoints, and operational details.

**Related docs:** [IMPORT_FILE_FORMATS.md](IMPORT_FILE_FORMATS.md) — column requirements per format; [INGESTION_CONTRACT.md](INGESTION_CONTRACT.md) — idempotency, SKU mapping, completeness rules.

---

## Overview

Ingestion follows a **stage → execute** pattern:

1. **Upload:** User uploads a file (CSV or XLSX). The API parses it, validates rows, and writes valid rows to a **stage** table. Invalid rows go to `ingestion_rejections`.
2. **Execute:** User confirms (if required) and runs execute. The stage data is transformed into **canonical** tables (e.g. `demand_facts_weekly`, `inventory_snapshots_daily`).

Each upload creates an `IngestionRun` record. Runs are auditable (who, when, file hash, metrics).

### Import progress (platform standard)

Long jobs update `ingestion_runs.progress_meta` with **v1** fields (see `backend/app/ingestion_progress.py`) so the Imports page can poll `GET /api/ingestion/runs/{run_id}` while **Execute** runs in parallel:

| Field | Meaning |
|-------|---------|
| `import_version` | `1` |
| `import_phase` | Short id (e.g. `soh_daily`, `sales_out_write`, `demand_transform`) |
| `import_message` | Primary line for the UI |
| `import_detail` | Optional secondary line |
| `import_percent` | 0–100 when known; omitted for indeterminate |

Older keys (`daily_batches_done`, `batches_done`, BLP coverage, etc.) are still mapped to human-readable lines in `frontend/src/config/importProgressSpec.ts`. The Imports UI shows upload byte progress separately, then server transform progress when polling returns data.

---

## Entities and Flows

| Entity          | Stage table(s)              | Canonical output                          | Upload location                    |
|-----------------|-----------------------------|-------------------------------------------|------------------------------------|
| demand          | demand_stage_weekly         | demand_facts_weekly                       | Imports → Entity: Demand           |
| product_master  | product_master_stage        | products, product_master_attributes       | Imports → Entity: Product Master   |
| forecast_output | forecast_run_output_stage   | forecast_baseline, forecast_published     | Imports → Entity: Forecast output  |
| sales_out       | sales_out_stage             | demand_facts_weekly (CUSTOMER, AAH)       | Imports → Sales Out section        |
| stock_on_hand   | stock_on_hand_stage         | inventory_snapshots_daily → weekly        | Imports → Stock On Hand section    |

### Stock On Hand (SOH)

- **Formats:** AAH (standard) or BLP-AYMES. Format is auto-detected from headers.
- **AAH:** Requires Stock at, AAH Code, STOCK, ON ORDER. All rows roll to warehouse AAH. Branch Name read but not persisted.
- **BLP:** Requires Code, Balance. User must select **Warehouse** at upload. Code is resolved to canonical SKU via:
  1. **Warehouse Product Codes** mapping table (Admin → Warehouse Product Codes)
  2. products.sku
  3. products.aah_code
  4. HSCODE:(\d+) in Description → product_master_attributes.hs_code
- **Execute:** stage → inventory_snapshots_daily → inventory_snapshots_weekly (W-TUE bucketing).

### Demand

- **Formats:** Weekly (week_start, sku, warehouse_code, demand_type, qty) or daily (event_date, …).
- **Execute:** stage → demand_facts_weekly. Uses `sku_code_map` for old_sku → new_sku. Enforces MIN_WEEKS_HISTORY per (sku, warehouse_code, demand_type).

### Product Master

- **Format:** SKU code, Description, AAH code, HS Code, etc. See [IMPORT_FILE_FORMATS.md](IMPORT_FILE_FORMATS.md).
- **Execute:** stage → products, product_master_attributes. AAH code is reference only; never used for joins.

### Sales Out

- **Format:** AAH_Product_Code, Business_Processed_Date, Invoiced_Qty, etc.
- **Execute:** stage → demand_facts_weekly (CUSTOMER type, warehouse AAH). AAH_Product_Code must exist in products.aah_code.

### Forecast Output

- **Format:** AAH_Product_Code, Inference_Date, Forecast_Week, Model, Forecast/Actual/Interpolated_Values.
- **Execute:** stage → forecast_baseline, forecast_published. AAH_Product_Code resolved via products.aah_code.

### Backbone imports

Direct CSV imports (no stage table) for stock positions, inbound orders, demand weekly. Upload via Imports page 2×2 card grid.

---

## Warehouse Product Codes

For BLP and other formats with external product codes, map codes to canonical SKU via **Admin → Warehouse Product Codes**:

- **Add mapping:** warehouse_code + external_code → sku
- **Bulk upload:** CSV with columns external_code, sku, external_name, hs_code. Set warehouse at upload.
- **Unmapped codes:** After a BLP SOH import, view unmapped codes (product_not_found rejections) and create mappings from the panel.

The resolver uses the mapping table **first**, so imports become deterministic once codes are mapped.

---

## BLP SOH Coverage Metrics

For BLP SOH imports, the run's `progress_meta` includes coverage:

| Metric              | Description                          |
|---------------------|--------------------------------------|
| total_unique_codes  | Distinct external codes in file      |
| mapped_codes        | Codes that resolved to a SKU         |
| missing_codes       | Codes that did not resolve           |
| pct_coverage_codes  | mapped / total × 100                 |
| units_total         | Sum of all quantities                |
| units_missing       | Sum of quantities for missing codes  |
| pct_units_missing   | units_missing / units_total × 100    |

Missing codes are rejected and recorded in `ingestion_rejections` with reason `product_not_found`. They appear in the Unmapped codes panel for quick mapping creation.

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ingestion/upload` | POST | Upload CSV for demand, product_master, forecast_output |
| `/api/ingestion/stock-on-hand/upload` | POST | Upload SOH (AAH or BLP). Params: warehouse_code, snapshot_date (BLP) |
| `/api/ingestion/sales-out/upload` | POST | Upload Sales Out |
| `/api/ingestion/forecast-output/upload` | POST | Upload Forecast output |
| `/api/ingestion/runs/{run_id}/execute` | POST | Execute stage → canonical |
| `/api/ingestion/stock-on-hand/{run_id}/execute` | POST | Execute SOH stage → daily → weekly |
| `/api/ingestion/runs/{run_id}/confirm` | POST | Confirm run (when requires_confirm) |
| `/api/ingestion/runs` | GET | List runs (filter by status, entity) |
| `/api/ingestion/runs/{run_id}` | GET | Run details and rejections sample |

### Warehouse Product Codes (Admin)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/admin/warehouse-product-codes` | GET | List mappings (filter: warehouse_code, q, active_only) |
| `/api/admin/warehouse-product-codes` | POST | Create mapping |
| `/api/admin/warehouse-product-codes/{id}` | PUT | Update mapping |
| `/api/admin/warehouse-product-codes/{id}` | DELETE | Soft or hard delete |
| `/api/admin/warehouse-product-codes/bulk` | POST | Bulk upload CSV (query: warehouse_code) |
| `/api/admin/warehouse-product-codes/unmapped` | GET | Unmapped codes from latest SOH run |
| `/api/admin/warehouse-product-codes/unmapped/csv` | GET | Download unmapped codes as CSV |

---

## Idempotency

- **Same file:** If a run with the same entity + file_sha256 has status=success, the API returns that run_id with `duplicate_noop: true` instead of creating a new run.
- **After reset:** Pass `force_reimport=true` (or tick **Re-import same file if it was imported before** in the Imports UI) to create a fresh staged run from the same file after canonical data has been cleared.
- **Re-execute:** Running execute on the same run_id multiple times is idempotent for canonical tables (UPSERT semantics where applicable).

See [INGESTION_CONTRACT.md](INGESTION_CONTRACT.md) for full rules.

---

## Rejections and Audit

- **ingestion_rejections:** Every bad or skipped row is recorded with ingestion_run_id, row_number, raw_payload (JSONB), reason.
- **Run metadata:** file_name, file_sha256, created_by, started_at, finished_at, row_count, inserted_count, updated_count, rejected_count, error_summary.

---

## Week Bucketing

- **Company timezone:** Europe/London
- **Week start:** Tuesday (W-TUE)
- Weekly tables store `week_start` as the Tuesday that starts the week.
- See `backend/app/services/time_bucketing.py`.
