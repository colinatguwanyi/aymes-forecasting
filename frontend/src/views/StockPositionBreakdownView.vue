<template>
  <div class="page-shell space-y-6">
    <header class="page-header">
      <PageHeader title="Stock Position Breakdown" :breadcrumbs="[{ label: 'Planning', path: '/' }]" />
    </header>

    <PageHelpPanel page-key="StockPosition" />

    <section v-if="selectedRunSkippedWarehouses.length" class="mb-4 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-sm">
      Some warehouses were skipped: {{ selectedRunSkippedWarehouses.join(', ') }}.
    </section>

    <section v-if="planRunId && selectedRun" class="mb-3 flex flex-wrap items-center gap-2 text-sm">
      <span
        class="inline-flex items-center rounded-md px-2 py-1 text-xs font-medium border"
        :class="isDemandOnlyRun ? 'bg-sky-50 text-sky-900 border-sky-200' : 'bg-emerald-50 text-emerald-900 border-emerald-200'"
      >{{ planningModeLabel }}</span>
      <span v-if="isDemandOnlyRun && syntheticStartingInventory" class="text-xs text-slate-600">This run used synthetic starting inventory where SOH was missing.</span>
    </section>

    <section v-if="planRunId && isDemandOnlyRun" class="mb-4 p-3 rounded-lg bg-sky-50 border border-sky-200 text-sky-900 text-sm">
      <strong>Demand-only run.</strong> Projected inventory and the rolling-week view (when you open a row) are a modeled ledger, not warehouse on-hand. <strong>On hand</strong> in the table and detail panel still comes from stock snapshots where available. Treat target, ROP, and breach signals as planning views, not physical stock truth.
    </section>

    <section class="card card-body">
      <FilterBar
        v-model="search"
        search-placeholder="Search SKU or warehouse…"
        :has-active-filters="hasActiveFilters"
        @clear="clearFilters"
      >
        <template #filters>
          <select v-model="planRunId" class="select min-w-48">
            <option :value="null">Plan run</option>
            <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ formatPlanRunLabel(r) }}</option>
          </select>
          <select v-model="warehouseFilter" class="select min-w-40">
            <option value="">All warehouses</option>
            <option v-for="w in warehouses" :key="w.id" :value="w.code">{{ w.code }}</option>
          </select>
          <select v-model="productFamilyFilter" class="select min-w-40">
            <option value="">All families</option>
            <option v-for="f in productFamilies" :key="f" :value="f">{{ f }}</option>
          </select>
          <label class="flex items-center gap-2 text-sm text-slate-700">
            <input v-model="breachOnly" type="checkbox" class="rounded border-slate-300" />
            Breach only
          </label>
        </template>
      </FilterBar>
    </section>

    <section class="card">
      <p class="card-header text-sm text-slate-500">
        Click a row to open the calculation breakdown and 12-week rolling view.
        <span class="block mt-1.5 text-xs text-slate-500 leading-snug">
          Target and ROP (units) come from <strong>stock position breakdown</strong> logic. Lead time and safety stock used here may differ from the weekly planning engine.
        </span>
      </p>
      <div v-if="loading" class="px-5 py-8 text-sm text-slate-500">Loading…</div>
      <div v-else-if="displayRows.length" class="overflow-x-auto max-h-[60vh] overflow-y-auto">
        <table class="w-full text-sm border-collapse">
          <thead class="sticky top-0 z-10 bg-slate-50 border-b border-slate-200">
            <tr>
              <th class="px-3 py-1.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">SKU</th>
              <th class="px-3 py-1.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Warehouse</th>
              <th class="px-3 py-1.5 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">On hand</th>
              <th class="px-3 py-1.5 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">Avg demand</th>
              <th class="px-3 py-1.5 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">ROP</th>
              <th class="px-3 py-1.5 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">Target</th>
              <th class="px-3 py-1.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Next breach</th>
              <th class="px-3 py-1.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Order week</th>
              <th class="px-3 py-1.5 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">Rec. qty</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="r in displayRows"
              :key="`${r.sku}-${r.warehouse_code}`"
              :class="[r.next_breach_week_start && 'bg-amber-50', 'border-b border-slate-200 hover:bg-slate-50 cursor-pointer']"
              @click="openDetail(r)"
            >
              <td class="px-3 py-1.5 text-slate-700">{{ r.sku }}</td>
              <td class="px-3 py-1.5 text-slate-700">{{ r.warehouse_code }}</td>
              <td class="px-3 py-1.5 text-right text-slate-700">{{ r.on_hand_qty }}</td>
              <td class="px-3 py-1.5 text-right text-slate-700">{{ r.avg_weekly_demand }}</td>
              <td class="px-3 py-1.5 text-right text-slate-700">{{ r.reorder_point_units }}</td>
              <td class="px-3 py-1.5 text-right text-slate-700">{{ r.target_stock_units }}</td>
              <td class="px-3 py-1.5 text-slate-700">{{ r.next_breach_week_start ?? '—' }}</td>
              <td class="px-3 py-1.5 text-slate-700">{{ r.recommended_order_week_start ?? '—' }}</td>
              <td class="px-3 py-1.5 text-right text-slate-700">{{ r.recommended_order_qty }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <NoDataWithReason
        v-else
        :title="noDataTitle"
        :reasons="noDataReasons"
        :actions="noDataActions"
      />
    </section>

    <Teleport to="#right-panel-body">
      <div v-if="detailRow" class="stock-position-detail">
        <template v-if="detailLoading">Loading…</template>
        <template v-else>
          <h3 class="text-sm font-semibold text-neutral-800 mb-2">{{ detailRow.sku }} × {{ detailRow.warehouse_code }}</h3>

          <section class="mb-4">
            <h4 class="text-xs font-medium text-neutral-600 uppercase tracking-wide mb-1">Inputs</h4>
            <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
              <dt class="text-neutral-500">On hand</dt><dd>{{ detailRow.on_hand_qty }} (week {{ detailRow.on_hand_snapshot_week ?? '—' }})</dd>
              <dt class="text-neutral-500">Avg weekly demand</dt><dd>{{ detailRow.avg_weekly_demand }}</dd>
              <dt class="text-neutral-500">Forecast window</dt><dd>{{ detailRow.forecast_window_weeks }} weeks</dd>
            </dl>
          </section>

          <section class="mb-4">
            <h4 class="text-xs font-medium text-neutral-600 uppercase tracking-wide mb-1">Policy</h4>
            <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
              <dt class="text-neutral-500">Mode</dt><dd>{{ detailRow.mode }}</dd>
              <dt class="text-neutral-500">Target weeks</dt><dd>{{ detailRow.target_weeks }}</dd>
              <dt class="text-neutral-500">Safety stock</dt><dd>{{ detailRow.safety_stock_method }} {{ detailRow.safety_stock_weeks }} wk → {{ detailRow.safety_stock_units }} units</dd>
              <dt class="text-neutral-500">Effective lead time</dt><dd>{{ detailRow.effective_lead_time_weeks }} wk (supplier {{ detailRow.supplier_lead_time_weeks }} + haul {{ detailRow.haulage_buffer_weeks }} + stock {{ detailRow.stocking_buffer_weeks }})</dd>
              <dt class="text-neutral-500">MOQ / Pack</dt><dd>{{ detailRow.moq_units ?? '—' }} / {{ detailRow.pack_size_units ?? '—' }}</dd>
            </dl>
          </section>

          <section v-if="demandInputsForDetail.length" class="mb-4">
            <h4 class="text-xs font-medium text-neutral-600 uppercase tracking-wide mb-1">Demand composition</h4>
            <p class="text-xs text-neutral-500 mb-1">Included/excluded types and totals per week (samples {{ demandInputsForDetail[0]?.demand_includes_samples !== false ? 'included' : 'excluded' }}).</p>
            <div class="overflow-x-auto max-h-[24vh] overflow-y-auto">
              <table class="w-full text-xs border-collapse">
                <thead class="bg-neutral-50 border-b border-neutral-200">
                  <tr>
                    <th class="px-2 py-1.5 text-left font-medium text-neutral-600">Week</th>
                    <th class="px-2 py-1.5 text-right font-medium text-neutral-600">Qty</th>
                    <th class="px-2 py-1.5 text-left font-medium text-neutral-600">Source</th>
                    <th class="px-2 py-1.5 text-left font-medium text-neutral-600">Breakdown</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="d in demandInputsForDetail.slice(0, 12)"
                    :key="d.week_start"
                    class="border-b border-neutral-100"
                  >
                    <td class="px-2 py-1.5">{{ d.week_start }}</td>
                    <td class="px-2 py-1.5 text-right">{{ d.demand_qty }}</td>
                    <td class="px-2 py-1.5">{{ d.source }}</td>
                    <td class="px-2 py-1.5">
                      <span v-if="d.demand_breakdown_json">
                        <template v-if="d.demand_breakdown_json.OVERRIDE">
                          Override ({{ d.demand_breakdown_json.reason_code ?? '—' }})
                        </template>
                        <template v-else-if="d.demand_breakdown_json.FORECAST_TOTAL != null">
                          Forecast
                        </template>
                        <template v-else>
                          <span v-if="getBreakdownIncluded(d.demand_breakdown_json)" class="text-neutral-600">In: {{ getBreakdownIncluded(d.demand_breakdown_json) }}</span>
                          <span v-if="getBreakdownExcluded(d.demand_breakdown_json)" class="text-neutral-500"> · Ex: {{ getBreakdownExcluded(d.demand_breakdown_json) }}</span>
                          <span v-if="d.demand_breakdown_json.CUSTOMER != null"> C{{ d.demand_breakdown_json.CUSTOMER }}</span>
                          <span v-if="d.demand_breakdown_json.SAMPLES != null"> S{{ d.demand_breakdown_json.SAMPLES }}</span>
                          <span v-if="d.demand_breakdown_json.ADJUSTMENT != null"> A{{ d.demand_breakdown_json.ADJUSTMENT }}</span>
                        </template>
                      </span>
                      <span v-else class="text-neutral-400">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section class="mb-4">
            <h4 class="text-xs font-medium text-neutral-600 uppercase tracking-wide mb-1">Derived</h4>
            <p class="text-xs text-neutral-500 mb-2 leading-snug">
              Target and ROP below are from stock position breakdown rules. Lead time and safety stock here may differ from the weekly planning engine.
            </p>
            <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
              <dt class="text-neutral-500">Reorder point</dt><dd>{{ detailRow.reorder_point_units }}</dd>
              <dt class="text-neutral-500">Target stock</dt><dd>{{ detailRow.target_stock_units }}</dd>
              <dt class="text-neutral-500">Next breach week</dt><dd>{{ detailRow.next_breach_week_start ?? '—' }}</dd>
              <dt class="text-neutral-500">Recommended order week</dt><dd>{{ detailRow.recommended_order_week_start ?? '—' }}</dd>
              <dt class="text-neutral-500">Recommended order qty</dt><dd>{{ detailRow.recommended_order_qty }}</dd>
              <dt class="text-neutral-500">Projected qty at arrival</dt><dd>{{ detailRow.projected_qty_at_arrival ?? '—' }}</dd>
            </dl>
          </section>

          <section>
            <h4 class="text-xs font-medium text-neutral-600 uppercase tracking-wide mb-1">Rolling 12 weeks</h4>
            <div class="overflow-x-auto max-h-[40vh] overflow-y-auto">
              <table class="w-full text-xs border-collapse">
                <thead class="bg-neutral-50 border-b border-neutral-200">
                  <tr>
                    <th class="px-2 py-1.5 text-left font-medium text-neutral-600">Week</th>
                    <th class="px-2 py-1.5 text-right font-medium text-neutral-600">Open</th>
                    <th class="px-2 py-1.5 text-right font-medium text-neutral-600">Receipts</th>
                    <th class="px-2 py-1.5 text-right font-medium text-neutral-600">Demand</th>
                    <th class="px-2 py-1.5 text-right font-medium text-neutral-600">Close</th>
                    <th class="px-2 py-1.5 text-right font-medium text-neutral-600">WOC</th>
                    <th class="px-2 py-1.5 text-right font-medium text-neutral-600">Order</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="w in rollingWeeks"
                    :key="w.week_start"
                    :class="[w.stockout && 'bg-red-50', 'border-b border-neutral-100']"
                  >
                    <td class="px-2 py-1.5">{{ w.week_start }}</td>
                    <td class="px-2 py-1.5 text-right">{{ w.opening_qty }}</td>
                    <td class="px-2 py-1.5 text-right">{{ w.receipts_qty }}</td>
                    <td class="px-2 py-1.5 text-right">{{ w.demand_qty }}</td>
                    <td class="px-2 py-1.5 text-right">{{ w.closing_qty }}</td>
                    <td class="px-2 py-1.5 text-right">{{ w.weeks_of_cover ?? '—' }}</td>
                    <td class="px-2 py-1.5 text-right">{{ w.planned_order_qty ?? '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p v-if="!rollingWeeks.length" class="text-xs text-neutral-500 py-2">No rolling data.</p>
          </section>
        </template>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePlanningStore } from '@/stores/planning'
import { useAdminStore } from '@/stores/admin'
import { useLayoutStore } from '@/stores/layout'
import type { StockPositionBreakdown } from '@/api/client'
import { fetchPlanningReadiness, formatPlanRunLabel, planRunPlanningMode } from '@/api/client'
import PageHeader from '@/components/console/PageHeader.vue'
import FilterBar from '@/components/console/FilterBar.vue'
import NoDataWithReason from '@/components/console/NoDataWithReason.vue'
import PageHelpPanel from '@/components/console/PageHelpPanel.vue'

const route = useRoute()
const router = useRouter()
const store = usePlanningStore()
const adminStore = useAdminStore()
const layout = useLayoutStore()
const planRunId = ref<number | null>(null)
const warehouseFilter = ref('')
const productFamilyFilter = ref('')
const breachOnly = ref(false)
const search = ref('')
const loading = ref(false)
const breakdown = ref<StockPositionBreakdown[]>([])
const detailRow = ref<StockPositionBreakdown | null>(null)
const detailLoading = ref(false)
const rollingWeeks = ref<{ week_start: string; opening_qty: string; receipts_qty: string; demand_qty: string; closing_qty: string; weeks_of_cover: number | null; stockout: boolean; planned_order_qty: string | null }[]>([])
const demandInputsForDetail = ref<{ week_start: string; sku: string; warehouse_code: string; demand_qty: number; source: string; demand_breakdown_json: Record<string, unknown> | null; demand_includes_samples: boolean }[]>([])

const planRuns = computed(() => store.planRuns)
const selectedRun = computed(() => planRunId.value ? planRuns.value.find((r) => r.id === planRunId.value) : null)
const isDemandOnlyRun = computed(
  () => selectedRun.value != null && planRunPlanningMode(selectedRun.value) === 'demand_only'
)
const planningModeLabel = computed(() => (isDemandOnlyRun.value ? 'Demand-only' : 'Stock-aware'))
const syntheticStartingInventory = computed(() => {
  const meta = selectedRun.value?.progress_meta as { synthetic_starting_inventory?: boolean } | undefined
  return meta?.synthetic_starting_inventory === true
})
const selectedRunSkippedWarehouses = computed(() => {
  const meta = selectedRun.value?.progress_meta as { warehouses_skipped?: string[] } | undefined
  return meta?.warehouses_skipped ?? []
})
const warehouses = computed(() => adminStore.warehouses)
const products = computed(() => adminStore.products)

const productFamilies = computed(() => {
  const set = new Set<string>()
  for (const p of products.value) {
    const fam = p.product_family
    if (fam) set.add(fam)
  }
  return Array.from(set).sort()
})

const hasActiveFilters = computed(
  () => !!planRunId.value || !!warehouseFilter.value || !!productFamilyFilter.value || breachOnly.value
)

function clearFilters() {
  planRunId.value = null
  warehouseFilter.value = ''
  productFamilyFilter.value = ''
  breachOnly.value = false
  search.value = ''
}

const displayRows = computed(() => {
  let list = breakdown.value
  const q = search.value.toLowerCase()
  if (q) list = list.filter((r) => r.sku.toLowerCase().includes(q) || r.warehouse_code.toLowerCase().includes(q))
  return list
})

const diagnosticsData = ref<Awaited<ReturnType<typeof fetchPlanningReadiness>> | null>(null)
const noDataTitle = computed(() => {
  if (!planRunId.value && store.planRuns.length) return 'No plan run selected'
  if (!planRunId.value) return 'No plan runs yet'
  return 'No breakdown for this plan run'
})
const noDataReasons = computed(() => {
  const d = diagnosticsData.value
  const meta = selectedRun.value?.progress_meta as { warehouses_planned_detail?: Array<{ warehouse_code: string; overlap_pairs_count?: number }>; skipped_warehouses_detail?: Array<{ warehouse_code: string; blockers: string[] }> } | undefined
  const reasons: string[] = d ? d.blockers.map((b) => b.message) : ['Loading diagnostics…']
  if (meta?.skipped_warehouses_detail?.length) {
    for (const s of meta.skipped_warehouses_detail) {
      reasons.push(`${s.warehouse_code} skipped: ${s.blockers.join('; ')}`)
    }
  }
  const planned = meta?.warehouses_planned_detail ?? []
  const runDemandOnly =
    selectedRun.value != null && planRunPlanningMode(selectedRun.value) === 'demand_only'
  if (planned.length && planned.every((p) => (p.overlap_pairs_count ?? 0) === 0)) {
    reasons.push(
      runDemandOnly
        ? 'No overlapping SKUs across demand and policies for planned warehouses (SOH overlap not required for demand-only).'
        : 'No overlapping SKUs in SOH, demand, and policies for planned warehouses.'
    )
  }
  return reasons
})
const noDataActions = computed(() => {
  const actions: { label: string; href: string }[] = []
  if (store.planRuns.length === 0) actions.push({ label: 'Run plan', href: '/' })
  const d = diagnosticsData.value
  if (d) {
    const seen = new Set<string>()
    for (const b of d.blockers) {
      if (!seen.has(b.action_href)) {
        seen.add(b.action_href)
        actions.push({ label: b.action_label, href: b.action_href })
      }
    }
  }
  return actions
})

async function load() {
  if (!planRunId.value) {
    breakdown.value = []
    return
  }
  loading.value = true
  try {
    breakdown.value = await store.fetchStockPositionBreakdown(planRunId.value, {
      warehouseCode: warehouseFilter.value || undefined,
      productFamily: productFamilyFilter.value || undefined,
      breachOnly: breachOnly.value,
    })
  } finally {
    loading.value = false
  }
}

function getBreakdownIncluded(b: Record<string, unknown> | null | undefined): string {
  if (!b) return ''
  const inc = b.included
  return Array.isArray(inc) ? (inc as string[]).join(', ') : ''
}
function getBreakdownExcluded(b: Record<string, unknown> | null | undefined): string {
  if (!b) return ''
  const exc = b.excluded
  return Array.isArray(exc) ? (exc as string[]).join(', ') : ''
}

function openDetail(row: StockPositionBreakdown) {
  detailRow.value = row
  rollingWeeks.value = []
  demandInputsForDetail.value = []
  if (!planRunId.value) return
  layout.openRightPanel(`Stock position: ${row.sku} × ${row.warehouse_code}`)

  detailLoading.value = true
  Promise.all([
    store.fetchStockPositionRolling(planRunId.value, row.warehouse_code, row.sku, 12),
    store.fetchDemandInputs(planRunId.value),
  ])
    .then(([rollingData, demandRows]) => {
      rollingWeeks.value = rollingData
      demandInputsForDetail.value = demandRows.filter(
        (d) => d.sku === row.sku && d.warehouse_code === row.warehouse_code
      )
    })
    .finally(() => {
      detailLoading.value = false
    })
}

function planningReadinessParam(runId: number | null | undefined): 'stock_aware' | 'demand_only' {
  if (runId == null) return 'stock_aware'
  const r = store.planRuns.find((x) => x.id === runId)
  return r != null && planRunPlanningMode(r) === 'demand_only' ? 'demand_only' : 'stock_aware'
}

watch([planRunId, warehouseFilter, productFamilyFilter, breachOnly], load, { immediate: true })

watch(
  () => ({ loading: loading.value, rows: displayRows.value.length, runId: planRunId.value }),
  async ({ loading: ld, rows, runId }) => {
    if (!ld && rows === 0) {
      diagnosticsData.value = await fetchPlanningReadiness(runId ?? undefined, planningReadinessParam(runId ?? null))
    } else {
      diagnosticsData.value = null
    }
  },
  { immediate: true }
)

onMounted(async () => {
  await Promise.all([store.fetchPlanRuns(), adminStore.fetchProducts(), adminStore.fetchWarehouses()])
  const q = route.query.plan_run_id
  if (typeof q === 'string' && q) {
    const id = parseInt(q, 10)
    if (!isNaN(id) && store.planRuns.some((r) => r.id === id)) planRunId.value = id
  }
  if (planRunId.value == null && store.planRuns.length) {
    planRunId.value = store.planRuns[0].id
    router.replace({ path: route.path, query: { ...route.query, plan_run_id: String(store.planRuns[0].id) } })
  }
})
</script>

<style scoped>
.stock-position-detail {
  padding: 0.5rem 0;
  font-size: 0.875rem;
}
.stock-position-detail dl dt {
  font-weight: 500;
}
.page-header :deep(.mb-6) {
  margin-bottom: 0;
}
</style>
