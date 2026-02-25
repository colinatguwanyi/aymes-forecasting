/**
 * Single source of truth for import file formats.
 * Used by Admin Import Formats page. Do not duplicate across files.
 */

export type FieldUsage = 'required' | 'optional' | 'not_used'

export interface ImportFormatDef {
  id: string
  title: string
  acceptedFileTypes: string
  requiredColumns: string[]
  fields: Record<string, FieldUsage>
  notes: string
}

export const IMPORT_FORMATS: ImportFormatDef[] = [
  {
    id: 'soh-standard',
    title: 'SOH Standard (AAH)',
    acceptedFileTypes: 'CSV, XLSX',
    requiredColumns: ['Stock at', 'AAH Code', 'STOCK', 'ON ORDER'],
    fields: {
      'Stock at': 'required',
      'AAH Code': 'required',
      'STOCK': 'required',
      'ON ORDER': 'required',
      'Branch Name': 'optional',
      'Description': 'optional',
    },
    notes: 'Rolls up to warehouse AAH. Branch read but not persisted. Quantities summed per (product, warehouse, date).',
  },
  {
    id: 'soh-blp',
    title: 'SOH BLP-AYMES',
    acceptedFileTypes: 'CSV, XLSX',
    requiredColumns: ['Code', 'Balance'],
    fields: {
      'Code': 'required',
      'Balance': 'required',
      'Description': 'optional',
      'Location': 'optional',
      'Expiry Date': 'optional',
    },
    notes: 'Select Warehouse at upload. Code resolved via Warehouse Product Codes mapping first, then sku, aah_code, HSCODE in Description. Location/Expiry ignored for totals.',
  },
  {
    id: 'demand-weekly',
    title: 'Demand weekly',
    acceptedFileTypes: 'CSV',
    requiredColumns: ['week_start', 'sku', 'warehouse_code', 'demand_type', 'qty'],
    fields: {
      'week_start': 'required',
      'sku': 'required',
      'warehouse_code': 'required',
      'demand_type': 'required',
      'qty': 'required',
    },
    notes: 'demand_type: CUSTOMER, SAMPLES, or ADJUSTMENT. Week bucketing: W-TUE.',
  },
  {
    id: 'demand-daily',
    title: 'Demand daily',
    acceptedFileTypes: 'CSV',
    requiredColumns: ['event_date', 'sku', 'warehouse_code', 'demand_type', 'qty'],
    fields: {
      'event_date': 'required',
      'sku': 'required',
      'warehouse_code': 'required',
      'demand_type': 'required',
      'qty': 'required',
      'source': 'optional',
    },
    notes: 'event_date YYYY-MM-DD.',
  },
  {
    id: 'sales-out',
    title: 'Sales Out',
    acceptedFileTypes: 'CSV, XLSX',
    requiredColumns: ['AAH_Product_Code', 'Business_Processed_Date'],
    fields: {
      'AAH_Product_Code': 'required',
      'Business_Processed_Date': 'required',
      'Invoiced_Qty': 'optional',
      'Account_Code': 'optional',
      'Delivery_Address_Line_1': 'optional',
      'Delivery_Address_Postcode': 'optional',
      'Customer_Business_Sector_Name': 'optional',
      'PIP_Code': 'optional',
      'Product_Name': 'optional',
      'Item_Size': 'optional',
      'Servings_Qty': 'optional',
      'Net_Sales_Value': 'optional',
      'Business_Processed_Year': 'optional',
      'Print_Branch': 'optional',
      'Branch': 'optional',
    },
    notes: 'AAH_Product_Code must exist in products.aah_code. Demand built as CUSTOMER for warehouse AAH.',
  },
  {
    id: 'product-master',
    title: 'Product Master',
    acceptedFileTypes: 'CSV',
    requiredColumns: ['SKU code', 'Description'],
    fields: {
      'Supplier': 'optional',
      'SKU code': 'required',
      'AAH code': 'optional',
      'Description': 'required',
      'Single Unit Content (g/ml)': 'optional',
      'Selling Unit': 'optional',
      'Single/Selling Unit': 'optional',
      'Selling/Trade Unit': 'optional',
      'Trade Unit': 'optional',
      'Selling Unit/Pallet': 'optional',
      'Single Units_MOQ': 'optional',
      'Incremental Qty (Single Units)': 'optional',
      'Supplier Leadtime': 'optional',
      'Shelf Life': 'optional',
      'AYMES Recipe (Y/N)': 'optional',
      'Price_Unit': 'optional',
      'COGs_Unit (Content)': 'optional',
      'Curr': 'optional',
      'COGs_ Selling Unit': 'optional',
      'Product Family': 'optional',
      'Pallet weight (Kg)': 'optional',
      'Pallet Dimensions (WxDxH)': 'optional',
      'HS Code': 'optional',
      'Brand': 'optional',
      'Ti-Hi': 'optional',
    },
    notes: 'SKU code is canonical. AAH code reference only.',
  },
  {
    id: 'forecast-output',
    title: 'Forecast Output',
    acceptedFileTypes: 'XLSX, CSV',
    requiredColumns: ['AAH_Product_Code', 'Inference_Date', 'Forecast_Week', 'Model'],
    fields: {
      'AAH_Product_Code': 'required',
      'Inference_Date': 'required',
      'Forecast_Week': 'required',
      'Model': 'required',
      'Forecast': 'optional',
      'Actual': 'optional',
      'Interpolated_Values': 'optional',
      'Product_Name': 'optional',
      'Model_Details': 'optional',
      'Mean_Absolute_Error': 'optional',
      'Mean_Absolute_Percentage_Error': 'optional',
      'Is_Best_Model': 'optional',
      'Outlier': 'optional',
      'Predicted_Best_Model_Bool': 'optional',
    },
    notes: 'At least one of Forecast, Actual, Interpolated_Values required. AAH_Product_Code must exist.',
  },
  {
    id: 'backbone-stock-positions',
    title: 'Backbone: Stock positions',
    acceptedFileTypes: 'CSV',
    requiredColumns: ['warehouse_code', 'sku', 'iso_year', 'iso_week', 'on_hand_units'],
    fields: {
      'warehouse_code': 'required',
      'sku': 'required',
      'iso_year': 'required',
      'iso_week': 'required',
      'on_hand_units': 'required',
    },
    notes: 'Direct import. iso_week 1–53.',
  },
  {
    id: 'backbone-inbound-orders',
    title: 'Backbone: Inbound orders',
    acceptedFileTypes: 'CSV',
    requiredColumns: ['warehouse_code', 'sku', 'iso_year', 'iso_week', 'inbound_units'],
    fields: {
      'warehouse_code': 'required',
      'sku': 'required',
      'iso_year': 'required',
      'iso_week': 'required',
      'inbound_units': 'required',
      'supplier_code': 'optional',
    },
    notes: 'Direct import.',
  },
  {
    id: 'backbone-demand-weekly',
    title: 'Backbone: Demand weekly',
    acceptedFileTypes: 'CSV',
    requiredColumns: ['warehouse_code', 'sku', 'iso_year', 'iso_week', 'demand_units'],
    fields: {
      'warehouse_code': 'required',
      'sku': 'required',
      'iso_year': 'required',
      'iso_week': 'required',
      'demand_units': 'required',
    },
    notes: 'Direct import.',
  },
  {
    id: 'legacy-inventory-snapshots',
    title: 'Legacy: Inventory snapshots',
    acceptedFileTypes: 'CSV',
    requiredColumns: ['week_start', 'sku', 'warehouse_code', 'on_hand_qty'],
    fields: {
      'week_start': 'required',
      'sku': 'required',
      'warehouse_code': 'required',
      'on_hand_qty': 'required',
    },
    notes: 'Template: /api/templates/inventory-snapshots',
  },
  {
    id: 'legacy-receipts',
    title: 'Legacy: Receipts',
    acceptedFileTypes: 'CSV',
    requiredColumns: ['week_start', 'sku', 'warehouse_code', 'qty', 'source_type'],
    fields: {
      'week_start': 'required',
      'sku': 'required',
      'warehouse_code': 'required',
      'qty': 'required',
      'source_type': 'required',
    },
    notes: 'Template: /api/templates/receipts',
  },
  {
    id: 'legacy-samples-withdrawals',
    title: 'Legacy: Samples withdrawals',
    acceptedFileTypes: 'CSV',
    requiredColumns: ['week_start', 'sku', 'warehouse_code', 'qty'],
    fields: {
      'week_start': 'required',
      'sku': 'required',
      'warehouse_code': 'required',
      'qty': 'required',
    },
    notes: 'Template: /api/templates/samples-withdrawals',
  },
  {
    id: 'legacy-products-simple',
    title: 'Legacy: Products (simple)',
    acceptedFileTypes: 'CSV',
    requiredColumns: ['sku'],
    fields: {
      'sku': 'required',
      'name': 'optional',
      'description': 'optional',
    },
    notes: 'Template: /api/templates/products',
  },
  {
    id: 'legacy-sku-code-map',
    title: 'Legacy: SKU code map',
    acceptedFileTypes: 'CSV',
    requiredColumns: ['old_sku', 'new_sku'],
    fields: {
      'old_sku': 'required',
      'new_sku': 'required',
      'effective_from_week_start': 'optional',
      'effective_to_week_start': 'optional',
      'notes': 'optional',
    },
    notes: 'Template: /api/templates/sku-code-map. Mapping for staging → canonical.',
  },
]

/** All unique field names across imports, for matrix rows */
export function getAllFields(): string[] {
  const set = new Set<string>()
  for (const imp of IMPORT_FORMATS) {
    for (const f of Object.keys(imp.fields)) {
      set.add(f)
    }
  }
  return Array.from(set).sort()
}
