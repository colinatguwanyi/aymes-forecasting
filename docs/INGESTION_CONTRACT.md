# Ingestion Contract

This document describes the ingestion pipeline, weekly time bucketing, CSV schemas, idempotency, SKU mapping, and completeness rules.

**Related docs:** [INGESTION.md](INGESTION.md) — full ingestion pipeline guide; [IMPORT_FILE_FORMATS.md](IMPORT_FILE_FORMATS.md) — column requirements per format.

## Week bucketing rule

- **Company timezone:** `Europe/London`
- **Week start day:** **Tuesday** (W-TUE)
- Weeks run Tuesday (inclusive) to Monday (inclusive).
- All weekly tables store `week_start` as a **date** (the Tuesday that starts the week).
- The function `week_start_for_date(d)` returns the W-TUE week start for any calendar date `d` (treated as London-local).

Implementation: `backend/app/services/time_bucketing.py` (`COMPANY_TIMEZONE`, `WEEK_START_DAY`, `week_start_for_date()`).

## CSV schemas (templates)

Templates are available under `/api/templates/`:

| Template | Columns |
|----------|---------|
| **sku-code-map** | old_sku, new_sku, effective_from_week_start, effective_to_week_start, notes |
| **demand-weekly** | week_start (YYYY-MM-DD, any date → normalized to W-TUE), sku, warehouse_code, demand_type (CUSTOMER \| SAMPLES \| ADJUSTMENT), qty |
| **demand-daily** | event_date, sku, warehouse_code, demand_type, qty, source |
| **receipts** | week_start, sku, warehouse_code, qty, source_type |
| **inventory-snapshots** | week_start, sku, warehouse_code, on_hand_qty |

## Idempotency rules

- **Upload (duplicate detection):** Before creating a new run, the API checks for an existing run with the same **entity** and **file_sha256** and **status = success**. If one exists, **no new run is created**; the API returns the existing run’s `run_id` with `"duplicate_noop": true` and a message: *"Same file (entity+sha256) already ingested successfully; returning existing run_id."* This makes re-uploading the same file deterministic and avoids duplicate work when the same file is uploaded again.
- **Upload (first time):** If no successful run matches entity+file_sha256, a new run is created (status PENDING), rows are staged, and the new `run_id` is returned.
- **Execute:** Running execute on the same `run_id` multiple times is **idempotent** for the canonical table: stage → demand_facts_weekly uses UPSERT (same key updates qty and source_run_id). Rejections and run metrics are updated each time.

## Product Master: canonical SKU and AAH code (non-negotiable)

- **Canonical SKU:** `products.sku` = TRIM(row["SKU code"]). Case is preserved exactly. Rows with blank SKU code after trim are rejected. SKU code is the only key for products in planning (planning_policies.sku, projected_inventory.sku, planned_orders.sku). Never use AAH code as a join key.
- **AAH code:** `products.aah_code` is a reference field only (nullable). It is set to **NULL** if the value is blank or equals (case-insensitive) any of: `NA`, `N/A`, `-`, `null`. There is **no** unique constraint on `aah_code`; duplicate AAH codes across different SKUs are allowed. AAH code must never be used for joins in any service.
- **Data lifecycle:** If SKU codes change in future, handle via `sku_code_map` (old_sku → new_sku), not by editing history or rekeying existing rows.

## SKU mapping

- Table: `sku_code_map` (old_sku, new_sku, effective_from_week_start, effective_to_week_start, notes).
- When building the weekly series, for each staged row we resolve **old_sku** (from CSV, stored as `sku_raw`) to **new_sku** using `sku_code_map`: any row where `old_sku` matches and `week_start` falls within `[effective_from_week_start, effective_to_week_start]` (nulls mean unbounded) maps to `new_sku`. If no mapping exists, we use the raw SKU as-is.
- Mapping is applied **before** filtering by active products and before aggregation.

## Completeness / minimum history

- **MIN_WEEKS_HISTORY** (default 60) is enforced per (sku, warehouse_code, demand_type).
- After aggregating staged rows by (week_start, sku, warehouse_code, demand_type), we count distinct weeks per (sku, warehouse_code, demand_type). If the count is **less than** MIN_WEEKS_HISTORY, that series is **not** written to `demand_facts_weekly`; all keys for that series are dropped and a rejection reason is recorded (e.g. "Insufficient history: 30 weeks < 60").
- Series that pass the check get **missing weeks filled**: for every week_start between min and max observed for that (sku, warehouse_code, demand_type), we insert or update a row with qty=0 and `is_imputed=true` when that week was not in the staged data.

## Rejections and audit

- Every bad or skipped row is recorded in `ingestion_rejections` with: ingestion_run_id, row_number, raw_payload (JSONB), reason.
- Runs are auditable: who (created_by), when (started_at, finished_at), what file (file_name, file_sha256), and metrics (row_count, inserted_count, updated_count, rejected_count, error_summary).

## API (non-breaking)

- **POST /api/ingestion/upload** — multipart CSV + entity; parse and stage; create run; return run_id.
- **POST /api/ingestion/runs/{run_id}/execute** — run stage → demand_facts_weekly transform (synchronous).
- **GET /api/ingestion/runs** — list runs with status and metrics.
- **GET /api/ingestion/runs/{run_id}** — run details and rejections sample.

No existing planning or demand routes are changed; new tables and routes are additive.
