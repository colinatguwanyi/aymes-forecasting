<template>
  <div class="page-shell layout-data-wide space-y-6">
    <header class="page-header">
      <h1>Weekly Planning Grid</h1>
      <p class="muted mt-1">SKU × Week matrix. Red = stockout, amber = low cover, green = healthy. Click a cell to open the explanation panel.</p>
      <p class="muted mt-2 text-sm leading-snug max-w-3xl">
        <strong>Colour semantics:</strong> amber (low cover) uses a <strong>fixed</strong> threshold — weeks of cover below <strong>{{ LOW_COVER_WEEKS }} weeks</strong> — for every SKU. That is <strong>not</strong> necessarily the same as each row’s policy <strong>target weeks</strong> (see the right-hand panel under Policy, and Target &amp; ROP where available).
      </p>
    </header>

    <PageHelpPanel page-key="WeeklyPlanningGrid" />

    <section v-if="selectedRunSkippedWarehouses.length" class="mb-4 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-sm">
      Some warehouses were skipped: {{ selectedRunSkippedWarehouses.join(', ') }}.
    </section>

    <!-- demand_only: grid colors are modeled ledger / synthetic anchor — not physical SOH (backend contract). -->
    <section v-if="selectedRunId && isDemandOnlyRun" class="mb-4 p-3 rounded-lg bg-sky-50 border border-sky-200 text-sky-900 text-sm">
      <strong>Demand-only run.</strong> This grid shows a modeled position (including synthetic starts where used), not warehouse on-hand. Red and amber cells describe the model, not a promise of real-world stockout.
    </section>

    <section class="card card-body">
      <h3 class="section-title mb-3">Filters</h3>
      <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
        <div>
          <label class="form-label">Scenario</label>
          <select v-model="selectedRunId" class="select w-full max-w-xs">
            <option :value="null">Select scenario</option>
            <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ formatPlanRunLabel(r) }}</option>
          </select>
        </div>
        <div>
          <label class="form-label">Warehouse</label>
          <input v-model="whFilter" class="input w-full max-w-xs" placeholder="Filter warehouse" />
        </div>
        <div>
          <label class="form-label">SKU</label>
          <input v-model="skuFilter" class="input w-full max-w-xs" placeholder="Filter SKU" />
        </div>
      </div>
    </section>

    <section class="card card-body">
      <h3 class="section-title mb-3">Planning grid</h3>
      <p class="text-sm text-slate-600 mb-3 leading-snug">
        Heatmap: amber if weeks of cover &lt; {{ LOW_COVER_WEEKS }} weeks (grid-wide fixed rule). Policy <strong>target weeks</strong> per SKU are in the explain panel, not in the cell colour rule.
      </p>
      <div v-if="loading" class="py-8 text-sm text-slate-500">Loading…</div>
      <template v-else>
        <div v-if="rows.length && weekColumns.length" class="grid-section">
          <div class="planning-grid-wrap">
            <table class="planning-grid">
              <thead>
                <tr>
                  <th class="sticky-col sticky-header week-header">SKU / Warehouse</th>
                  <th
                    v-for="week in weekColumns"
                    :key="week"
                    class="sticky-header week-header"
                  >{{ week }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in rows" :key="row.key">
                  <td class="sticky-col row-label">
                    <router-link
                      :to="{ path: '/sku-detail', query: selectedRunId ? { sku: row.sku, warehouse_code: row.warehouse_code, plan_run_id: String(selectedRunId) } : { sku: row.sku, warehouse_code: row.warehouse_code } }"
                      class="row-label-link"
                      @click.stop
                    >{{ row.sku }} / {{ row.warehouse_code }}</router-link>
                  </td>
                  <td
                    v-for="week in weekColumns"
                    :key="week"
                    :class="cellClass(row, week)"
                    class="grid-cell"
                    role="button"
                    tabindex="0"
                    @click="openExplanationForCell(row, week)"
                    @keydown.enter="openExplanationForCell(row, week)"
                    @keydown.space.prevent="openExplanationForCell(row, week)"
                  >{{ cellDisplay(row, week) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <NoDataWithReason
          v-else
          :title="noDataTitle"
          :reasons="noDataReasons"
          :actions="noDataActions"
        />
      </template>
    </section>

    <Teleport to="#right-panel-body">
      <div v-if="explanation" class="explanation-panel">
        <template v-if="explanationLoading">Loading…</template>
        <template v-else-if="explanationData">
          <div v-if="stockBreakdownLoading" class="muted text-sm mb-3">Loading target &amp; ROP (stock position breakdown)…</div>
          <div v-else-if="stockBreakdownRow" class="stock-target-snippet mb-3">
            <h3 class="explanation-heading">Target &amp; ROP (units)</h3>
            <p class="muted text-sm stock-target-snippet__note">
              These values come from the <strong>stock position breakdown</strong> logic (policy and planning parameters for this scenario), not from new calculations in this panel.
              They describe a planning view of target level and reorder point in units, using average weekly demand from this plan run’s demand inputs.
              <template v-if="isDemandOnlyRun">
                For this demand-only run, <strong>projected position</strong> in the week detail below is a <strong>modeled ledger</strong>, not warehouse on-hand truth (see banner on the grid); breakdown on-hand still reflects snapshots where present.
              </template>
            </p>
            <dl class="explanation-dl">
              <dt>Target stock (units)</dt><dd>{{ formatPlanningNumber(stockBreakdownRow.target_stock_units) }}</dd>
              <dt>Reorder point (units)</dt><dd>{{ formatPlanningNumber(stockBreakdownRow.reorder_point_units) }}</dd>
              <dt>Avg weekly demand</dt><dd>{{ formatPlanningNumber(stockBreakdownRow.avg_weekly_demand) }}</dd>
            </dl>
          </div>
          <p v-else class="muted text-sm mb-3">
            No stock position breakdown row for this SKU and warehouse in this run (the breakdown needs projected inventory for the pair).
          </p>
          <h3 class="explanation-heading">Week {{ explanationData.projection?.week_start }}</h3>
          <dl class="explanation-dl" v-if="explanationData.projection">
            <dt>Start qty</dt><dd>{{ formatPlanningNumber(explanationData.projection.start_qty) }}</dd>
            <dt>Receipts</dt><dd>{{ formatPlanningNumber(explanationData.projection.receipts_qty) }}</dd>
            <dt>Demand</dt><dd>{{ formatPlanningNumber(explanationData.projection.demand_qty) }}</dd>
            <dt>Projected qty</dt><dd>{{ formatPlanningNumber(explanationData.projection.projected_qty) }}</dd>
            <dt>Weeks of cover</dt><dd>{{ formatPlanningNumber(explanationData.projection.weeks_of_cover) }}</dd>
            <dt>Stockout</dt><dd>{{ explanationData.projection.stockout ? 'Yes' : 'No' }}</dd>
          </dl>
          <p class="muted text-sm mb-2 leading-snug">
            This grid colours amber when weeks of cover is below <strong>{{ LOW_COVER_WEEKS }} weeks</strong> (same fixed value for all SKUs). Your policy <strong>target weeks</strong> are listed below — they can differ.
          </p>
          <h3 class="explanation-heading">Policy</h3>
          <dl class="explanation-dl" v-if="explanationData.policy">
            <dt>Mode</dt><dd>{{ explanationData.policy.mode ?? '—' }}</dd>
            <dt>Target weeks</dt><dd>{{ explanationData.policy.target_weeks ?? '—' }}</dd>
            <dt>Safety stock weeks</dt><dd>{{ explanationData.policy.safety_stock_weeks ?? '—' }}</dd>
            <dt>Forecast window</dt><dd>{{ explanationData.policy.forecast_window_weeks ?? '—' }}</dd>
            <dt>Lead time (prod / slot / haul / putaway / padding)</dt>
            <dd>{{ [explanationData.policy.lead_time_production_weeks, explanationData.policy.lead_time_slot_wait_weeks, explanationData.policy.lead_time_haulage_weeks, explanationData.policy.lead_time_putaway_weeks, explanationData.policy.lead_time_padding_weeks].filter(Boolean).join(' / ') || '—' }}</dd>
          </dl>
          <p class="muted">Forecast method: {{ explanationData.forecast_method }}</p>
        </template>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLayoutStore } from '@/stores/layout'
import { usePlanningStore } from '@/stores/planning'
import type { ProjectedInventory, SkuWeekExplanation, StockPositionBreakdown } from '@/api/client'
import { fetchPlanningReadiness, formatPlanRunLabel, planRunPlanningMode } from '@/api/client'
import NoDataWithReason from '@/components/console/NoDataWithReason.vue'
import PageHelpPanel from '@/components/console/PageHelpPanel.vue'

const LOW_COVER_WEEKS = 2

const route = useRoute()
const router = useRouter()
const store = usePlanningStore()
const layout = useLayoutStore()
const loading = ref(true)
const selectedRunId = ref<number | null>(null)
const whFilter = ref('')
const skuFilter = ref('')
const projected = ref<ProjectedInventory[]>([])
const explanation = ref(false)
const explanationLoading = ref(false)
const explanationData = ref<SkuWeekExplanation | null>(null)
const stockBreakdownRow = ref<StockPositionBreakdown | null>(null)
const stockBreakdownLoading = ref(false)

const planRuns = computed(() => store.planRuns)
const selectedRun = computed(() => selectedRunId.value ? planRuns.value.find((r) => r.id === selectedRunId.value) : null)
const isDemandOnlyRun = computed(
  () => selectedRun.value != null && planRunPlanningMode(selectedRun.value) === 'demand_only'
)
const selectedRunSkippedWarehouses = computed(() => {
  const meta = selectedRun.value?.progress_meta as { warehouses_skipped?: string[] } | undefined
  return meta?.warehouses_skipped ?? []
})

const cellMap = computed(() => {
  const m = new Map<string, ProjectedInventory>()
  for (const p of projected.value) {
    m.set(`${p.sku}|${p.warehouse_code}|${p.week_start}`, p)
  }
  return m
})

const weekColumns = computed(() => {
  const weeks = new Set(projected.value.map((p) => p.week_start))
  return Array.from(weeks).sort()
})

const rows = computed(() => {
  const seen = new Map<string, { sku: string; warehouse_code: string }>()
  for (const p of projected.value) {
    const key = `${p.sku}|${p.warehouse_code}`
    if (!seen.has(key)) seen.set(key, { sku: p.sku, warehouse_code: p.warehouse_code })
  }
  return Array.from(seen.entries()).map(([key, { sku, warehouse_code }]) => ({
    key,
    sku,
    warehouse_code,
  }))
})

const diagnosticsData = ref<Awaited<ReturnType<typeof fetchPlanningReadiness>> | null>(null)
const noDataTitle = computed(() => {
  if (!selectedRunId.value && store.planRuns.length) return 'No plan run selected'
  if (!selectedRunId.value) return 'No plan runs yet'
  return 'No data for this plan run'
})
const noDataReasons = computed(() => {
  const d = diagnosticsData.value
  const meta = selectedRun.value?.progress_meta as { warehouses_planned_detail?: Array<{ overlap_pairs_count?: number }>; skipped_warehouses_detail?: Array<{ warehouse_code: string; blockers: string[] }> } | undefined
  const reasons: string[] = d ? d.blockers.map((b) => b.message) : ['Loading diagnostics…']
  if (meta?.skipped_warehouses_detail?.length) {
    for (const s of meta.skipped_warehouses_detail) {
      reasons.push(`${s.warehouse_code} skipped: ${s.blockers.join('; ')}`)
    }
  }
  const planned = meta?.warehouses_planned_detail ?? []
  if (planned.length && planned.every((p) => (p.overlap_pairs_count ?? 0) === 0)) {
    reasons.push(
      isDemandOnlyRun.value
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

/** Format numeric API values (e.g. Decimal as "126.0000") for display: integers without trailing zeros; up to 2 decimals otherwise. */
function formatPlanningNumber(v: string | number | null | undefined): string {
  if (v == null || v === '') return '—'
  const n = typeof v === 'number' ? v : Number(String(v).trim().replace(/,/g, ''))
  if (Number.isNaN(n)) return String(v)
  if (Math.abs(n - Math.round(n)) < 1e-6) return String(Math.round(n))
  const r = Math.round(n * 100) / 100
  return String(r)
}

function cellClass(
  row: { sku: string; warehouse_code: string },
  week: string
): string[] {
  const p = cellMap.value.get(`${row.sku}|${row.warehouse_code}|${week}`)
  if (!p) return ['grid-cell']
  const c = ['grid-cell', 'cell-clickable']
  if (p.stockout) c.push('cell-status-error')
  else if (p.weeks_of_cover != null) {
    const woc = parseFloat(p.weeks_of_cover)
    if (woc < LOW_COVER_WEEKS) c.push('cell-status-warning')
    else c.push('cell-status-ok')
  } else c.push('cell-status-ok')
  return c
}

function cellDisplay(
  row: { sku: string; warehouse_code: string },
  week: string
): string {
  const p = cellMap.value.get(`${row.sku}|${row.warehouse_code}|${week}`)
  if (!p) return '—'
  return formatPlanningNumber(p.projected_qty)
}

async function openExplanationForCell(
  row: { sku: string; warehouse_code: string },
  week: string
) {
  if (!selectedRunId.value) return
  explanation.value = true
  explanationData.value = null
  stockBreakdownRow.value = null
  explanationLoading.value = true
  stockBreakdownLoading.value = true
  layout.openRightPanel(`Explain: ${row.sku} / ${row.warehouse_code} — ${week}`)
  try {
    const data = await store.fetchSkuWeekExplanation(
      selectedRunId.value,
      row.sku,
      row.warehouse_code,
      week
    )
    explanationData.value = data
  } finally {
    explanationLoading.value = false
  }
  try {
    const rows = await store.fetchStockPositionBreakdown(selectedRunId.value, {
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
  if (!selectedRunId.value) {
    projected.value = []
    return
  }
  loading.value = true
  try {
    projected.value = await store.fetchProjectedInventory(
      selectedRunId.value,
      skuFilter.value || undefined,
      whFilter.value || undefined
    )
  } finally {
    loading.value = false
  }
}

function planningReadinessParam(runId: number | null | undefined): 'stock_aware' | 'demand_only' {
  if (runId == null) return 'stock_aware'
  const r = store.planRuns.find((x) => x.id === runId)
  return r != null && planRunPlanningMode(r) === 'demand_only' ? 'demand_only' : 'stock_aware'
}

watch([selectedRunId, whFilter, skuFilter], load)
watch(
  () => ({ loading: loading.value, rowsLen: rows.value.length, runId: selectedRunId.value }),
  async ({ loading: ld, rowsLen, runId }) => {
    if (!ld && rowsLen === 0) {
      diagnosticsData.value = await fetchPlanningReadiness(runId ?? undefined, planningReadinessParam(runId ?? null))
    } else {
      diagnosticsData.value = null
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
      stockBreakdownRow.value = null
      stockBreakdownLoading.value = false
    }
  }
)
onMounted(async () => {
  await store.fetchPlanRuns()
  const q = route.query.plan_run_id
  if (typeof q === 'string' && q) {
    const id = parseInt(q, 10)
    if (!isNaN(id) && store.planRuns.some((r) => r.id === id)) selectedRunId.value = id
  }
  if (selectedRunId.value == null && store.planRuns.length) {
    selectedRunId.value = store.planRuns[0].id
    router.replace({ path: route.path, query: { ...route.query, plan_run_id: String(store.planRuns[0].id) } })
  }
  const skuQ = route.query.sku
  const whQ = route.query.warehouse_code
  if (typeof skuQ === 'string' && skuQ) skuFilter.value = skuQ
  if (typeof whQ === 'string' && whQ) whFilter.value = whQ
  loading.value = false
  await load()
})
</script>

<style scoped>
.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1.5rem;
  align-items: flex-end;
}
.form-row {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.form-label {
  font-size: 0.8125rem;
  color: var(--muted);
}
.grid-section {
  overflow: hidden;
}
.planning-grid-wrap {
  overflow: auto;
  max-height: min(70vh, 600px);
  border: 1px solid var(--border);
  width: 100%;
}
.planning-grid {
  table-layout: fixed;
  min-width: max-content;
  width: 100%;
}
.planning-grid .sticky-col {
  position: sticky;
  left: 0;
  z-index: 2;
  background: var(--main-bg);
  border-right: 1px solid var(--border);
  min-width: 140px;
  max-width: 180px;
}
.planning-grid .sticky-header {
  position: sticky;
  top: 0;
  z-index: 3;
  background: var(--main-bg);
}
.planning-grid .sticky-col.sticky-header {
  z-index: 4;
}
.planning-grid .week-header {
  min-width: 96px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.025em;
  color: var(--muted);
  white-space: nowrap;
  padding: 0.375rem 0.5rem;
}
.planning-grid .row-label {
  font-size: 0.8125rem;
}
.row-label-link {
  color: var(--accent);
  text-decoration: none;
}
.row-label-link:hover {
  text-decoration: underline;
}
.planning-grid .grid-cell {
  min-width: 64px;
  text-align: right;
  cursor: pointer;
}
.planning-grid .grid-cell.cell-clickable:hover {
  background: var(--hover);
}
.planning-grid .grid-cell.cell-status-error {
  background: rgba(153, 27, 27, 0.12);
  color: var(--error);
}
.planning-grid .grid-cell.cell-status-warning {
  background: rgba(180, 83, 9, 0.12);
  color: var(--warning);
}
.planning-grid .grid-cell.cell-status-ok {
  background: rgba(22, 101, 52, 0.08);
  color: var(--success);
}
.explanation-panel {
  font-size: 0.875rem;
}
.explanation-heading {
  font-size: 0.9375rem;
  font-weight: 500;
  margin: 0.75rem 0 0.25rem;
}
.explanation-dl {
  margin: 0;
}
.explanation-dl dt {
  font-weight: 500;
  color: var(--muted);
  margin-top: 0.35rem;
}
.explanation-dl dd {
  margin: 0 0 0 0.5rem;
}
.stock-target-snippet {
  padding: 0.75rem 1rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--main-bg);
}
.stock-target-snippet__note {
  margin: 0 0 0.5rem;
  line-height: 1.45;
}
.text-sm {
  font-size: 0.8125rem;
}
</style>
