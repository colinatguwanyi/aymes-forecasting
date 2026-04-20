import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api, {
  type PlanRun,
  type PlannedOrder,
  type PlanningException,
  type ProjectedInventory,
  type Receipt,
  type DemandActual,
  type InventorySnapshot,
  type SkuWeekExplanation,
  type StockPositionBreakdown,
  type StockPositionRollingWeek,
} from '@/api/client'

export const usePlanningStore = defineStore('planning', () => {
  const planRuns = ref<PlanRun[]>([])
  const selectedRunIds = ref<number[]>([])

  async function fetchPlanRuns() {
    const { data } = await api.get<PlanRun[]>('/plan/runs')
    planRuns.value = data
    return data
  }

  async function runPlan(
    scenarioName: string,
    runAt?: string,
    demandSource: string = 'actuals',
    freezeWeeks: number = 4,
    notes?: string
  ) {
    const params = new URLSearchParams({
      scenario_name: scenarioName,
      demand_source: demandSource,
      freeze_weeks: String(freezeWeeks),
    })
    if (runAt) params.set('run_at', runAt)
    if (notes) params.set('notes', notes)
    const { data } = await api.post<PlanRun>(`/plan/run?${params}`)
    planRuns.value = [data, ...planRuns.value]
    return data
  }

  async function freezePlanRun(planRunId: number, scope: 'demand' | 'orders' | 'both', freezeWeeks?: number, frozenBy?: string, notes?: string) {
    const body: Record<string, unknown> = { scope }
    if (freezeWeeks != null) body.freeze_weeks = freezeWeeks
    if (frozenBy) body.frozen_by = frozenBy
    if (notes) body.notes = notes
    await api.post(`/plan/runs/${planRunId}/freeze`, body)
  }

  async function recalculateDemand(planRunId: number) {
    await api.post(`/plan/runs/${planRunId}/recalculate-demand`)
  }

  async function fetchExplain(planRunId: number, sku: string, warehouseCode: string, weekStart: string) {
    const params = new URLSearchParams({ sku, warehouse_code: warehouseCode, week_start: weekStart })
    const { data } = await api.get<Record<string, unknown>>(`/plan/runs/${planRunId}/explain?${params}`)
    return data
  }

  async function fetchProjectedInventory(planRunId: number, sku?: string, warehouseCode?: string) {
    const params = new URLSearchParams()
    if (sku) params.set('sku', sku)
    if (warehouseCode) params.set('warehouse_code', warehouseCode)
    const { data } = await api.get<ProjectedInventory[]>(`/plan/runs/${planRunId}/projected-inventory?${params}`)
    return data
  }

  async function fetchPlannedOrders(planRunId: number, sku?: string, warehouseCode?: string) {
    const params = new URLSearchParams()
    if (sku) params.set('sku', sku)
    if (warehouseCode) params.set('warehouse_code', warehouseCode)
    const { data } = await api.get<PlannedOrder[]>(`/plan/runs/${planRunId}/planned-orders?${params}`)
    return data
  }

  async function fetchSkuWeekExplanation(
    planRunId: number,
    sku: string,
    warehouseCode: string,
    weekStart: string
  ) {
    const params = new URLSearchParams({ sku, warehouse_code: warehouseCode, week_start: weekStart })
    const { data } = await api.get<SkuWeekExplanation>(
      `/plan/runs/${planRunId}/explanation?${params}`
    )
    return data
  }

  async function fetchExceptions(
    planRunId: number,
    withinWeeks: number = 12,
    includeLowCover: boolean = true
  ) {
    const params = new URLSearchParams({
      within_weeks: String(withinWeeks),
      include_low_cover: String(includeLowCover),
    })
    const { data } = await api.get<PlanningException[]>(
      `/plan/runs/${planRunId}/exceptions?${params}`
    )
    return data
  }

  async function fetchReceipts(sku: string, warehouseCode: string) {
    const params = new URLSearchParams({ sku, warehouse_code: warehouseCode })
    const { data } = await api.get<Receipt[]>(`/receipts?${params}`)
    return data
  }

  async function fetchDemandActuals(sku: string, warehouseCode: string) {
    const params = new URLSearchParams({ sku, warehouse_code: warehouseCode })
    const { data } = await api.get<DemandActual[]>(`/demand?${params}`)
    return data
  }

  async function fetchInventorySnapshots(sku: string, warehouseCode: string) {
    const params = new URLSearchParams({ sku, warehouse_code: warehouseCode })
    const { data } = await api.get<InventorySnapshot[]>(`/inventory?${params}`)
    return data
  }

  async function fetchStockPositionBreakdown(
    planRunId: number,
    opts?: { warehouseCode?: string; sku?: string; productFamily?: string; breachOnly?: boolean; limit?: number }
  ) {
    const params = new URLSearchParams({ plan_run_id: String(planRunId) })
    if (opts?.warehouseCode) params.set('warehouse_code', opts.warehouseCode)
    if (opts?.sku) params.set('sku', opts.sku)
    if (opts?.productFamily) params.set('product_family', opts.productFamily)
    if (opts?.breachOnly) params.set('breach_only', 'true')
    if (opts?.limit != null) params.set('limit', String(opts.limit))
    const { data } = await api.get<StockPositionBreakdown[]>(`/stock-position/breakdown?${params}`)
    return data
  }

  async function fetchStockPositionRolling(
    planRunId: number,
    warehouseCode: string,
    sku: string,
    weeks: number = 12
  ) {
    const params = new URLSearchParams({
      plan_run_id: String(planRunId),
      warehouse_code: warehouseCode,
      sku,
      weeks: String(weeks),
    })
    const { data } = await api.get<StockPositionRollingWeek[]>(`/stock-position/rolling?${params}`)
    return data
  }

  const selectedRuns = computed(() =>
    planRuns.value.filter((r) => selectedRunIds.value.includes(r.id))
  )

  return {
    planRuns,
    selectedRunIds,
    selectedRuns,
    fetchPlanRuns,
    runPlan,
    freezePlanRun,
    recalculateDemand,
    fetchExplain,
    fetchProjectedInventory,
    fetchPlannedOrders,
    fetchSkuWeekExplanation,
    fetchExceptions,
    fetchReceipts,
    fetchDemandActuals,
    fetchInventorySnapshots,
    fetchStockPositionBreakdown,
    fetchStockPositionRolling,
  }
})
