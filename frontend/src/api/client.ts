import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// When sending FormData (e.g. file upload), do not set Content-Type so the browser
// sets multipart/form-data with boundary. Otherwise the server may not parse the body.
api.interceptors.request.use((config) => {
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type']
  }
  return config
})

// Log 4xx/5xx detail so users see the server message in console (and we can show in UI)
api.interceptors.response.use(
  (r) => r,
  (err) => {
    const detail = err.response?.data?.detail
    if (detail != null) {
      console.error('API error:', err.response?.status, typeof detail === 'string' ? detail : JSON.stringify(detail))
    }
    return Promise.reject(err)
  }
)

export default api

export interface PlanRun {
  id: number
  scenario_name: string
  run_at: string
  created_at: string
  demand_source?: string
  freeze_weeks?: number
  baseline_train_end_week_start?: string | null
  selected_train_end_week_start?: string | null
}

/** One row from GET /forecast/runs (available baseline runs to pin). */
export interface ForecastRunOption {
  train_end_week_start: string
  model_name?: string | null
  count_rows: number
  created_at?: string | null
  notes?: string | null
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
  uom: string
  active: boolean
  product_family?: string | null
}

export interface Warehouse {
  id: number
  code: string
  name: string | null
  timezone: string
  active: boolean
}

export interface Supplier {
  id: number
  code: string
  name: string | null
  active: boolean
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
  include_samples: boolean
}

/** Planning exception for exceptions queue (Phase 3). */
export interface PlanningException {
  type: 'stockout' | 'low_cover'
  severity: 'error' | 'warning'
  sku: string
  warehouse_code: string
  week_start: string
  message: string
  projected_qty?: string | null
  weeks_of_cover?: string | null
  plan_run_id: number
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
  demand_breakdown?: Record<string, unknown> | null
  demand_includes_samples?: boolean | null
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

/** Backbone import: row_number + message per error */
export interface BackboneImportError {
  row_number: number
  message: string
}

export interface BackboneImportResult {
  rows_processed: number
  rows_failed: number
  errors: BackboneImportError[]
}

/** Backbone: warehouse-product planning parameters */
export interface WarehouseProduct {
  id: number
  warehouse_id: number
  product_id: number
  safety_stock_mode: 'fixed_units' | 'fixed_weeks'
  safety_stock_units: number | null
  safety_stock_weeks: number | null
  haulage_buffer_weeks: number
  stocking_buffer_weeks: number
  reorder_review_weeks: number
  active: boolean
}

/** Backbone: supplier-product (lead time, MOQ, pack size) */
export interface SupplierProduct {
  id: number
  supplier_id: number
  product_id: number
  lead_time_weeks: number
  moq_units: number | null
  pack_size_units: number | null
  active: boolean
}

export interface ImportDryRunResult {
  valid: boolean
  total_rows: number
  valid_rows: number
  errors: ImportRowError[]
  preview?: Record<string, string | number | null>[]
}

/** Timeline view: lead time segments + markers. */
export interface TimelineSegment {
  key: string
  label: string
  start_week_index: number
  duration_weeks: number
  tooltip: string
}

export interface TimelineMarker {
  key: string
  label: string
  week_index: number
  type: 'stockout' | 'receipt' | 'need_by'
  tooltip: string
  qty?: string
}

export interface TimelineReceiptRow {
  week_start: string
  qty: string
  on_time: boolean
}

export interface TimelineResponse {
  week_labels: string[]
  segments: TimelineSegment[]
  markers: TimelineMarker[]
  receipts: TimelineReceiptRow[]
}

/** Plan run demand input row (single truth for planning). */
export interface DemandInputRow {
  week_start: string
  sku: string
  warehouse_code: string
  demand_qty: number
  source: string
  source_ref: Record<string, unknown> | null
  demand_breakdown_json: Record<string, unknown> | null
  demand_includes_samples: boolean
  is_frozen: boolean
}

/** Stock position breakdown row (per SKU x warehouse). */
export interface StockPositionBreakdown {
  plan_run_id: number
  sku: string
  warehouse_code: string
  current_week_start: string
  on_hand_qty: string
  on_hand_snapshot_week: string | null
  avg_weekly_demand: string
  forecast_window_weeks: number
  target_weeks: number
  safety_stock_weeks: number
  safety_stock_method: string
  safety_stock_units: number
  supplier_lead_time_weeks: number
  haulage_buffer_weeks: number
  stocking_buffer_weeks: number
  effective_lead_time_weeks: number
  reorder_point_units: number
  target_stock_units: number
  next_breach_week_start: string | null
  projected_qty_at_breach: number | null
  recommended_order_week_start: string | null
  recommended_order_qty: number
  projected_qty_at_arrival: number | null
  moq_units: number | null
  pack_size_units: number | null
  mode: string
}

/** Forecast methods descriptor (governance/audit). */
export interface ForecastMethodsDoc {
  method_version: string
  updated_at: string
  overview?: Record<string, unknown>
  inputs?: Record<string, unknown>
  time_series_prep?: Record<string, unknown>
  forecasting?: Record<string, unknown>
  planning_integration?: Record<string, unknown>
  known_limitations?: string[]
  audit?: { hash?: string }
}

/** Forecast method acknowledgement (sign-off). */
export interface ForecastMethodAcknowledgement {
  id: number
  created_by: string
  method_version: string
  method_hash: string
  acknowledged_at: string
  notes: string | null
}

/** Rolling week row (opening/receipts/demand/closing + planned order). */
export interface StockPositionRollingWeek {
  week_start: string
  opening_qty: string
  receipts_qty: string
  demand_qty: string
  closing_qty: string
  weeks_of_cover: number | null
  stockout: boolean
  planned_order_qty: string | null
}
