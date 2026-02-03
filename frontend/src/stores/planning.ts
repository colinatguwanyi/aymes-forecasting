import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api, { type PlanRun, type ProjectedInventory, type PlannedOrder } from '@/api/client'

export const usePlanningStore = defineStore('planning', () => {
  const planRuns = ref<PlanRun[]>([])
  const selectedRunIds = ref<number[]>([])

  async function fetchPlanRuns() {
    const { data } = await api.get<PlanRun[]>('/plan/runs')
    planRuns.value = data
    return data
  }

  async function runPlan(scenarioName: string, runAt?: string) {
    const params = new URLSearchParams({ scenario_name: scenarioName })
    if (runAt) params.set('run_at', runAt)
    const { data } = await api.post<PlanRun>(`/plan/run?${params}`)
    planRuns.value = [data, ...planRuns.value]
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

  const selectedRuns = computed(() =>
    planRuns.value.filter((r) => selectedRunIds.value.includes(r.id))
  )

  return {
    planRuns,
    selectedRunIds,
    selectedRuns,
    fetchPlanRuns,
    runPlan,
    fetchProjectedInventory,
    fetchPlannedOrders,
  }
})
