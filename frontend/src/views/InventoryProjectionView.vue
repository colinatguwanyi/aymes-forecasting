<template>
  <div class="layout-data-wide space-y-4 w-full inventory-projection-root">
    <PageHeader title="Inventory Projection" :breadcrumbs="[{ label: 'Planning', path: '/' }]">
      <template #actions>
        <button type="button" class="px-4 py-2 text-sm font-medium text-neutral-700 bg-white border border-neutral-300 rounded-lg hover:bg-neutral-50" @click="exportCsv" title="Export Scenario 1 data to CSV">Export CSV</button>
      </template>
    </PageHeader>

    <PageHelpPanel page-key="InventoryProjection" />

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
        <select
          v-model="skuFilter"
          class="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white min-w-56 max-w-[min(24rem,100%)]"
          title="SKUs from the selected plan output are listed first; remaining options are the product catalog."
        >
          <option value="">All SKUs</option>
          <template v-if="skusInLoadedProjection.length">
            <optgroup label="In selected plan output">
              <option
                v-for="s in skusInLoadedProjection"
                :key="'proj-' + s"
                :value="s"
              >{{ skuFilterOptionLabel(s) }}</option>
            </optgroup>
            <optgroup v-if="catalogSkusNotInProjection.length" label="Rest of product catalog">
              <option v-for="s in catalogSkusNotInProjection" :key="'cat-' + s" :value="s">{{ s }}</option>
            </optgroup>
          </template>
          <template v-else>
            <option v-for="s in catalogSkusSorted" :key="'all-' + s" :value="s">{{ s }}</option>
          </template>
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

    <section v-if="runId1 && isDemandOnlyRun1" class="mb-4 p-3 rounded-lg bg-sky-50 border border-sky-200 text-sky-900 text-sm">
      <strong>Plan run 1 is demand-only.</strong> Rows are a modeled ledger (not physical SOH). Red highlighting is relative to that model.
    </section>
    <section v-if="runId2 && isDemandOnlyRun2" class="mb-4 p-3 rounded-lg bg-sky-50 border border-sky-200 text-sky-900 text-sm">
      <strong>Plan run 2 is demand-only.</strong> Same as run 1: modeled position, not warehouse stock truth.
    </section>
    <section v-if="crossModeComparisonWarning" class="mb-4 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 text-sm">
      <strong>Mixed planning modes.</strong> These two runs use different rules (stock-aware vs demand-only). Compare them carefully — the side-by-side view is not apples-to-apples for physical stock.
    </section>

    <section
      v-if="!loading && orphanSkusInProjection.length"
      class="mb-4 p-3 rounded-lg border border-amber-200 bg-amber-50 text-amber-900 text-sm"
    >
      <strong>SKU catalog mismatch.</strong> This plan output includes
      <span class="font-mono text-xs">{{ orphanSkusInProjection.join(', ') }}</span>,
      which {{ orphanSkusInProjection.length === 1 ? 'is' : 'are' }} not in the current product list loaded in the app. Rows may be from stale planning policies, deleted products, or another environment. Align
      <router-link to="/admin/policies" class="font-medium underline hover:no-underline">planning policies</router-link>
      and
      <router-link to="/admin/products" class="font-medium underline hover:no-underline">products</router-link>
      with your product master, or re-run the plan after cleanup.
    </section>

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
                <th class="px-3 py-2 text-right font-medium text-neutral-600">Projected qty</th>
                <th class="px-3 py-2 text-right font-medium text-neutral-600">Weeks of cover</th>
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
                <td class="px-3 py-2 tabular-nums">{{ r.week_start }}</td>
                <td class="px-3 py-2 font-mono text-xs">
                  <span :class="{ 'text-amber-800 bg-amber-100/80 rounded px-1 py-0.5': !isSkuInCatalog(r.sku) }">{{ r.sku }}</span>
                </td>
                <td class="px-3 py-2">{{ r.warehouse_code }}</td>
                <td class="px-3 py-2 text-right tabular-nums">{{ formatPlanQty(r.projected_qty) }}</td>
                <td class="px-3 py-2 text-right tabular-nums">{{ formatPlanWoc(r.weeks_of_cover) }}</td>
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
                <th class="px-3 py-2 text-right font-medium text-neutral-600">Projected qty</th>
                <th class="px-3 py-2 text-right font-medium text-neutral-600">Weeks of cover</th>
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
                <td class="px-3 py-2 tabular-nums">{{ r.week_start }}</td>
                <td class="px-3 py-2 font-mono text-xs">
                  <span :class="{ 'text-amber-800 bg-amber-100/80 rounded px-1 py-0.5': !isSkuInCatalog(r.sku) }">{{ r.sku }}</span>
                </td>
                <td class="px-3 py-2">{{ r.warehouse_code }}</td>
                <td class="px-3 py-2 text-right tabular-nums">{{ formatPlanQty(r.projected_qty) }}</td>
                <td class="px-3 py-2 text-right tabular-nums">{{ formatPlanWoc(r.weeks_of_cover) }}</td>
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
          <div v-if="stockBreakdownLoading" class="text-sm text-neutral-500 mb-3">Loading target &amp; ROP (stock position breakdown)…</div>
          <div v-else-if="stockBreakdownRow" class="stock-target-snippet mb-3">
            <h3 class="explanation-heading">Target &amp; ROP (units)</h3>
            <p class="text-sm text-neutral-600 stock-target-snippet__note">
              These values come from the <strong>stock position breakdown</strong> logic (policy and planning parameters for this scenario), not from new calculations in this panel.
              They describe a planning view of target level and reorder point in units, using average weekly demand from this plan run’s demand inputs.
              <template v-if="explanationDemandOnly">
                For this demand-only run, <strong>projected position</strong> in the week detail below is a <strong>modeled ledger</strong>, not warehouse on-hand truth (see the demand-only banner for this plan run above); breakdown on-hand still reflects snapshots where present.
              </template>
            </p>
            <dl class="explanation-dl">
              <dt>Target stock (units)</dt><dd>{{ formatPlanQty(stockBreakdownRow.target_stock_units) }}</dd>
              <dt>Reorder point (units)</dt><dd>{{ formatPlanQty(stockBreakdownRow.reorder_point_units) }}</dd>
              <dt>Avg weekly demand</dt><dd>{{ formatPlanQty(stockBreakdownRow.avg_weekly_demand) }}</dd>
            </dl>
          </div>
          <p v-else class="text-sm text-neutral-500 mb-3">
            No stock position breakdown row for this SKU and warehouse in this run (the breakdown needs projected inventory for the pair).
          </p>
          <h3 class="explanation-heading">Week {{ explanationData.projection?.week_start }}</h3>
          <dl class="explanation-dl" v-if="explanationData.projection">
            <dt>Start qty</dt><dd>{{ formatPlanQty(explanationData.projection.start_qty) }}</dd>
            <dt>Receipts</dt><dd>{{ formatPlanQty(explanationData.projection.receipts_qty) }}</dd>
            <dt>Demand</dt><dd>{{ formatPlanQty(explanationData.projection.demand_qty) }}</dd>
            <dt>Projected qty</dt><dd>{{ formatPlanQty(explanationData.projection.projected_qty) }}</dd>
            <dt>Weeks of cover</dt><dd>{{ formatPlanWoc(explanationData.projection.weeks_of_cover) }}</dd>
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
import { useRoute, useRouter } from 'vue-router'
import { useLayoutStore } from '@/stores/layout'
import { usePlanningStore } from '@/stores/planning'
import { useAdminStore } from '@/stores/admin'
import type { ProjectedInventory, SkuWeekExplanation, StockPositionBreakdown } from '@/api/client'
import { formatPlanRunLabel, planRunPlanningMode, fetchPlanningReadiness } from '@/api/client'
import { Chart, registerables } from 'chart.js'
import PageHeader from '@/components/console/PageHeader.vue'
import FilterBar from '@/components/console/FilterBar.vue'
import NoDataWithReason from '@/components/console/NoDataWithReason.vue'
import PageHelpPanel from '@/components/console/PageHelpPanel.vue'

Chart.register(...registerables)

const route = useRoute()
const router = useRouter()
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
const warehouses = computed(() => adminStore.warehouses)
const data1 = ref<ProjectedInventory[]>([])
const data2 = ref<ProjectedInventory[]>([])

const productSkuSet = computed(() => new Set(adminStore.products.map((p) => p.sku)))
const projectionSkuSet = computed(() => {
  const u = new Set<string>()
  data1.value.forEach((r) => u.add(r.sku))
  data2.value.forEach((r) => u.add(r.sku))
  return u
})
const skusInLoadedProjection = computed(() =>
  Array.from(projectionSkuSet.value).sort((a, b) => a.localeCompare(b)),
)
const catalogSkusNotInProjection = computed(() =>
  adminStore.products
    .map((p) => p.sku)
    .filter((s) => !projectionSkuSet.value.has(s))
    .sort((a, b) => a.localeCompare(b)),
)
const catalogSkusSorted = computed(() =>
  [...adminStore.products.map((p) => p.sku)].sort((a, b) => a.localeCompare(b)),
)
const orphanSkusInProjection = computed(() =>
  skusInLoadedProjection.value.filter((s) => !productSkuSet.value.has(s)),
)

function skuFilterOptionLabel(sku: string): string {
  return productSkuSet.value.has(sku) ? sku : `${sku} — not in catalog`
}

function isSkuInCatalog(sku: string): boolean {
  return productSkuSet.value.has(sku)
}

function formatPlanQty(v: string | number | null | undefined): string {
  if (v == null || v === '') return '—'
  const n = typeof v === 'number' ? v : Number(String(v).trim().replace(/,/g, ''))
  if (Number.isNaN(n)) return String(v)
  if (Math.abs(n - Math.round(n)) < 1e-6) return String(Math.round(n))
  return String(Math.round(n * 100) / 100)
}

function formatPlanWoc(v: string | number | null | undefined): string {
  if (v == null || v === '') return '—'
  const n = typeof v === 'number' ? v : Number(String(v).trim().replace(/,/g, ''))
  if (Number.isNaN(n)) return String(v)
  if (Math.abs(n - Math.round(n)) < 1e-6) return String(Math.round(n))
  return String(Math.round(n * 100) / 100)
}

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
  const run1 = runId1.value ? planRuns.value.find((r) => r.id === runId1.value) : null
  const meta = run1?.progress_meta as { warehouses_planned_detail?: Array<{ overlap_pairs_count?: number }>; skipped_warehouses_detail?: Array<{ warehouse_code: string; blockers: string[] }> } | undefined
  const reasons: string[] = d ? d.blockers.map((b) => b.message) : ['Loading diagnostics…']
  if (meta?.skipped_warehouses_detail?.length) {
    for (const s of meta.skipped_warehouses_detail) {
      reasons.push(`${s.warehouse_code} skipped: ${s.blockers.join('; ')}`)
    }
  }
  const planned = meta?.warehouses_planned_detail ?? []
  if (planned.length && planned.every((p) => (p.overlap_pairs_count ?? 0) === 0)) {
    reasons.push(
      isDemandOnlyRun1.value
        ? 'No overlapping SKUs across demand and policies for planned warehouses (SOH overlap not required for demand-only).'
        : 'No overlapping SKUs in SOH, demand, and policies for planned warehouses.'
    )
  }
  return reasons
})
const noDataActions1 = computed(() => {
  const actions: { label: string; href: string }[] = []
  if (store.planRuns.length === 0) actions.push({ label: 'Run plan', href: '/' })
  const d = diagnostics1.value
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
const explanationPlanRunId = ref<number | null>(null)
const stockBreakdownRow = ref<StockPositionBreakdown | null>(null)
const stockBreakdownLoading = ref(false)
let chartInstance: Chart | null = null

const planRuns = computed(() => store.planRuns)
const selectedRun = computed(() => runId1.value ? planRuns.value.find((r) => r.id === runId1.value) : null)
const run2Selected = computed(() => runId2.value ? planRuns.value.find((r) => r.id === runId2.value) ?? null : null)
const isDemandOnlyRun1 = computed(
  () => selectedRun.value != null && planRunPlanningMode(selectedRun.value) === 'demand_only'
)
const isDemandOnlyRun2 = computed(
  () => run2Selected.value != null && planRunPlanningMode(run2Selected.value) === 'demand_only'
)
const crossModeComparisonWarning = computed(() => {
  if (!runId1.value || !runId2.value || !selectedRun.value || !run2Selected.value) return false
  return planRunPlanningMode(selectedRun.value) !== planRunPlanningMode(run2Selected.value)
})
const explanationDemandOnly = computed(() => {
  const id = explanationPlanRunId.value
  if (id == null) return false
  const r = planRuns.value.find((x) => x.id === id)
  return r != null && planRunPlanningMode(r) === 'demand_only'
})
const selectedRunSkippedWarehouses = computed(() => {
  const meta = selectedRun.value?.progress_meta as { warehouses_skipped?: string[] } | undefined
  return meta?.warehouses_skipped ?? []
})

async function openExplanation(planRunId: number, row: ProjectedInventory) {
  explanationPlanRunId.value = planRunId
  explanation.value = true
  explanationData.value = null
  stockBreakdownRow.value = null
  explanationLoading.value = true
  stockBreakdownLoading.value = true
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
  try {
    const rows = await store.fetchStockPositionBreakdown(planRunId, {
      sku: row.sku,
      warehouseCode: row.warehouse_code,
      limit: 5,
    })
    stockBreakdownRow.value = rows[0] ?? null
  } catch {
    stockBreakdownRow.value = null
  } finally {
    stockBreakdownLoading.value = false
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

function planningReadinessParam(runId: number | null | undefined): 'stock_aware' | 'demand_only' {
  if (runId == null) return 'stock_aware'
  const r = store.planRuns.find((x) => x.id === runId)
  return r != null && planRunPlanningMode(r) === 'demand_only' ? 'demand_only' : 'stock_aware'
}

watch([runId1, runId2, skuFilter, whFilter], load)
watch(
  () => ({ len1: displayData1.value.length, run1: runId1.value }),
  async ({ len1, run1 }) => {
    if (len1 === 0) {
      diagnostics1.value = await fetchPlanningReadiness(run1 ?? undefined, planningReadinessParam(run1 ?? null))
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
      diagnostics2.value = await fetchPlanningReadiness(run2, planningReadinessParam(run2))
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
      explanationPlanRunId.value = null
      stockBreakdownRow.value = null
      stockBreakdownLoading.value = false
    }
  }
)
onMounted(async () => {
  await Promise.all([store.fetchPlanRuns(), adminStore.fetchProducts(), adminStore.fetchWarehouses()])
  const q = route.query.plan_run_id
  if (typeof q === 'string' && q) {
    const id = parseInt(q, 10)
    if (!isNaN(id) && store.planRuns.some((r) => r.id === id)) runId1.value = id
  }
  if (runId1.value == null && store.planRuns.length) {
    runId1.value = store.planRuns[0].id
    router.replace({ path: route.path, query: { ...route.query, plan_run_id: String(store.planRuns[0].id) } })
  }
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
.stock-target-snippet {
  padding: 0.75rem 1rem;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 6px;
  background: var(--main-bg, #fff);
}
.stock-target-snippet__note { margin: 0 0 0.5rem; line-height: 1.45; }
</style>
