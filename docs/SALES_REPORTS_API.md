# Sales Reports API

Sales reports from `demand_facts_weekly` (CUSTOMER = Sales Out). All endpoints require authentication.

## Endpoints

### GET /api/v1/reports/sales/grid

All-products weekly sales grid. Rows = products, columns = week_starts, values = qty. Paginated.

| Param | Required | Description |
|-------|----------|-------------|
| warehouse_code | yes | Warehouse (e.g. AAH) |
| weeks | no | Number of weeks (default 12, max 26) |
| anchor_week_start | no | YYYY-MM-DD; if omitted, uses MAX(week_start) for warehouse + demand_type |
| q | no | Search SKU or name (partial, case-insensitive) |
| limit | no | Rows per page (default 50, max 200) |
| offset | no | Pagination offset (default 0) |
| active_only | no | Only active products (default true) |
| demand_type | no | CUSTOMER (default), SAMPLES, or ADJUSTMENT |

**Response:**
```json
{
  "warehouse_code": "AAH",
  "anchor_week_start": "2025-02-18",
  "week_starts": ["2025-02-18", "2025-02-11", "2025-02-04", ...],
  "total_products": 1234,
  "rows": [
    {
      "sku": "AC1.5-BA",
      "name": "Actagain 1.5 Complete Banana",
      "values": [1316, 1290, 1402, ...],
      "latest": 1316,
      "total": 5028
    }
  ]
}
```

- **week_starts:** Ordered most-recent first (anchor, anchor-7, anchor-14, …).
- **values:** Aligned with week_starts; missing weeks → 0.
- **latest:** Value for the most recent week (values[0]).
- **total:** Sum of values across visible weeks.
- **Edge case:** If no data in demand_facts_weekly for that warehouse + demand_type, returns `week_starts=[]`, `rows=[]`, `total_products=0`.
