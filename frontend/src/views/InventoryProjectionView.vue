<template>
  <div class="page-content-inner">
    <p class="muted">Table and chart by SKU/warehouse. Compare up to two scenarios.</p>

    <section class="content-section controls">
      <div class="form-row">
        <label class="form-label">Scenario 1</label>
        <select v-model="runId1" class="app-select" style="max-width: 18rem;">
          <option :value="null">—</option>
          <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
        </select>
      </div>
      <div class="form-row">
        <label class="form-label">Scenario 2</label>
        <select v-model="runId2" class="app-select" style="max-width: 18rem;">
          <option :value="null">—</option>
          <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
        </select>
      </div>
      <div class="form-row">
        <label class="form-label">SKU filter</label>
        <input v-model="skuFilter" class="app-input" placeholder="SKU" style="max-width: 10rem;" />
      </div>
      <div class="form-row">
        <label class="form-label">Warehouse filter</label>
        <input v-model="whFilter" class="app-input" placeholder="Warehouse" style="max-width: 10rem;" />
      </div>
    </section>

    <section v-if="loading" class="content-section">Loading...</section>
    <template v-else>
      <section class="content-section">
        <h2>Projected inventory (Scenario 1)</h2>
        <p class="muted">Click a row to open the explain-the-forecast panel.</p>
        <div v-if="data1.length" class="app-table-wrap">
          <table class="app-table">
            <thead>
              <tr>
                <th>Week start</th>
                <th>SKU</th>
                <th>Warehouse</th>
                <th>Projected qty</th>
                <th>Weeks of cover</th>
                <th>Stockout</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="r in data1"
                :key="`1-${r.id}`"
                :class="{ 'row-status-error': r.stockout }"
                class="row-clickable"
                role="button"
                tabindex="0"
                @click="openExplanation(runId1!, r)"
                @keydown.enter="openExplanation(runId1!, r)"
                @keydown.space.prevent="openExplanation(runId1!, r)"
              >
                <td>{{ r.week_start }}</td>
                <td>{{ r.sku }}</td>
                <td>{{ r.warehouse_code }}</td>
                <td>{{ r.projected_qty }}</td>
                <td>{{ r.weeks_of_cover ?? '—' }}</td>
                <td>{{ r.stockout ? 'Yes' : 'No' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="muted">No data. Select a scenario and run a plan if needed.</p>
      </section>

      <section class="content-section">
        <h2>Projected inventory (Scenario 2)</h2>
        <p class="muted">Click a row to open the explain-the-forecast panel.</p>
        <div v-if="data2.length" class="app-table-wrap">
          <table class="app-table">
            <thead>
              <tr>
                <th>Week start</th>
                <th>SKU</th>
                <th>Warehouse</th>
                <th>Projected qty</th>
                <th>Weeks of cover</th>
                <th>Stockout</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="r in data2"
                :key="`2-${r.id}`"
                :class="{ 'row-status-error': r.stockout }"
                class="row-clickable"
                role="button"
                tabindex="0"
                @click="runId2 && openExplanation(runId2, r)"
                @keydown.enter="runId2 && openExplanation(runId2, r)"
                @keydown.space.prevent="runId2 && openExplanation(runId2, r)"
              >
                <td>{{ r.week_start }}</td>
                <td>{{ r.sku }}</td>
                <td>{{ r.warehouse_code }}</td>
                <td>{{ r.projected_qty }}</td>
                <td>{{ r.weeks_of_cover ?? '—' }}</td>
                <td>{{ r.stockout ? 'Yes' : 'No' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="muted">No data.</p>
      </section>

      <section class="content-section chart-section">
        <h2>Projected qty over time (first SKU/WH in list)</h2>
        <div class="chart-container" ref="chartContainer">
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
import type { ProjectedInventory, SkuWeekExplanation } from '@/api/client'
import { Chart, registerables } from 'chart.js'

Chart.register(...registerables)

const store = usePlanningStore()
const layout = useLayoutStore()
const loading = ref(true)
const runId1 = ref<number | null>(null)
const runId2 = ref<number | null>(null)
const skuFilter = ref('')
const whFilter = ref('')
const data1 = ref<ProjectedInventory[]>([])
const data2 = ref<ProjectedInventory[]>([])
const chartCanvas = ref<HTMLCanvasElement | null>(null)
const chartContainer = ref<HTMLDivElement | null>(null)
const explanation = ref(false)
const explanationLoading = ref(false)
const explanationData = ref<SkuWeekExplanation | null>(null)
let chartInstance: Chart | null = null

const planRuns = computed(() => store.planRuns)

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
