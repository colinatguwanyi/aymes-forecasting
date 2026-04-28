# Import File Formats Reference

This document describes the required file format for every import type in the AYMES forecasting application.

**File types:** CSV or XLSX (unless noted). Headers are case-insensitive for most imports.

**Related docs:** [INGESTION.md](INGESTION.md) — full ingestion pipeline guide; [INGESTION_CONTRACT.md](INGESTION_CONTRACT.md) — idempotency, SKU mapping, completeness rules.

---

## 1. Stock On Hand (SOH)

**Entity:** `stock_on_hand`  
**Upload:** Imports page → Stock On Hand (SOH) section

### Format A: Standard format (AAH)

| Column        | Required | Notes                                                                 |
|---------------|----------|----------------------------------------------------------------------|
| Stock at      | Yes      | Date (DD/MM/YYYY or YYYY-MM-DD)                                      |
| AAH Code      | Yes      | Product identifier (maps to products via `products.aah_code`)        |
| STOCK         | Yes      | On-hand quantity (non-negative number)                               |
| ON ORDER      | Yes      | On-order quantity (non-negative number)                               |
| Branch Name   | No       | Read for validation only; not persisted. All rows roll to warehouse AAH. |
| Description   | No       | Optional                                                             |

**Roll-up:** All AAH SOH rows roll up to warehouse `AAH`. Quantities are summed per (product, warehouse, date). Branch column is ignored for storage.

### Format B: BLP-AYMES Report

| Column     | Required | Notes                                                                 |
|------------|----------|----------------------------------------------------------------------|
| Code       | Yes      | Resolved to canonical SKU: 0) Warehouse Product Codes mapping table (Admin → Warehouse Product Codes), 1) products.sku, 2) products.aah_code, 3) HSCODE:(\d+) in Description → product_master_attributes.hs_code |
| Balance    | Yes      | Stock quantity (number)                                              |
| Description| No       | Optional; used for HSCODE regex if Code does not match               |
| Location   | No       | Ignored for stock totals                                             |
| Expiry Date| No       | Optional (DD/MM/YYYY); metadata only, does not affect totals        |

**Required at upload:** Select **Warehouse** from dropdown and optionally set **Snapshot date**. Location and Expiry Date are ignored for aggregation.

**BLP codes:** Map external codes to canonical SKU via Admin → Warehouse Product Codes. The resolver uses the mapping table first for deterministic imports. Unmapped codes are rejected and appear in the Unmapped codes panel for quick mapping creation.

---

## 2. Demand

**Entity:** `demand`  
**Upload:** Imports page → Ingestion pipeline (Entity: Demand)

| Column        | Required | Notes                                                                 |
|---------------|----------|----------------------------------------------------------------------|
| week_start    | Yes      | YYYY-MM-DD (any date → normalized to W-TUE week)                     |
| sku           | Yes      | Product SKU (must exist in products)                                 |
| warehouse_code| Yes      | Warehouse code (must exist in warehouses)                            |
| demand_type   | Yes      | One of: `CUSTOMER`, `SAMPLES`, `ADJUSTMENT`                          |
| qty           | Yes      | Quantity (number)                                                    |

---

## 3. Demand (daily)

**Entity:** `demand` (daily staging)  
**Template:** `/api/templates/demand-daily`

| Column        | Required | Notes                                                                 |
|---------------|----------|----------------------------------------------------------------------|
| event_date    | Yes      | YYYY-MM-DD                                                            |
| sku           | Yes      | Product SKU                                                          |
| warehouse_code| Yes      | Warehouse code                                                       |
| demand_type   | Yes      | `CUSTOMER`, `SAMPLES`, or `ADJUSTMENT`                               |
| qty           | Yes      | Quantity                                                             |
| source        | No       | Optional (e.g. "CSV")                                                 |

---

## 4. Sales Out

**Entity:** `sales_out`  
**Upload:** Imports page → Sales Out section

| Column                      | Required | Notes                                      |
|-----------------------------|----------|--------------------------------------------|
| AAH_Product_Code            | Yes      | Product code (maps to products.aah_code)  |
| Business_Processed_Date     | Yes      | DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, or YYYY-MM-DD |
| Invoiced_Qty                | No       | Decimal                                   |
| Account_Code                | No       |                                            |
| Delivery_Address_Line_1      | No       |                                            |
| Delivery_Address_Postcode    | No       |                                            |
| Customer_Business_Sector_Name| No       |                                            |
| PIP_Code                    | No       |                                            |
| Product_Name                | No       |                                            |
| Item_Size                   | No       |                                            |
| Servings_Qty                | No       |                                            |
| Net_Sales_Value             | No       |                                            |
| Business_Processed_Year     | No       |                                            |
| Print_Branch                | No       |                                            |
| Branch                      | No       |                                            |

**Note:** AAH_Product_Code must exist in `products.aah_code`. Demand is built as CUSTOMER type for warehouse AAH.

---

## 5. Product Master

**Entity:** `product_master`  
**Template:** `/api/templates/product-master`

| Column                      | Required | Notes                                      |
|-----------------------------|----------|--------------------------------------------|
| Supplier                    | No       | Defaults to "DEFAULT" if missing           |
| SKU code                    | Yes      | Canonical product SKU (case preserved)     |
| AAH code                    | No       | Reference only; NULL if blank/NA/N/A/-    |
| Description                 | Yes      |                                            |
| Single Unit Content (g/ml)  | No       | Decimal                                   |
| Selling Unit                | No       |                                            |
| Single/Selling Unit         | No       |                                            |
| Selling/Trade Unit          | No       |                                            |
| Trade Unit                  | No       |                                            |
| Selling Unit/Pallet         | No       |                                            |
| Single Units_MOQ            | No       | Integer                                   |
| Incremental Qty (Single Units)| No    | Integer                                   |
| Supplier Leadtime           | No       | e.g. "8 weeks"                            |
| Shelf Life                  | No       |                                            |
| AYMES Recipe (Y/N)          | No       |                                            |
| Price_Unit                  | No       |                                            |
| COGs_Unit (Content)         | No       |                                            |
| Curr                       | No       |                                            |
| COGs_ Selling Unit          | No       |                                            |
| Product Family              | No       |                                            |
| Pallet weight (Kg)          | No       |                                            |
| Pallet Dimensions (WxDxH)   | No       |                                            |
| HS Code                     | No       |                                            |
| Brand                       | No       |                                            |
| Ti-Hi                       | No       |                                            |

**Note:** SKU code is the canonical key. AAH code is reference only and must never be used for joins.

---

## 6. Forecast Output

**Entity:** `forecast_output`  
**Upload:** Imports page → Ingestion pipeline (Entity: Forecast output)

| Column              | Required | Notes                                      |
|---------------------|----------|--------------------------------------------|
| AAH_Product_Code    | Yes      | Must exist in products.aah_code            |
| Inference_Date      | Yes      | YYYY-MM-DD or DD/MM/YYYY                   |
| Forecast_Week       | Yes      | YYYY-MM-DD or DD/MM/YYYY                   |
| Model               | Yes      | Model name                                 |
| Forecast            | No*      | *At least one of Forecast, Actual, Interpolated_Values required |
| Actual              | No*      |                                            |
| Interpolated_Values | No*      |                                            |
| Product_Name        | No       |                                            |
| Model_Details       | No       |                                            |
| Mean_Absolute_Error | No       |                                            |
| Mean_Absolute_Percentage_Error | No |                            |
| Is_Best_Model       | No       |                                            |
| Outlier             | No       |                                            |
| Predicted_Best_Model_Bool | No |                                    |

---

## 7. Backbone imports (direct CSV)

**Upload:** Imports page → 2x2 card grid (Stock positions / Inbound orders / Demand weekly)

### Stock positions weekly

| Column         | Required | Notes                    |
|----------------|----------|--------------------------|
| warehouse_code | Yes      |                          |
| sku            | Yes      |                          |
| iso_year       | Yes      | Integer (e.g. 2025)      |
| iso_week       | Yes      | Integer 1–53             |
| on_hand_units  | Yes      | Integer                  |

### Inbound orders weekly

| Column         | Required | Notes                    |
|----------------|----------|--------------------------|
| warehouse_code | Yes      |                          |
| sku            | Yes      |                          |
| iso_year       | Yes      | Integer                  |
| iso_week       | Yes      | Integer 1–53             |
| inbound_units  | Yes      | Integer                  |
| supplier_code  | No       | Optional                 |

### Demand weekly

| Column         | Required | Notes                    |
|----------------|----------|--------------------------|
| warehouse_code | Yes      |                          |
| sku            | Yes      |                          |
| iso_year       | Yes      | Integer                  |
| iso_week       | Yes      | Integer 1–53             |
| demand_units   | Yes      | Integer                  |

---

## 8. Legacy templates (available via Templates drawer)

### Inventory snapshots

| Column         | Required |
|----------------|----------|
| week_start     | Yes      |
| sku            | Yes      |
| warehouse_code | Yes      |
| on_hand_qty    | Yes      |

### Receipts

| Column         | Required |
|----------------|----------|
| week_start     | Yes      |
| sku            | Yes      |
| warehouse_code | Yes      |
| qty            | Yes      |
| source_type    | Yes      |

### Samples withdrawals

| Column         | Required |
|----------------|----------|
| week_start     | Yes      |
| sku            | Yes      |
| warehouse_code | Yes      |
| qty            | Yes      |

### Products (simple)

| Column      | Required |
|-------------|----------|
| sku         | Yes      |
| name        | No       |
| description | No       |

### SKU code map

| Column                    | Required |
|---------------------------|----------|
| old_sku                   | Yes      |
| new_sku                   | Yes      |
| effective_from_week_start | No       |
| effective_to_week_start   | No       |
| notes                     | No       |

---

## Week bucketing

- **Company timezone:** Europe/London  
- **Week start day:** Tuesday (W-TUE)  
- Weekly tables store `week_start` as the Tuesday that starts the week.  
- Any date in a week maps to that week's Tuesday.

---

## Templates

Download templates from the Imports page (Templates link) or:

- `/api/templates/stock-on-hand` – SOH standard format
- `/api/templates/demand-weekly` – Demand weekly
- `/api/templates/demand-daily` – Demand daily
- `/api/templates/product-master` – Product master (full)
- `/api/templates/inventory-snapshots` – Inventory snapshots
- `/api/templates/receipts` – Receipts
- `/api/templates/samples-withdrawals` – Samples withdrawals
- `/api/templates/products` – Simple products
- `/api/templates/sku-code-map` – SKU code map

---

## Warehouse Product Codes (bulk mapping)

**Location:** Admin → Warehouse Product Codes → Bulk upload CSV

Used to map external product codes (e.g. BLP Code) to canonical `products.sku` per warehouse. The SOH BLP resolver uses this mapping first for deterministic imports.

| Column        | Required | Notes                                      |
|---------------|----------|--------------------------------------------|
| external_code | Yes      | External code from source (e.g. BLP Code) |
| sku           | Yes      | Canonical product SKU (must exist)        |
| external_name | No       | Raw description for reference             |
| hs_code       | No       | HS code if known                          |

**Note:** Set the warehouse at upload time (dropdown). All rows in the CSV apply to that warehouse.
