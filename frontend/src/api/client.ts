import axios from 'axios'

export interface NormalizedApiError {
  message: string
  code: string
  detail?: string
  statusCode?: number
  nextActions: string[]
  technicalDetails?: unknown
}

/** Use on ingestion file POSTs; staging can run many minutes after upload bytes complete. */
export const INGESTION_UPLOAD_TIMEOUT_MS = 3_600_000

/** Admin full DB reset can run many DELETEs; align with Vite `/api` proxy timeout. */
export const ADMIN_DATA_RESET_TIMEOUT_MS = 3_600_000

/** Summary + reset-preview run many COUNT queries; allow long responses on large MySQL DBs. */
export const ADMIN_DATA_MANAGEMENT_READ_TIMEOUT_MS = 3_600_000

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function stringifyDetail(value: unknown): string | undefined {
  if (value == null) return undefined
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function pickString(record: Record<string, unknown>, key: string): string | undefined {
  const value = record[key]
  return typeof value === 'string' && value.trim() ? value : undefined
}

function nextActionsFor(statusCode: number | undefined, code: string): string[] {
  if (code === 'ECONNABORTED' || code === 'timeout') {
    return ['Refresh the page or status list before retrying.', 'Check whether the server completed the request in the background.']
  }
  if (!statusCode) {
    return ['Check that the API server is running.', 'Retry after network connectivity is restored.']
  }
  if (statusCode === 401) return ['Sign in again, then retry.']
  if (statusCode === 403) return ['Ask an administrator to confirm your access.', 'Retry with an account that has permission.']
  if (statusCode === 409) return ['Refresh the current data, resolve the conflict, then retry.']
  if (statusCode === 422) return ['Check the form inputs and required fields, then retry.']
  if (statusCode >= 500) return ['Check API/server logs.', 'Retry after the backend is healthy.']
  return ['Review the error details, then retry.']
}

export function normalizeApiError(error: unknown): NormalizedApiError {
  if (axios.isAxiosError(error)) {
    const statusCode = error.response?.status
    const responseData = error.response?.data
    const detail = isRecord(responseData) && 'detail' in responseData ? responseData.detail : responseData
    const detailRecord = isRecord(detail) ? detail : null
    const code =
      (detailRecord && pickString(detailRecord, 'code')) ||
      (isRecord(responseData) && pickString(responseData, 'code')) ||
      error.code ||
      (statusCode ? `http_${statusCode}` : 'network_error')
    const message =
      (detailRecord && pickString(detailRecord, 'message')) ||
      (isRecord(responseData) && pickString(responseData, 'message')) ||
      stringifyDetail(detail) ||
      error.message ||
      'Request failed'

    return {
      message,
      code,
      detail: stringifyDetail(detail),
      statusCode,
      nextActions: nextActionsFor(statusCode, code),
      technicalDetails: {
        code,
        statusCode,
        method: error.config?.method,
        url: error.config?.url,
        response: responseData,
      },
    }
  }

  if (error instanceof Error) {
    const code = error.name || 'error'
    return {
      message: error.message || 'Operation failed',
      code,
      detail: error.message || undefined,
      nextActions: nextActionsFor(undefined, code),
      technicalDetails: {
        name: error.name,
        message: error.message,
        stack: error.stack,
      },
    }
  }

  const detail = stringifyDetail(error)
  return {
    message: detail || 'Operation failed',
    code: 'unknown_error',
    detail,
    nextActions: nextActionsFor(undefined, 'unknown_error'),
    technicalDetails: error,
  }
}

// Add X-Dev-User so backend can authenticate without Entra (dev/local only on server).
// - Vite dev server (npm run dev): always sends (MODE !== production).
// - Built SPA: set VITE_SEND_DEV_AUTH_HEADER=true at build time for local “all on :8000” only.
const devUser =
  import.meta.env.VITE_DEV_USER ??
  JSON.stringify({ email: 'dev@local', name: 'Dev User', roles: ['Admin'] })

const sendDevAuthHeader =
  import.meta.env.MODE !== 'production' ||
  import.meta.env.VITE_SEND_DEV_AUTH_HEADER === 'true'

api.interceptors.request.use((config) => {
  if (sendDevAuthHeader) {
    config.headers['X-Dev-User'] = devUser
  }
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type']
  }
  return config
})

// Log 4xx/5xx detail so users see the server message in console (and we can show in UI)
api.interceptors.response.use(
  (r) => r,
  (err) => {
    const normalized = normalizeApiError(err)
    console.error('API error:', normalized.statusCode, normalized.message)
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
  notes?: string | null
  warehouses_scope?: string[] | null
  progress_meta?: {
    planning_mode?: string
    synthetic_starting_inventory?: boolean
    demand_source?: string
    plan_start_week_start?: string | null
    warehouses_planned?: string[]
    warehouses_planned_detail?: Array<{
      warehouse_code: string
      latest_soh_week_start?: string | null
      latest_demand_week_start?: string | null
      policy_pairs_count?: number
      starting_inv_pairs_count?: number
      overlap_pairs_count?: number
      skus_planned?: number
    }>
    warehouses_skipped?: string[]
    projected_inventory_rows_written?: number
    planned_orders_rows_written?: number
    skipped_warehouses_detail?: Array<{ warehouse_code: string; blockers: string[] }>
  } | null
}

/** Effective planning mode from API metadata; legacy runs without key are stock-aware. */
export function planRunPlanningMode(r: PlanRun): 'stock_aware' | 'demand_only' {
  return r.progress_meta?.planning_mode === 'demand_only' ? 'demand_only' : 'stock_aware'
}

/** Subtle suffix for list labels: demand-only runs are not physical SOH projections. */
function planRunModeLabelSuffix(r: PlanRun): string {
  if (planRunPlanningMode(r) !== 'demand_only') return ''
  const syn = r.progress_meta?.synthetic_starting_inventory ? ' · synthetic start' : ''
  return ` [Demand-only${syn}]`
}

/** Display label for a plan run: notes if set, else "scenario (date) #id"; demand_only runs get a mode suffix. */
export function formatPlanRunLabel(r: PlanRun): string {
  const suffix = planRunModeLabelSuffix(r)
  if (r.notes && String(r.notes).trim()) return `${String(r.notes).trim()}${suffix}`
  return `${r.scenario_name} (${r.run_at}) #${r.id}${suffix}`
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

/** site_type: soh_warehouse | factory | third_party_3pl */
export interface Warehouse {
  id: number
  code: string
  name: string | null
  timezone: string
  active: boolean
  is_own_site: boolean
  operator_name: string | null
  address: string | null
  site_type: string
  has_stock: boolean
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

/** Planning readiness diagnostics from GET /api/v1/diagnostics/planning-readiness */
export interface PlanningReadinessDiagnostics {
  ready_to_plan: boolean
  /** Echo of requested planning_mode query (default stock_aware). */
  planning_mode?: string
  blockers: Array<{ code: string; message: string; action_label: string; action_href: string }>
  stats: {
    products_count: number
    policies_count: number
    demand_rows: number
    demand_latest_week: string | null
    demand_warehouses: string[]
    soh_rows: number
    soh_latest_week: string | null
    soh_warehouses: string[]
    soh_config_warehouses: string[]
    receipts_rows: number
    receipts_latest_week: string | null
    plan_runs_count: number
    projected_inventory_rows_for_run: number
    planned_orders_rows_for_run: number
  }
}

export async function fetchPlanningReadiness(
  planRunId?: number | null,
  planningMode: 'stock_aware' | 'demand_only' = 'stock_aware',
): Promise<PlanningReadinessDiagnostics> {
  const params = new URLSearchParams()
  if (planRunId != null) params.set('plan_run_id', String(planRunId))
  params.set('planning_mode', planningMode)
  const q = params.toString()
  const { data } = await api.get<PlanningReadinessDiagnostics>(`/v1/diagnostics/planning-readiness?${q}`)
  return data
}

/** Per-warehouse readiness from GET /api/v1/diagnostics/warehouse-readiness */
export interface WarehouseReadinessItem {
  warehouse_code: string
  has_soh: boolean
  has_demand: boolean
  has_policies: boolean
  overlap_pairs: number
  ready: boolean
  blockers: string[]
  soh_latest_week: string | null
  demand_latest_week: string | null
}

export async function fetchWarehouseReadiness(
  demandSource: string = 'actuals',
  planningMode: 'stock_aware' | 'demand_only' = 'stock_aware',
): Promise<WarehouseReadinessItem[]> {
  const params = new URLSearchParams({ demand_source: demandSource, planning_mode: planningMode })
  const { data } = await api.get<WarehouseReadinessItem[]>(`/v1/diagnostics/warehouse-readiness?${params}`)
  return data
}

export type ForecastCheckStatus = 'green' | 'amber' | 'red'

export interface ForecastCheckCard {
  status: ForecastCheckStatus
  message: string
}

export interface ForecastCheckSalesFreshness extends ForecastCheckCard {
  latest_week: string | null
  weeks_available: number
  sku_count: number
}

export interface ForecastCheckSohFreshness extends ForecastCheckCard {
  latest_week: string | null
  sku_count: number
}

export interface ForecastCheckRun extends ForecastCheckCard {
  latest_run_id: number | null
  run_status: string | null
  inference_date: string | null
  completed_at: string | null
}

export interface ForecastCheckPlanningAlignment extends ForecastCheckCard {
  latest_baseline: string | null
  latest_plan_baseline: string | null
}

export interface ForecastCheckCoverage extends ForecastCheckCard {
  orphan_sku_count: number
  policy_gaps: number
  demand_without_soh_count: number | null
  demand_without_soh_ratio: number | null
}

export interface ForecastCheck {
  overall_status: ForecastCheckStatus
  headline: string
  sales_freshness: ForecastCheckSalesFreshness
  soh_freshness: ForecastCheckSohFreshness
  forecast_run: ForecastCheckRun
  planning_alignment: ForecastCheckPlanningAlignment
  sku_data_coverage: ForecastCheckCoverage
  actions: string[]
}

export async function fetchForecastCheck(): Promise<ForecastCheck> {
  const { data } = await api.get<ForecastCheck>('/v1/forecast/check')
  return data
}
