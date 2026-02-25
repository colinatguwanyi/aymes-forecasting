# SOH Reports API

Stock On Hand (SOH) reports from `inventory_snapshots_weekly`. All endpoints require authentication.

## Endpoints

### GET /api/v1/reports/stock-on-hand/series

Single-SKU time series. **Requires** warehouse and SKU.

| Param | Required | Description |
|-------|----------|-------------|
| warehouse_code | yes | Warehouse (e.g. AAH) |
| sku | yes | Product SKU |
| week_start_from | no | YYYY-MM-DD (inclusive) |
| week_start_to | no | YYYY-MM-DD (inclusive) |

**Response:** `[{ week_start, on_hand_units, on_order_units }, ...]` ordered by week_start ascending.

---

### GET /api/v1/reports/stock-on-hand/summary

Top SKUs by latest on-hand and biggest week-over-week deltas.

| Param | Required | Description |
|-------|----------|-------------|
| warehouse_code | yes | Warehouse |
| week_start_from | no | YYYY-MM-DD |
| week_start_to | no | YYYY-MM-DD |
| limit | no | Default 50, max 200 |

**Response:** `{ top_by_latest: [...], top_by_delta: [...] }`

---

### GET /api/v1/reports/stock-on-hand/grid

All-products SOH history grid. Rows = products, columns = week_starts, values = on_hand_qty. Paginated.

| Param | Required | Description |
|-------|----------|-------------|
| warehouse_code | yes | Warehouse (e.g. AAH) |
| weeks | no | Number of weeks (default 12, max 26) |
| anchor_week_start | no | YYYY-MM-DD; if omitted, uses MAX(week_start) for warehouse |
| q | no | Search SKU or name (partial, case-insensitive) |
| limit | no | Rows per page (default 50, max 200) |
| offset | no | Pagination offset (default 0) |
| active_only | no | Only active products (default true) |

**Response:**
```json
{
  "warehouse_code": "AAH",
  "anchor_week_start": "2025-02-18",
  "week_starts": ["2025-02-18", "2025-02-11", "2025-02-04", ...],
  "total_products": 1234,
  "rows": [
    { "sku": "AC1.5-BA", "name": "Actagain 1.5 Complete Banana", "values": [1316, 1290, 1402, ...] }
  ]
}
```

- **week_starts:** Ordered most-recent first (anchor, anchor-7, anchor-14, …).
- **values:** Aligned with week_starts; missing weeks → 0.
- **Edge case:** If no data in weekly for that warehouse, returns `week_starts=[]`, `rows=[]`, `total_products=0`.
