<template>
  <div class="page-content-inner">
    <h1 class="text-xl font-semibold text-slate-800 mb-1">Scenario Manager</h1>
    <p class="muted mb-6">Freeze runs, recalculate demand, pin forecast runs, compare scenarios, and view forecast health (WAPE).</p>

    <section v-if="loading" class="content-section">Loading…</section>
    <template v-else>
      <section class="content-section">
        <h2>Plan run actions</h2>
        <p class="text-sm text-slate-600 mb-3">Select a run to freeze, recalculate demand, or change its forecast run.</p>
        <select v-model="selectedRunId" class="app-select" style="max-width: 24rem; margin-bottom: 0.75rem;">
          <option :value="null">Select scenario</option>
          <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ formatPlanRunLabel(r) }}</option>
        </select>
        <div v-if="selectedRunId" class="actions-row">
          <div v-if="actionMessage" class="action-message">{{ actionMessage }}</div>
          <button type="button" @click="doFreeze" class="app-btn app-btn-secondary" title="Lock demand and/or orders for the freeze window.">Freeze now</button>
          <select v-model="freezeScope" class="app-select" style="max-width: 8rem;" title="What to freeze: both, demand only, or orders only.">
            <option value="both">Demand &amp; orders</option>
            <option value="demand">Demand only</option>
            <option value="orders">Orders only</option>
          </select>
          <button type="button" @click="doRecalculateDemand" class="app-btn app-btn-secondary" title="Recompute demand for weeks outside the freeze window.">Recalculate (non-frozen demand)</button>
          <template v-if="selectedRun && (selectedRun.demand_source === 'baseline' || selectedRun.demand_source === 'blended')">
            <label class="form-label">Forecast run (optional)</label>
            <select
              :value="forecastRunPickerValue"
              @change="onForecastRunChange(($event.target as HTMLSelectElement).value)"
              class="app-select"
              style="max-width: 14rem;"
              :disabled="forecastRunsLoading"
            >
              <option value="">Latest available (auto)</option>
              <option v-for="opt in forecastRunOptions" :key="opt.train_end_week_start" :value="opt.train_end_week_start">
                {{ opt.train_end_week_start }} ({{ opt.count_rows }} rows)
              </option>
            </select>
            <button
              v-if="selectedRun.selected_train_end_week_start"
              type="button"
              @click="doResetForecastRun"
              class="app-btn app-btn-secondary"
              :disabled="resetForecastRunLoading"
            >
              Reset to latest
            </button>
          </template>
        </div>
        <p v-if="selectedRun && (selectedRun.demand_source === 'baseline' || selectedRun.demand_source === 'blended')" class="muted helper-text mt-2">
          If unset, the next recalc uses the latest available run and pins it.
        </p>
      </section>

      <section class="content-section">
        <h2>Compare scenarios</h2>
        <p class="muted mb-3">Compare exception counts between two runs (within 26 weeks).</p>
        <div class="compare-controls">
          <div class="form-row">
            <label class="form-label">Scenario A</label>
            <select v-model="compareRunA" class="app-select" style="max-width: 18rem;">
              <option :value="null">Select</option>
              <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ formatPlanRunLabel(r) }}</option>
            </select>
          </div>
          <div class="form-row">
            <label class="form-label">Scenario B</label>
            <select v-model="compareRunB" class="app-select" style="max-width: 18rem;">
              <option :value="null">Select</option>
              <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ formatPlanRunLabel(r) }}</option>
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

      <section class="content-section forecast-health-card">
        <h2>Forecast health</h2>
        <p class="muted mb-3">WAPE/Bias over last 12 weeks with actuals. Use POST /api/forecast/metrics/recompute to refresh.</p>
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

      <section class="content-section">
        <h2>Plan runs</h2>
        <div class="app-table-wrap">
          <table class="app-table">
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Demand source</th>
                <th>Forecast run</th>
                <th>Forecast method</th>
                <th>Freeze weeks</th>
                <th>Run at</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in planRuns" :key="r.id" :class="{ 'row-selected': selectedRunId === r.id }" @click="selectedRunId = r.id">
                <td>{{ formatPlanRunLabel(r) }}</td>
                <td>{{ r.demand_source ?? 'actuals' }}</td>
                <td class="text-muted">
                  {{ (r.demand_source === 'baseline' || r.demand_source === 'blended') && r.selected_train_end_week_start ? `Using: ${r.selected_train_end_week_start}` : '—' }}
                </td>
                <td>
                  <router-link v-if="r.demand_source === 'baseline' || r.demand_source === 'blended'" to="/admin/forecast-methods" class="forecast-method-badge" @click.stop>
                    {{ methodVersion }}
                    <span v-if="needsAcknowledgement(r)" class="ack-warning" title="Method not acknowledged">⚠</span>
                  </router-link>
                  <span v-else class="text-muted">—</span>
                </td>
                <td>{{ r.freeze_weeks ?? 4 }}</td>
                <td>{{ r.run_at }}</td>
                <td>{{ r.created_at }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import api from '@/api/client'
import { usePlanningStore } from '@/stores/planning'
import type { ForecastRunOption, PlanningException } from '@/api/client'
import { formatPlanRunLabel } from '@/api/client'

interface ForecastMetric {
  model_name: string
  model_version: string
  train_end_week_start: string
  sku: string
  warehouse_code: string
  eval_weeks?: number | null
  wape: number | null
  bias: number | null
}

interface ForecastMetricsSummary {
  avg_wape: number | null
  avg_bias: number | null
  count_scored: number
  count_missing: number
}

const store = usePlanningStore()
const loading = ref(true)
const selectedRunId = ref<number | null>(null)
const compareRunA = ref<number | null>(null)
const compareRunB = ref<number | null>(null)
const exceptionsA = ref<PlanningException[]>([])
const exceptionsB = ref<PlanningException[]>([])
const freezeScope = ref<'demand' | 'orders' | 'both'>('both')
const forecastRunOptions = ref<ForecastRunOption[]>([])
const forecastRunsLoading = ref(false)
const resetForecastRunLoading = ref(false)
const actionMessage = ref('')
const methodVersion = ref('—')
const methodAcknowledgements = ref<{ method_version: string }[]>([])
const forecastMetrics = ref<ForecastMetric[]>([])
const forecastSummary = ref<ForecastMetricsSummary>({
  avg_wape: null,
  avg_bias: null,
  count_scored: 0,
  count_missing: 0,
})
const forecastMetricsLoading = ref(false)

const planRuns = computed(() => store.planRuns)
const selectedRun = computed(() => planRuns.value.find((r) => r.id === selectedRunId.value) ?? null)
const forecastRunPickerValue = computed(() => selectedRun.value?.baseline_train_end_week_start ?? '')
const runAName = computed(() => {
  const r = planRuns.value.find((r) => r.id === compareRunA.value)
  return r ? formatPlanRunLabel(r) : '—'
})
const runBName = computed(() => {
  const r = planRuns.value.find((r) => r.id === compareRunB.value)
  return r ? formatPlanRunLabel(r) : '—'
})
const summary = computed(() => forecastSummary.value)
const top5WorstByWape = computed(() =>
  forecastMetrics.value
    .filter((m) => m.wape != null)
    .sort((a, b) => (b.wape ?? 0) - (a.wape ?? 0))
    .slice(0, 5)
)

function setActionMessage(msg: string) {
  actionMessage.value = msg
  setTimeout(() => { actionMessage.value = '' }, 4000)
}

function needsAcknowledgement(r: { demand_source?: string }) {
  if (r.demand_source !== 'baseline' && r.demand_source !== 'blended') return false
  return methodAcknowledgements.value.length === 0
}

async function loadForecastMethodsMeta() {
  try {
    const docRes = await api.get<{ method_version: string }>('/admin/forecast-methods')
    methodVersion.value = docRes.data.method_version ?? '—'
    const version = docRes.data.method_version
    if (version) {
      const ackRes = await api.get<{ method_version: string }[]>('/admin/forecast-methods/acknowledgements', { params: { method_version: version } })
      methodAcknowledgements.value = Array.isArray(ackRes.data) ? ackRes.data : []
    } else {
      methodAcknowledgements.value = []
    }
  } catch {
    methodVersion.value = '—'
    methodAcknowledgements.value = []
  }
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

async function doFreeze() {
  if (!selectedRunId.value) return
  await store.freezePlanRun(selectedRunId.value, freezeScope.value)
  await store.fetchPlanRuns()
  setActionMessage('Freeze applied.')
}

async function doRecalculateDemand() {
  if (!selectedRunId.value) return
  await store.recalculateDemand(selectedRunId.value)
  await store.fetchPlanRuns()
  setActionMessage('Demand recalculated.')
}

async function onForecastRunChange(value: string) {
  if (!selectedRunId.value) return
  const val = value.trim() || null
  try {
    await store.updatePlanRunBaseline(selectedRunId.value, val)
    await store.fetchPlanRuns()
    setActionMessage('Forecast run updated.')
  } catch (err: unknown) {
    const msg = err && typeof err === 'object' && 'response' in err && typeof (err as { response?: { data?: { detail?: string } } }).response?.data?.detail === 'string'
      ? (err as { response: { data: { detail: string } } }).response.data.detail
      : 'Failed to update forecast run.'
    setActionMessage(msg)
  }
}

async function doResetForecastRun() {
  if (!selectedRunId.value) return
  resetForecastRunLoading.value = true
  try {
    await store.resetForecastRun(selectedRunId.value, false)
    await store.fetchPlanRuns()
    setActionMessage('Pinned forecast run cleared. Next recalc will use the latest available.')
  } finally {
    resetForecastRunLoading.value = false
  }
}

onMounted(async () => {
  await store.fetchPlanRuns()
  if (store.planRuns.length) selectedRunId.value = store.planRuns[0].id
  loadForecastMetrics()
  loadForecastMethodsMeta()
  loading.value = false
})

watch(selectedRunId, async (id) => {
  if (id) {
    const run = planRuns.value.find((r) => r.id === id)
    if (run && (run.demand_source === 'baseline' || run.demand_source === 'blended')) {
      forecastRunsLoading.value = true
      try {
        forecastRunOptions.value = await store.getForecastRuns('AAH')
      } finally {
        forecastRunsLoading.value = false
      }
    } else {
      forecastRunOptions.value = []
    }
  } else {
    forecastRunOptions.value = []
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
</script>

<style scoped>
.actions-row { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
.form-label { font-size: 0.875rem; margin-left: 0.5rem; margin-right: 0.25rem; }
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
.forecast-health-card .health-summary { display: flex; gap: 1.5rem; margin-bottom: 0.75rem; font-size: 0.875rem; }
.forecast-health-card .subsection { font-size: 0.9375rem; margin: 0.75rem 0 0.25rem; }
.action-message { font-size: 0.875rem; margin-bottom: 0.5rem; color: var(--success, green); }
.helper-text { font-size: 0.8125rem; }
.app-table tbody tr { cursor: pointer; }
.app-table tbody tr.row-selected { background: var(--border); }
.forecast-method-badge {
  font-size: 0.75rem;
  padding: 0.15rem 0.4rem;
  background: rgb(239 246 255);
  color: #1d4ed8;
  border-radius: 0.25rem;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
}
.forecast-method-badge:hover { background: rgb(219 234 254); }
.ack-warning { color: var(--warning, #b45309); font-size: 0.875rem; }
</style>
