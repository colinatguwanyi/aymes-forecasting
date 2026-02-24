<template>
  <div class="page-content-inner">
    <p class="muted">Stockout risk next 8 / 13 weeks and top SKUs by risk.</p>

    <section v-if="loading" class="content-section">Loading...</section>
    <template v-else>
      <section class="content-section">
        <h2>Run a scenario</h2>
        <form @submit.prevent="runScenario" class="form-inline plan-run-form">
          <input v-model="scenarioName" class="app-input" placeholder="Scenario name" required style="max-width: 12rem;" />
          <label class="form-label">Demand source</label>
          <select v-model="demandSource" class="app-select" style="max-width: 10rem;">
            <option value="actuals">Actuals</option>
            <option value="baseline">Baseline forecast</option>
            <option value="blended">Blended</option>
          </select>
          <label class="form-label">Freeze weeks</label>
          <input v-model.number="freezeWeeks" type="number" min="0" max="52" class="app-input" style="max-width: 4rem;" />
          <button type="submit" class="app-btn app-btn-primary">Run plan</button>
        </form>
      </section>

      <section v-if="selectedRunId" class="content-section">
        <h2>Plan run actions</h2>
        <p class="muted">Selected: {{ selectedRunName }}</p>
        <div class="actions-row">
          <button type="button" @click="doFreeze" class="app-btn app-btn-secondary">Freeze now</button>
          <select v-model="freezeScope" class="app-select" style="max-width: 8rem;">
            <option value="both">Demand &amp; orders</option>
            <option value="demand">Demand only</option>
            <option value="orders">Orders only</option>
          </select>
          <button type="button" @click="doRecalculateDemand" class="app-btn app-btn-secondary">Recalculate (non-frozen demand)</button>
        </div>
      </section>

      <section class="content-section">
        <h2>Stockout risk (next 8 weeks)</h2>
        <p v-if="!selectedRunId" class="muted">Select a scenario below to see risk.</p>
        <div v-else class="risk-summary">
          <p>Stockouts: {{ stockoutCount8 }}</p>
          <p>SKU/Warehouse combinations at risk: {{ atRiskSkus8.length }}</p>
        </div>
      </section>

      <section class="content-section">
        <h2>Stockout risk (next 13 weeks)</h2>
        <p v-if="!selectedRunId" class="muted">Select a scenario below.</p>
        <div v-else class="risk-summary">
          <p>Stockouts: {{ stockoutCount13 }}</p>
          <p>SKU/Warehouse at risk: {{ atRiskSkus13.length }}</p>
        </div>
      </section>

      <section class="content-section">
        <h2>Top SKUs by risk</h2>
        <select v-model="selectedRunId" class="app-select" style="max-width: 20rem; margin-bottom: 0.5rem;">
          <option :value="null">Select scenario</option>
          <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
        </select>
        <div v-if="selectedRunId && topRisks.length" class="app-table-wrap">
          <table class="app-table">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Warehouse</th>
                <th>Weeks at risk</th>
                <th>Min weeks of cover</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in topRisks" :key="i">
                <td>{{ row.sku }}</td>
                <td>{{ row.warehouse_code }}</td>
                <td>{{ row.stockoutWeeks }}</td>
                <td>{{ row.minWoc }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else-if="selectedRunId && !topRisks.length" class="muted">No stockout risk in projection.</p>
      </section>

      <section class="content-section">
        <h2>Compare scenarios</h2>
        <p class="muted">Compare exception counts between two runs (within 26 weeks).</p>
        <div class="compare-controls">
          <div class="form-row">
            <label class="form-label">Scenario A</label>
            <select v-model="compareRunA" class="app-select" style="max-width: 18rem;">
              <option :value="null">Select</option>
              <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
            </select>
          </div>
          <div class="form-row">
            <label class="form-label">Scenario B</label>
            <select v-model="compareRunB" class="app-select" style="max-width: 18rem;">
              <option :value="null">Select</option>
              <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
            </select>
          </div>
        </div>
        <div v-if="compareRunA && compareRunB" class="compare-summary">
          <div class="compare-card">
            <h3>{{ runAName }}</h3>
            <p>Stockouts: {{ exceptionsA.filter(e => e.type === 'stockout').length }}</p>
            <p>Low cover: {{ exceptionsA.filter(e => e.type === 'low_cover').length }}</p>
            <router-link :to="{ path: '/planning-grid', query: { plan_run_id: String(compareRunA) } }" class="app-btn">View in Planning Grid</router-link>
          </div>
          <div class="compare-card">
            <h3>{{ runBName }}</h3>
            <p>Stockouts: {{ exceptionsB.filter(e => e.type === 'stockout').length }}</p>
            <p>Low cover: {{ exceptionsB.filter(e => e.type === 'low_cover').length }}</p>
            <router-link :to="{ path: '/planning-grid', query: { plan_run_id: String(compareRunB) } }" class="app-btn">View in Planning Grid</router-link>
          </div>
        </div>
        <p v-else class="muted">Select two scenarios to compare.</p>
      </section>

      <section class="content-section">
        <h2>Plan runs</h2>
        <div class="app-table-wrap">
          <table class="app-table">
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Demand source</th>
                <th>Forecast run</th>
                <th>Freeze weeks</th>
                <th>Run at</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="r in planRuns"
                :key="r.id"
                :class="{ 'row-selected': selectedRunId === r.id }"
                @click="selectedRunId = r.id"
              >
                <td>{{ r.scenario_name }}</td>
                <td>{{ r.demand_source ?? 'actuals' }}</td>
                <td class="text-muted">
                  {{ (r.demand_source === 'baseline' || r.demand_source === 'blended') && r.selected_train_end_week_start ? `Using forecast run: ${r.selected_train_end_week_start}` : '—' }}
                </td>
                <td>{{ r.freeze_weeks ?? 4 }}</td>
                <td>{{ r.run_at }}</td>
                <td>{{ r.created_at }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="content-section forecast-health-card">
        <h2>Forecast health</h2>
        <p class="muted">WAPE/Bias over last 12 weeks with actuals. Use POST /api/forecast/metrics/recompute to refresh.</p>
        <div v-if="forecastMetricsLoading" class="muted">Loading…</div>
        <template v-else>
          <div class="health-summary">
            <span><strong>Avg WAPE:</strong> {{ summary.avg_wape != null ? (summary.avg_wape * 100).toFixed(2) + '%' : '—' }}</span>
            <span><strong>Scored:</strong> {{ summary.count_scored }}</span>
            <span><strong>Missing:</strong> {{ summary.count_missing }}</span>
          </div>
          <h3 class="subsection">Top 5 worst by WAPE</h3>
          <div v-if="top5WorstByWape.length" class="app-table-wrap">
            <table class="app-table">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Warehouse</th>
                  <th>Train end</th>
                  <th>WAPE</th>
                  <th>Bias</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(m, i) in top5WorstByWape" :key="i">
                  <td>{{ m.sku }}</td>
                  <td>{{ m.warehouse_code }}</td>
                  <td>{{ m.train_end_week_start }}</td>
                  <td>{{ m.wape != null ? (m.wape * 100).toFixed(2) + '%' : '—' }}</td>
                  <td>{{ m.bias != null ? m.bias.toFixed(4) : '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="muted">No scored metrics.</p>
        </template>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import api from '@/api/client'
import { usePlanningStore } from '@/stores/planning'
import type { ProjectedInventory, PlanningException } from '@/api/client'

export interface ForecastMetric {
  model_name: string
  model_version: string
  train_end_week_start: string
  sku: string
  warehouse_code: string
  eval_weeks?: number | null
  wape: number | null
  bias: number | null
}

export interface ForecastMetricsSummary {
  avg_wape: number | null
  avg_bias: number | null
  count_scored: number
  count_missing: number
}

const store = usePlanningStore()
const forecastMetrics = ref<ForecastMetric[]>([])
const forecastSummary = ref<ForecastMetricsSummary>({
  avg_wape: null,
  avg_bias: null,
  count_scored: 0,
  count_missing: 0,
})
const forecastMetricsLoading = ref(false)

const summary = computed(() => forecastSummary.value)
const top5WorstByWape = computed(() =>
  forecastMetrics.value
    .filter((m) => m.wape != null)
    .sort((a, b) => (b.wape ?? 0) - (a.wape ?? 0))
    .slice(0, 5)
)
const loading = ref(true)
const scenarioName = ref('baseline')
const demandSource = ref<'actuals' | 'baseline' | 'blended'>('actuals')
const freezeWeeks = ref(4)
const freezeScope = ref<'demand' | 'orders' | 'both'>('both')
const selectedRunId = ref<number | null>(null)
const compareRunA = ref<number | null>(null)
const compareRunB = ref<number | null>(null)
const exceptionsA = ref<PlanningException[]>([])
const exceptionsB = ref<PlanningException[]>([])

const planRuns = computed(() => store.planRuns)

const projected = ref<ProjectedInventory[]>([])
const weeks8 = 8
const weeks13 = 13

const distinctWeeks = computed(() => {
  const set = new Set(projected.value.map((p) => p.week_start))
  return Array.from(set).sort()
})
const first8Weeks = computed(() => distinctWeeks.value.slice(0, weeks8))
const first13Weeks = computed(() => distinctWeeks.value.slice(0, weeks13))

const stockoutCount8 = computed(() =>
  projected.value.filter((p) => p.stockout && first8Weeks.value.includes(p.week_start)).length
)
const stockoutCount13 = computed(() =>
  projected.value.filter((p) => p.stockout && first13Weeks.value.includes(p.week_start)).length
)

const atRiskSkus8 = computed(() => {
  const set = new Set<string>()
  projected.value
    .filter((p) => p.stockout && first8Weeks.value.includes(p.week_start))
    .forEach((p) => set.add(`${p.sku}|${p.warehouse_code}`))
  return Array.from(set)
})
const atRiskSkus13 = computed(() => {
  const set = new Set<string>()
  projected.value
    .filter((p) => p.stockout && first13Weeks.value.includes(p.week_start))
    .forEach((p) => set.add(`${p.sku}|${p.warehouse_code}`))
  return Array.from(set)
})

const topRisks = computed(() => {
  const byKey: Record<string, { sku: string; warehouse_code: string; stockoutWeeks: number; minWoc: number }> = {}
  for (const p of projected.value) {
    const key = `${p.sku}|${p.warehouse_code}`
    if (!byKey[key]) {
      byKey[key] = { sku: p.sku, warehouse_code: p.warehouse_code, stockoutWeeks: 0, minWoc: 999 }
    }
    if (p.stockout) byKey[key].stockoutWeeks++
    const woc = p.weeks_of_cover ? parseFloat(p.weeks_of_cover) : 999
    if (woc < byKey[key].minWoc) byKey[key].minWoc = woc
  }
  return Object.values(byKey)
    .filter((x) => x.stockoutWeeks > 0)
    .sort((a, b) => b.stockoutWeeks - a.stockoutWeeks)
    .slice(0, 20)
})

const runAName = computed(() => planRuns.value.find((r) => r.id === compareRunA.value)?.scenario_name ?? '—')
const runBName = computed(() => planRuns.value.find((r) => r.id === compareRunB.value)?.scenario_name ?? '—')
const selectedRunName = computed(() => planRuns.value.find((r) => r.id === selectedRunId.value)?.scenario_name ?? '—')

async function runScenario() {
  await store.runPlan(scenarioName.value, undefined, demandSource.value, freezeWeeks.value)
  await store.fetchPlanRuns()
  if (store.planRuns.length) selectedRunId.value = store.planRuns[0].id
}

async function loadForecastMetrics() {
  forecastMetricsLoading.value = true
  try {
    const [metricsRes, summaryRes] = await Promise.all([
      api.get<ForecastMetric[]>('/forecast/metrics', { params: { limit: 500 } }),
      api.get<ForecastMetricsSummary>('/forecast/metrics/summary'),
    ])
    forecastMetrics.value = metricsRes.data
    forecastSummary.value = summaryRes.data
  } finally {
    forecastMetricsLoading.value = false
  }
}

onMounted(async () => {
  await store.fetchPlanRuns()
  if (store.planRuns.length) selectedRunId.value = store.planRuns[0].id
  loadForecastMetrics()
  loading.value = false
})

watch(selectedRunId, async (id) => {
  if (id) {
    projected.value = await store.fetchProjectedInventory(id)
  } else {
    projected.value = []
  }
}, { immediate: true })

watch(compareRunA, async (id) => {
  if (id) exceptionsA.value = await store.fetchExceptions(id, 26, true)
  else exceptionsA.value = []
})
watch(compareRunB, async (id) => {
  if (id) exceptionsB.value = await store.fetchExceptions(id, 26, true)
  else exceptionsB.value = []
})

async function doFreeze() {
  if (!selectedRunId.value) return
  await store.freezePlanRun(selectedRunId.value, freezeScope.value)
  await store.fetchPlanRuns()
}

async function doRecalculateDemand() {
  if (!selectedRunId.value) return
  await store.recalculateDemand(selectedRunId.value)
  if (selectedRunId.value) projected.value = await store.fetchProjectedInventory(selectedRunId.value)
}
</script>

<style scoped>
.form-inline { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
.risk-summary p { margin: 0.25rem 0; font-size: 0.875rem; }
.compare-controls { display: flex; flex-wrap: wrap; gap: 1rem 1.5rem; margin-bottom: 0.75rem; }
.compare-summary { display: flex; gap: 1.5rem; flex-wrap: wrap; }
.compare-card {
  min-width: 200px;
  padding: 1rem;
  border: 1px solid var(--border);
  background: var(--main-bg);
}
.compare-card h3 { font-size: 0.9375rem; margin-bottom: 0.5rem; }
.compare-card p { margin: 0.25rem 0; font-size: 0.875rem; }
.compare-card .app-btn { margin-top: 0.5rem; text-decoration: none; display: inline-block; }
.plan-run-form .form-label { margin-left: 0.5rem; margin-right: 0.25rem; }
.actions-row { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
.form-label { font-size: 0.875rem; }
.app-table tbody tr { cursor: pointer; }
.app-table tbody tr.row-selected { background: var(--border); }
.forecast-health-card .health-summary { display: flex; gap: 1.5rem; margin-bottom: 0.75rem; font-size: 0.875rem; }
.forecast-health-card .subsection { font-size: 0.9375rem; margin: 0.75rem 0 0.25rem; }
</style>
