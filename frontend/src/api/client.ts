import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

export default api

export interface PlanRun {
  id: number
  scenario_name: string
  run_at: string
  created_at: string
}

export interface ProjectedInventory {
  id: number
  plan_run_id: number
  week_start: string
  sku: string
  warehouse_code: string
  projected_qty: string
  weeks_of_cover: string | null
  stockout: boolean
}

export interface PlannedOrder {
  id: number
  plan_run_id: number
  week_start: string
  sku: string
  warehouse_code: string
  order_qty: string
}

export interface Product {
  id: number
  sku: string
  name: string | null
  description: string | null
}

export interface Warehouse {
  id: number
  code: string
  name: string | null
}

export interface Supplier {
  id: number
  code: string
  name: string | null
}

export interface Lane {
  id: number
  supplier_id: number
  warehouse_id: number
  code: string | null
}

export interface PlanningPolicy {
  id: number
  sku: string
  warehouse_code: string
  mode: 'WOS_TARGET' | 'ROP'
  target_weeks: string
  safety_stock_method: 'WEEKS' | 'SERVICE_LEVEL'
  safety_stock_weeks: string
  service_level: string
  forecast_window_weeks: number
  lead_time_production_weeks: string
  lead_time_slot_wait_weeks: string
  lead_time_haulage_weeks: string
  lead_time_putaway_weeks: string
  lead_time_padding_weeks: string
}

/** Explain-the-forecast payload for one SKU/week (Phase 1). */
export interface SkuWeekExplanationPolicy {
  mode?: string | null
  target_weeks?: string | null
  safety_stock_weeks?: string | null
  safety_stock_method?: string | null
  forecast_window_weeks?: number | null
  lead_time_production_weeks?: string | null
  lead_time_slot_wait_weeks?: string | null
  lead_time_haulage_weeks?: string | null
  lead_time_putaway_weeks?: string | null
  lead_time_padding_weeks?: string | null
  include_samples?: boolean
}

export interface SkuWeekExplanationProjection {
  week_start: string
  start_qty?: string | null
  receipts_qty?: string | null
  demand_qty?: string | null
  projected_qty: string
  weeks_of_cover?: string | null
  stockout: boolean
}

export interface SkuWeekExplanation {
  sku: string
  warehouse_code: string
  plan_run_id: number
  policy?: SkuWeekExplanationPolicy | null
  projection?: SkuWeekExplanationProjection | null
  forecast_method: string
}

export interface Receipt {
  id: number
  week_start: string
  sku: string
  warehouse_code: string
  qty: string
  source_type: string | null
}

export interface DemandActual {
  id: number
  week_start: string
  sku: string
  warehouse_code: string
  demand_type: string
  qty: string
}

export interface InventorySnapshot {
  id: number
  week_start: string
  sku: string
  warehouse_code: string
  on_hand_qty: string
}

export interface ImportRowError {
  row: number
  errors: string[]
}

export interface ImportDryRunResult {
  valid: boolean
  total_rows: number
  valid_rows: number
  errors: ImportRowError[]
  preview?: Record<string, string | number | null>[]
}
