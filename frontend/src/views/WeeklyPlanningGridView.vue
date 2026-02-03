<template>
  <div class="page-content-inner">
    <p class="muted">SKU × Week matrix. Red = stockout, amber = low cover, green = healthy. Click a cell to open the explanation panel.</p>

    <section class="content-section controls">
      <div class="form-row">
        <label class="form-label">Scenario</label>
        <select v-model="selectedRunId" class="app-select" style="max-width: 18rem;">
          <option :value="null">Select scenario</option>
          <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
        </select>
      </div>
      <div class="form-row">
        <label class="form-label">Warehouse</label>
        <input v-model="whFilter" class="app-input" placeholder="Filter warehouse" style="max-width: 10rem;" />
      </div>
      <div class="form-row">
        <label class="form-label">SKU</label>
        <input v-model="skuFilter" class="app-input" placeholder="Filter SKU" style="max-width: 10rem;" />
      </div>
    </section>

    <section v-if="loading" class="content-section">Loading...</section>
    <template v-else>
      <section class="content-section grid-section">
        <div v-if="rows.length && weekColumns.length" class="planning-grid-wrap">
          <table class="planning-grid app-table">
            <thead>
              <tr>
                <th class="sticky-col sticky-header">SKU / Warehouse</th>
                <th
                  v-for="week in weekColumns"
                  :key="week"
                  class="sticky-header week-header"
                >{{ week }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.key">
                <td class="sticky-col row-label">{{ row.sku }} / {{ row.warehouse_code }}</td>
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
        <p v-else class="muted">No data. Select a scenario and run a plan, or adjust filters.</p>
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
import { useLayoutStore } from '@/stores/layout'
import { usePlanningStore } from '@/stores/planning'
import type { ProjectedInventory, SkuWeekExplanation } from '@/api/client'

const LOW_COVER_WEEKS = 2

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

const planRuns = computed(() => store.planRuns)

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
  return p.projected_qty
}

async function openExplanationForCell(
  row: { sku: string; warehouse_code: string },
  week: string
) {
  if (!selectedRunId.value) return
  explanation.value = true
  explanationData.value = null
  explanationLoading.value = true
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

watch([selectedRunId, whFilter, skuFilter], load)
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
  await store.fetchPlanRuns()
  if (store.planRuns.length) selectedRunId.value = store.planRuns[0].id
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
}
.planning-grid {
  table-layout: fixed;
  min-width: max-content;
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
  white-space: nowrap;
}
.planning-grid .row-label {
  font-size: 0.8125rem;
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
</style>
