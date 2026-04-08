/**
 * Warehouse-first import cards config.
 * Single source of truth for what each warehouse supports.
 */

export type WarehouseCode = 'AAH' | 'BLP'

export type ImportDataType =
  | 'sales_out'
  | 'stock_on_hand'
  | 'demand'
  | 'demand_pipeline'
  | 'product_master'
  | 'warehouse_product_codes'
  | 'sales_direct'
  | 'samples'

export interface ImportCardDef {
  id: string
  dataType: ImportDataType
  title: string
  formatName: string
  requiredColumns: string[]
  entity: string
  targetWarehouse: WarehouseCode
  supportsHistorical: boolean
  historicalDisabledMessage?: string
  templateHref?: string
  linkHref?: string
  linkLabel?: string
}

/** Cards per warehouse. Data type selector options. */
export const IMPORT_CARDS_BY_WAREHOUSE: Record<WarehouseCode, ImportCardDef[]> = {
  AAH: [
    {
      id: 'aah-sales-out',
      dataType: 'sales_out',
      title: 'Sales Out',
      formatName: 'AAH Sales Out',
      requiredColumns: ['AAH_Product_Code', 'Business_Processed_Date', 'Invoiced_Qty'],
      entity: 'sales_out',
      targetWarehouse: 'AAH',
      supportsHistorical: true,
      templateHref: undefined,
    },
    {
      id: 'aah-soh',
      dataType: 'stock_on_hand',
      title: 'Stock on Hand (SOH)',
      formatName: 'AAH SOH',
      requiredColumns: ['Stock at', 'AAH Code', 'STOCK', 'ON ORDER'],
      entity: 'stock_on_hand',
      targetWarehouse: 'AAH',
      supportsHistorical: true,
      templateHref: '/api/templates/stock-on-hand',
    },
    {
      id: 'aah-demand-pipeline',
      dataType: 'demand_pipeline',
      title: 'Demand (pipeline)',
      formatName: 'Demand weekly',
      requiredColumns: ['week_start', 'sku', 'warehouse_code', 'demand_type', 'qty'],
      entity: 'demand',
      targetWarehouse: 'AAH',
      supportsHistorical: true,
      templateHref: '/api/templates/demand-weekly',
    },
    {
      id: 'aah-product-master',
      dataType: 'product_master',
      title: 'Product Master',
      formatName: 'Product Master',
      requiredColumns: ['SKU code', 'Description'],
      entity: 'product_master',
      targetWarehouse: 'AAH',
      supportsHistorical: false,
      templateHref: '/api/templates/product-master',
    },
  ],
  BLP: [
    {
      id: 'blp-sales-direct',
      dataType: 'sales_direct',
      title: 'Sales (direct)',
      formatName: 'Demand weekly',
      requiredColumns: ['week_start', 'sku', 'warehouse_code', 'demand_type', 'qty'],
      entity: 'demand',
      targetWarehouse: 'BLP',
      supportsHistorical: true,
      templateHref: '/api/templates/demand-weekly',
    },
    {
      id: 'blp-samples',
      dataType: 'samples',
      title: 'Samples',
      formatName: 'Demand weekly',
      requiredColumns: ['week_start', 'sku', 'warehouse_code', 'demand_type', 'qty'],
      entity: 'demand',
      targetWarehouse: 'BLP',
      supportsHistorical: true,
      templateHref: '/api/templates/samples-withdrawals',
    },
    {
      id: 'blp-soh',
      dataType: 'stock_on_hand',
      title: 'Stock on Hand (SOH)',
      formatName: 'BLP SOH',
      requiredColumns: ['Code', 'Balance'],
      entity: 'stock_on_hand',
      targetWarehouse: 'BLP',
      supportsHistorical: true,
      historicalDisabledMessage: 'BLP SOH history not loaded yet',
      templateHref: '/api/templates/stock-on-hand',
    },
    {
      id: 'blp-product-master',
      dataType: 'product_master',
      title: 'Product Master',
      formatName: 'Product Master',
      requiredColumns: ['SKU code', 'Description'],
      entity: 'product_master',
      targetWarehouse: 'BLP',
      supportsHistorical: false,
      templateHref: '/api/templates/product-master',
    },
    {
      id: 'blp-warehouse-product-codes',
      dataType: 'warehouse_product_codes',
      title: 'Warehouse Product Codes',
      formatName: '—',
      requiredColumns: [],
      entity: '',
      targetWarehouse: 'BLP',
      supportsHistorical: false,
      linkHref: '/admin/warehouse-product-codes',
      linkLabel: 'Add Warehouse Product Codes',
    },
  ],
}

export const WAREHOUSE_OPTIONS: { value: WarehouseCode; label: string }[] = [
  { value: 'AAH', label: 'AAH' },
  { value: 'BLP', label: 'BLP' },
]

const IMPORTS_STORAGE_KEY = 'imports_warehouse'

export function getStoredWarehouse(): WarehouseCode {
  try {
    const v = localStorage.getItem(IMPORTS_STORAGE_KEY)
    if (v === 'AAH' || v === 'BLP') return v
  } catch {
    /* ignore */
  }
  return 'AAH'
}

export function setStoredWarehouse(wh: WarehouseCode): void {
  try {
    localStorage.setItem(IMPORTS_STORAGE_KEY, wh)
  } catch {
    /* ignore */
  }
}
