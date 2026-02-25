<template>
  <div class="space-y-4">
    <PageHeader title="Inventory Projection" :breadcrumbs="[{ label: 'Planning', path: '/' }]">
      <template #actions>
        <button type="button" class="px-4 py-2 text-sm font-medium text-neutral-700 bg-white border border-neutral-300 rounded-lg hover:bg-neutral-50" @click="exportCsv" title="Export Scenario 1 data to CSV">Export CSV</button>
      </template>
    </PageHeader>

    <section v-if="!loading && !planRuns.length" class="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-amber-800">
      <strong>No plan runs yet.</strong> Go to the <router-link to="/" class="font-medium underline hover:no-underline">Dashboard</router-link>, run a plan (Scenario + Demand source + Run plan), then return here to select it and view projections.
    </section>

    <section v-else-if="!loading && planRuns.length && !runId1" class="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-blue-800">
      <strong>Select a plan run</strong> from the dropdown above. Plan runs are created on the <router-link to="/" class="font-medium underline hover:no-underline">Dashboard</router-link>.
    </section>

    <section v-if="selectedRunSkippedWarehouses.length" class="mb-4 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-sm">
      Some warehouses were skipped: {{ selectedRunSkippedWarehouses.join(', ') }}.
    </section>

    <FilterBar v-model="search" search-placeholder="Search SKU or warehouse…" :has-active-filters="hasActiveFilters" @clear="runId1 = null; runId2 = null; skuFilter = ''; whFilter = ''; stockoutOnly = false; search = ''">
      <template #filters>
        <select v-model="runId1" class="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white min-w-48" title="Select a plan run to view its projected inventory. Created on the Dashboard.">
          <option :value="null">Plan run 1 — select</option>
          <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ formatPlanRunLabel(r) }}</option>
        </select>
        <select v-model="runId2" class="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white min-w-48" title="Optional: select a second run to compare side by side.">
          <option :value="null">Plan run 2 — optional</option>
          <option v-for="r in planRuns" :key="'2-' + r.id" :value="r.id">{{ formatPlanRunLabel(r) }}</option>
        </select>
        <select v-model="skuFilter" class="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white min-w-40" title="Filter to a specific SKU.">
          <option value="">All SKUs</option>
          <option v-for="p in products" :key="p.id" :value="p.sku">{{ p.sku }}</option>
        </select>
        <select v-model="whFilter" class="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white min-w-40" title="Filter to a specific warehouse.">
          <option value="">All warehouses</option>
          <option v-for="w in warehouses" :key="w.id" :value="w.code">{{ w.code }}</option>
        </select>
        <label class="flex items-center gap-2 text-sm text-neutral-700" title="Show only rows where projected qty ≤ 0 (stockout).">
          <input v-model="stockoutOnly" type="checkbox" class="rounded border-neutral-300" />
          Stockout only
        </label>
      </template>
    </FilterBar>

    <section v-if="loading" class="text-sm text-neutral-500 py-8">Loading…</section>
    <template v-else>
      <section class="border border-neutral-200 rounded-lg bg-white overflow-hidden">
        <h2 class="px-4 py-3 text-sm font-medium text-neutral-700 border-b border-neutral-200">Projected inventory (Scenario 1)</h2>
        <p class="px-4 py-1 text-xs text-neutral-500">Click a row to open the explain-the-forecast panel.</p>
        <div v-if="displayData1.length" class="overflow-x-auto max-h-[50vh] overflow-y-auto">
          <table class="w-full text-sm border-collapse">
            <thead class="sticky top-0 bg-neutral-50 border-b border-neutral-200">
              <tr>
                <th class="px-3 py-2 text-left font-medium text-neutral-600">Week start</th>
                <th class="px-3 py-2 text-left font-medium text-neutral-600">SKU</th>
                <th class="px-3 py-2 text-left font-medium text-neutral-600">Warehouse</th>
                <th class="px-3 py-2 text-left font-medium text-neutral-600">Projected qty</th>
                <th class="px-3 py-2 text-left font-medium text-neutral-600">Weeks of cover</th>
                <th class="px-3 py-2 text-left font-medium text-neutral-600">Stockout</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="r in displayData1"
                :key="`1-${r.id}`"
                :class="[r.stockout && 'bg-red-50', 'border-b border-neutral-100 hover:bg-neutral-50 cursor-pointer']"
                @click="openExplanation(runId1!, r)"
              >
                <td class="px-3 py-2">{{ r.week_start }}</td>
                <td class="px-3 py-2">{{ r.sku }}</td>
                <td class="px-3 py-2">{{ r.warehouse_code }}</td>
                <td class="px-3 py-2">{{ r.projected_qty }}</td>
                <td class="px-3 py-2">{{ r.weeks_of_cover ?? '—' }}</td>
                <td class="px-3 py-2">{{ r.stockout ? 'Yes' : 'No' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <NoDataWithReason
          v-else
          :title="noDataTitle1"
          :reasons="noDataReasons1"
          :actions="noDataActions1"
        />
      </section>

      <section class="border border-neutral-200 rounded-lg bg-white overflow-hidden">
        <h2 class="px-4 py-3 text-sm font-medium text-neutral-700 border-b border-neutral-200">Projected inventory (Scenario 2)</h2>
        <p class="px-4 py-1 text-xs text-neutral-500">Click a row to open the explain-the-forecast panel.</p>
        <div v-if="displayData2.length" class="overflow-x-auto max-h-[50vh] overflow-y-auto">
          <table class="w-full text-sm border-collapse">
            <thead class="sticky top-0 bg-neutral-50 border-b border-neutral-200">
              <tr>
                <th class="px-3 py-2 text-left font-medium text-neutral-600">Week start</th>
                <th class="px-3 py-2 text-left font-medium text-neutral-600">SKU</th>
                <th class="px-3 py-2 text-left font-medium text-neutral-600">Warehouse</th>
                <th class="px-3 py-2 text-left font-medium text-neutral-600">Projected qty</th>
                <th class="px-3 py-2 text-left font-medium text-neutral-600">Weeks of cover</th>
                <th class="px-3 py-2 text-left font-medium text-neutral-600">Stockout</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="r in displayData2"
                :key="`2-${r.id}`"
                :class="[r.stockout && 'bg-red-50', 'border-b border-neutral-100 hover:bg-neutral-50 cursor-pointer']"
                @click="runId2 && openExplanation(runId2, r)"
              >
                <td class="px-3 py-2">{{ r.week_start }}</td>
                <td class="px-3 py-2">{{ r.sku }}</td>
                <td class="px-3 py-2">{{ r.warehouse_code }}</td>
                <td class="px-3 py-2">{{ r.projected_qty }}</td>
                <td class="px-3 py-2">{{ r.weeks_of_cover ?? '—' }}</td>
                <td class="px-3 py-2">{{ r.stockout ? 'Yes' : 'No' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <NoDataWithReason
          v-else
          :title="noDataTitle2"
          :reasons="noDataReasons2"
          :actions="noDataActions2"
        />
      </section>

      <section class="border border-neutral-200 rounded-lg bg-white overflow-hidden p-4">
        <h2 class="text-sm font-medium text-neutral-700 mb-2">Projected qty over time (first SKU/WH in list)</h2>
        <div class="chart-container min-h-[200px]" ref="chartContainer">
          <canvas ref="chartCanvas"></canvas>
        </div>
      </section>
    </template>

    <Teleport to="#right-panel-body">
      <div v-if="explanation" class="explanation-panel">
        <template v-if="explanationLoading">Loading…</template>
        <template v-else-if="explanationData">
          <h3 class="explanation-heading">Week {{ explanationData.projection?.week_start }}</h3>
          <dl class="explanation-dl" v-if="explanationData.projection">
            <dt>Start qty</dt><dd>{{ explanationData.projection.start_qty ?? '—' }}</dd>
            <dt>Receipts</dt><dd>{{ explanationData.projection.receipts_qty ?? '—' }}</dd>
            <dt>Demand</dt><dd>{{ explanationData.projection.demand_qty ?? '—' }}</dd>
            <dt>Projected qty</dt><dd>{{ explanationData.projection.projected_qty }}</dd>
            <dt>Weeks of cover</dt><dd>{{ explanationData.projection.weeks_of_cover ?? '—' }}</dd>
            <dt>Stockout</dt><dd>{{ explanationData.projection.stockout ? 'Yes' : 'No' }}</dd>
          </dl>
          <h3 class="explanation-heading">Policy</h3>
          <dl class="explanation-dl" v-if="explanationData.policy">
            <dt>Mode</dt><dd>{{ explanationData.policy.mode ?? '—' }}</dd>
            <dt>Target weeks</dt><dd>{{ explanationData.policy.target_weeks ?? '—' }}</dd>
            <dt>Safety stock weeks</dt><dd>{{ explanationData.policy.safety_stock_weeks ?? '—' }}</dd>
            <dt>Forecast window</dt><dd>{{ explanationData.policy.forecast_window_weeks ?? '—' }}</dd>
            <dt>Lead time (prod / slot / haul / putaway / padding)</dt>
            <dd>{{ [explanationData.policy.lead_time_production_weeks, explanationData.policy.lead_time_slot_wait_weeks, explanationData.policy.lead_time_haulage_weeks, explanationData.policy.lead_time_putaway_weeks, explanationData.policy.lead_time_padding_weeks].join(' / ') }}</dd>
          </dl>
          <p class="muted">Forecast method: {{ explanationData.forecast_method }}</p>
        </template>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useLayoutStore } from '@/stores/layout'
import { usePlanningStore } from '@/stores/planning'
import { useAdminStore } from '@/stores/admin'
import type { ProjectedInventory, SkuWeekExplanation } from '@/api/client'
import { formatPlanRunLabel, fetchPlanningReadiness } from '@/api/client'
import { Chart, registerables } from 'chart.js'
import PageHeader from '@/components/console/PageHeader.vue'
import FilterBar from '@/components/console/FilterBar.vue'
import NoDataWithReason from '@/components/console/NoDataWithReason.vue'

Chart.register(...registerables)

const store = usePlanningStore()
const adminStore = useAdminStore()
const layout = useLayoutStore()
const loading = ref(true)
const runId1 = ref<number | null>(null)
const runId2 = ref<number | null>(null)
const skuFilter = ref('')
const whFilter = ref('')
const search = ref('')
const stockoutOnly = ref(false)
const products = computed(() => adminStore.products)
const warehouses = computed(() => adminStore.warehouses)
const data1 = ref<ProjectedInventory[]>([])
const data2 = ref<ProjectedInventory[]>([])

const hasActiveFilters = computed(() => !!runId1.value || !!runId2.value || !!skuFilter.value || !!whFilter.value || stockoutOnly.value)

function filterBySearchAndStockout(list: ProjectedInventory[], q: string): ProjectedInventory[] {
  let out = list
  if (q) {
    const lower = q.toLowerCase()
    out = out.filter((r) => r.sku.toLowerCase().includes(lower) || r.warehouse_code.toLowerCase().includes(lower))
  }
  if (stockoutOnly.value) out = out.filter((r) => r.stockout)
  return out
}

const displayData1 = computed(() => filterBySearchAndStockout(data1.value, search.value))
const displayData2 = computed(() => filterBySearchAndStockout(data2.value, search.value))

const diagnostics1 = ref<Awaited<ReturnType<typeof fetchPlanningReadiness>> | null>(null)
const diagnostics2 = ref<Awaited<ReturnType<typeof fetchPlanningReadiness>> | null>(null)
const noDataTitle1 = computed(() => {
  if (!runId1.value && store.planRuns.length) return 'No plan run selected'
  if (!runId1.value) return 'No plan runs yet'
  return 'No projection rows for this run'
})
const noDataReasons1 = computed(() => {
  const d = diagnostics1.value
  if (!d) return ['Loading diagnostics…']
  return d.blockers.map((b) => b.message)
})
const noDataActions1 = computed(() => {
  const d = diagnostics1.value
  if (!d) return []
  const seen = new Set<string>()
  return d.blockers
    .filter((b) => !seen.has(b.action_href) && seen.add(b.action_href))
    .map((b) => ({ label: b.action_label, href: b.action_href }))
})
const noDataTitle2 = computed(() => {
  if (!runId2.value) return 'Optional: select Plan run 2 to compare'
  return 'No projection rows for this run and filters'
})
const noDataReasons2 = computed(() => {
  const d = diagnostics2.value
  if (!d) return []
  return d.blockers.map((b) => b.message)
})
const noDataActions2 = computed(() => {
  const d = diagnostics2.value
  if (!d) return []
  const seen = new Set<string>()
  return d.blockers
    .filter((b) => !seen.has(b.action_href) && seen.add(b.action_href))
    .map((b) => ({ label: b.action_label, href: b.action_href }))
})

function exportCsv() {
  const rows = [...displayData1.value]
  const headers = ['week_start', 'sku', 'warehouse_code', 'projected_qty', 'weeks_of_cover', 'stockout']
  const csv = [headers.join(','), ...rows.map((r) => [r.week_start, r.sku, r.warehouse_code, r.projected_qty, r.weeks_of_cover ?? '', r.stockout ? 'Yes' : 'No'].join(','))].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'projected_inventory_weekly.csv'
  a.click()
  URL.revokeObjectURL(a.href)
}
const chartCanvas = ref<HTMLCanvasElement | null>(null)
const chartContainer = ref<HTMLDivElement | null>(null)
const explanation = ref(false)
const explanationLoading = ref(false)
const explanationData = ref<SkuWeekExplanation | null>(null)
let chartInstance: Chart | null = null

const planRuns = computed(() => store.planRuns)
const selectedRun = computed(() => runId1.value ? planRuns.value.find((r) => r.id === runId1.value) : null)
const selectedRunSkippedWarehouses = computed(() => {
  const meta = selectedRun.value?.progress_meta as { warehouses_skipped?: string[] } | undefined
  return meta?.warehouses_skipped ?? []
})

async function openExplanation(planRunId: number, row: ProjectedInventory) {
  explanation.value = true
  explanationData.value = null
  explanationLoading.value = true
  layout.openRightPanel(`Explain: ${row.sku} / ${row.warehouse_code} — ${row.week_start}`)
  try {
    const data = await store.fetchSkuWeekExplanation(
      planRunId,
      row.sku,
      row.warehouse_code,
      row.week_start
    )
    explanationData.value = data
  } finally {
    explanationLoading.value = false
  }
}

async function load() {
  if (runId1.value) {
    data1.value = await store.fetchProjectedInventory(
      runId1.value,
      skuFilter.value || undefined,
      whFilter.value || undefined
    )
  } else {
    data1.value = []
  }
  if (runId2.value) {
    data2.value = await store.fetchProjectedInventory(
      runId2.value,
      skuFilter.value || undefined,
      whFilter.value || undefined
    )
  } else {
    data2.value = []
  }
  updateChart()
}

function updateChart() {
  if (!chartCanvas.value) return
  const firstKey = (arr: ProjectedInventory[]) => {
    if (!arr.length) return null
    const r = arr[0]
    return `${r.sku}|${r.warehouse_code}`
  }
  const key1 = firstKey(data1.value)
  const key2 = firstKey(data2.value)
  const series1 = key1 ? data1.value.filter((p) => `${p.sku}|${p.warehouse_code}` === key1) : []
  const series2 = key2 ? data2.value.filter((p) => `${p.sku}|${p.warehouse_code}` === key2) : []

  if (chartInstance) chartInstance.destroy()
  chartInstance = new Chart(chartCanvas.value, {
    type: 'line',
    data: {
      labels: series1.length ? series1.map((p) => p.week_start) : series2.map((p) => p.week_start),
      datasets: [
        { label: 'Scenario 1', data: series1.map((p) => parseFloat(p.projected_qty)), borderColor: 'var(--accent)', fill: false },
        { label: 'Scenario 2', data: series2.map((p) => parseFloat(p.projected_qty)), borderColor: 'var(--success)', fill: false },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: 'top' } },
      scales: { y: { beginAtZero: true } },
    },
  })
}

watch([runId1, runId2, skuFilter, whFilter], load)
watch(
  () => ({ len1: displayData1.value.length, run1: runId1.value }),
  async ({ len1, run1 }) => {
    if (len1 === 0) {
      diagnostics1.value = await fetchPlanningReadiness(run1 ?? undefined)
    } else {
      diagnostics1.value = null
    }
  },
  { immediate: true }
)
watch(
  () => ({ len2: displayData2.value.length, run2: runId2.value }),
  async ({ len2, run2 }) => {
    if (len2 === 0 && run2) {
      diagnostics2.value = await fetchPlanningReadiness(run2)
    } else {
      diagnostics2.value = null
    }
  },
  { immediate: true }
)
watch(
  () => layout.rightPanelOpen,
  (open) => {
    if (!open) {
      explanation.value = false
      explanationData.value = null
    }
  }
)
onMounted(async () => {
  await Promise.all([store.fetchPlanRuns(), adminStore.fetchProducts(), adminStore.fetchWarehouses()])
  if (store.planRuns.length) runId1.value = store.planRuns[0].id
  loading.value = false
  await load()
})
</script>

<style scoped>
.controls { display: flex; flex-wrap: wrap; gap: 0.75rem 1.5rem; align-items: flex-end; }
.form-row { display: flex; flex-direction: column; gap: 0.25rem; }
.form-label { font-size: 0.8125rem; color: var(--muted); }
.chart-container { max-width: 800px; height: 300px; }
.row-clickable { cursor: pointer; }
.row-clickable:hover { background: var(--hover); }
.explanation-panel { font-size: 0.875rem; }
.explanation-heading { font-size: 0.9375rem; font-weight: 500; margin: 0.75rem 0 0.25rem; }
.explanation-dl { margin: 0; }
.explanation-dl dt { font-weight: 500; color: var(--muted); margin-top: 0.35rem; }
.explanation-dl dd { margin: 0 0 0 0.5rem; }
</style>
