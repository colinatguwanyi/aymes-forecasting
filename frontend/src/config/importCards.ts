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
  targetWarehouse: string
  supportsHistorical: boolean
  historicalDisabledMessage?: string
  templateHref?: string
  linkHref?: string
  linkLabel?: string
}

export function getImportCardsForLocation(locationCode: string | null | undefined): ImportCardDef[] {
  const targetWarehouse = (locationCode || '').trim().toUpperCase()
  const locationCards: ImportCardDef[] = targetWarehouse
    ? [
        {
          id: `${targetWarehouse}-sales-out`,
          dataType: 'sales_out',
          title: 'Sales Out',
          formatName: 'Sales Out',
          requiredColumns: ['AAH_Product_Code', 'Business_Processed_Date', 'Invoiced_Qty'],
          entity: 'sales_out',
          targetWarehouse,
          supportsHistorical: true,
          templateHref: undefined,
        },
        {
          id: `${targetWarehouse}-soh`,
          dataType: 'stock_on_hand',
          title: 'Stock on Hand (SOH)',
          formatName: 'SOH',
          requiredColumns: ['Stock at or snapshot date', 'Product code', 'STOCK or Balance'],
          entity: 'stock_on_hand',
          targetWarehouse,
          supportsHistorical: true,
          templateHref: '/api/templates/stock-on-hand',
        },
        {
          id: `${targetWarehouse}-demand-pipeline`,
          dataType: 'demand_pipeline',
          title: 'Demand (pipeline)',
          formatName: 'Demand weekly',
          requiredColumns: ['week_start', 'sku', 'warehouse_code', 'demand_type', 'qty'],
          entity: 'demand',
          targetWarehouse,
          supportsHistorical: true,
          templateHref: '/api/templates/demand-weekly',
        },
      ]
    : []

  return [
    {
      id: 'product-master',
      dataType: 'product_master',
      title: 'Product Master',
      formatName: 'Product Master',
      requiredColumns: ['SKU code', 'Description'],
      entity: 'product_master',
      targetWarehouse,
      supportsHistorical: false,
      templateHref: '/api/templates/product-master',
    },
    ...locationCards,
  ]
}

const IMPORTS_STORAGE_KEY = 'imports_warehouse'

export function getStoredWarehouse(): string {
  try {
    return localStorage.getItem(IMPORTS_STORAGE_KEY)?.trim().toUpperCase() || ''
  } catch {
    /* ignore */
  }
  return ''
}

export function setStoredWarehouse(wh: string): void {
  try {
    const value = wh.trim().toUpperCase()
    if (value) localStorage.setItem(IMPORTS_STORAGE_KEY, value)
    else localStorage.removeItem(IMPORTS_STORAGE_KEY)
  } catch {
    /* ignore */
  }
}
