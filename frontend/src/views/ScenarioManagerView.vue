<template>
  <div class="page-content-inner">
    <h1 class="text-xl font-semibold text-slate-800 mb-1">Scenario Manager</h1>
    <p class="muted mb-6">Freeze runs, recalculate demand, pin forecast runs, compare scenarios, and view forecast health (WAPE).</p>

    <PageHelpPanel page-key="ScenarioManager" />

    <section v-if="loading" class="content-section">Loading…</section>
    <template v-else>
      <section class="content-section">
        <h2>Plan run actions</h2>
        <p class="text-sm text-slate-600 mb-3">Select a run to freeze, recalculate demand, or change its forecast run.</p>
        <select v-model="selectedRunId" class="app-select" style="max-width: 24rem; margin-bottom: 0.75rem;">
          <option :value="null">Select scenario</option>
          <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ formatPlanRunLabel(r) }}</option>
        </select>
        <div v-if="selectedRunId && selectedRunIsDemandOnly" class="scenario-demand-note mb-3">
          <strong>Demand-only run selected.</strong> Coverage-based exceptions (e.g. stockout/low cover lists) are not used for this mode. Use the planning grid and SKU detail for modeled position — do not read “no exceptions” as proof of physical stock health.
        </div>
        <div v-if="selectedRunId" class="actions-row">
          <button type="button" @click="doFreeze" class="app-btn app-btn-secondary" :disabled="planActionBusy" title="Lock demand and/or orders for the freeze window.">Freeze now</button>
          <select v-model="freezeScope" class="app-select" style="max-width: 8rem;" title="What to freeze: both, demand only, or orders only.">
            <option value="both">Demand &amp; orders</option>
            <option value="demand">Demand only</option>
            <option value="orders">Orders only</option>
          </select>
          <button type="button" @click="doRecalculateDemand" class="app-btn app-btn-secondary" :disabled="planActionBusy" title="Recompute demand for weeks outside the freeze window.">Recalculate (non-frozen demand)</button>
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
              {{ resetForecastRunLoading ? 'Resetting…' : 'Reset to latest' }}
            </button>
          </template>
        </div>
        <OperationStatusPanel :operation="planActionOperation.operation" class="mt-3" />
        <p v-if="selectedRun && (selectedRun.demand_source === 'baseline' || selectedRun.demand_source === 'blended')" class="muted helper-text mt-2">
          If unset, the next recalc uses the latest available run and pins it.
        </p>
      </section>

      <section class="content-section">
        <h2>Compare scenarios</h2>
        <p class="muted mb-3">
          Compare exception counts between two runs (within 26 weeks). Counts reflect <strong>stock-aware</strong> coverage rules only.
          For <strong>demand-only</strong> runs, counts are shown as N/A — that means exceptions are <strong>not used</strong> for that mode, <strong>not</strong> that the scenario has zero risk or “better” coverage outcomes.
        </p>
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
        <div v-if="compareRunA && compareRunB && compareHasAnyDemandOnly" class="scenario-demand-note mb-3">
          <strong>Demand-only in this comparison.</strong> N/A for stockouts/low cover does <strong>not</strong> mean a safer plan — those exception types are suppressed for demand-only runs, not demonstrated to be absent.
        </div>
        <div v-if="compareRunA && compareRunB && crossModeCompareWarning" class="compare-mode-warning">
          <strong>Mixed planning modes.</strong> These two runs use different rules (stock-aware vs demand-only). Exception counts and grid behavior are not directly comparable; do not rank scenarios using N/A as if it were zero.
        </div>
        <div v-if="compareRunA && compareRunB" class="compare-summary">
          <div class="compare-card">
            <h3>{{ runAName }}</h3>
            <p v-if="compareModeA === 'demand_only'" class="compare-exception-na">Stockouts: N/A — exceptions not used for demand-only</p>
            <p v-else>Stockouts: {{ exceptionsA.filter(e => e.type === 'stockout').length }}</p>
            <p v-if="compareModeA === 'demand_only'" class="compare-exception-na">Low cover: N/A — exceptions not used for demand-only</p>
            <p v-else>Low cover: {{ exceptionsA.filter(e => e.type === 'low_cover').length }}</p>
            <p v-if="compareModeA === 'demand_only'" class="compare-exception-footnote">N/A is not “zero issues”; use the grid for modeled signals.</p>
            <router-link :to="{ path: '/planning-grid', query: { plan_run_id: String(compareRunA) } }" class="app-btn">View in Planning Grid</router-link>
          </div>
          <div class="compare-card">
            <h3>{{ runBName }}</h3>
            <p v-if="compareModeB === 'demand_only'" class="compare-exception-na">Stockouts: N/A — exceptions not used for demand-only</p>
            <p v-else>Stockouts: {{ exceptionsB.filter(e => e.type === 'stockout').length }}</p>
            <p v-if="compareModeB === 'demand_only'" class="compare-exception-na">Low cover: N/A — exceptions not used for demand-only</p>
            <p v-else>Low cover: {{ exceptionsB.filter(e => e.type === 'low_cover').length }}</p>
            <p v-if="compareModeB === 'demand_only'" class="compare-exception-footnote">N/A is not “zero issues”; use the grid for modeled signals.</p>
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
import { formatPlanRunLabel, planRunPlanningMode } from '@/api/client'
import PageHelpPanel from '@/components/console/PageHelpPanel.vue'
import OperationStatusPanel from '@/components/common/OperationStatusPanel.vue'
import { useOperation } from '@/composables/useOperation'

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
const planActionOperation = useOperation('Scenario action')
const planActionBusy = planActionOperation.isRunning
const resetForecastRunLoading = planActionOperation.isRunning
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
const compareRunAData = computed(() => planRuns.value.find((r) => r.id === compareRunA.value) ?? null)
const compareRunBData = computed(() => planRuns.value.find((r) => r.id === compareRunB.value) ?? null)
const compareModeA = computed(() => (compareRunAData.value ? planRunPlanningMode(compareRunAData.value) : null))
const compareModeB = computed(() => (compareRunBData.value ? planRunPlanningMode(compareRunBData.value) : null))
const crossModeCompareWarning = computed(
  () =>
    compareRunA.value != null &&
    compareRunB.value != null &&
    compareModeA.value != null &&
    compareModeB.value != null &&
    compareModeA.value !== compareModeB.value,
)
const selectedRunIsDemandOnly = computed(
  () => selectedRun.value != null && planRunPlanningMode(selectedRun.value) === 'demand_only',
)
const compareHasAnyDemandOnly = computed(
  () =>
    compareRunA.value != null &&
    compareRunB.value != null &&
    (compareModeA.value === 'demand_only' || compareModeB.value === 'demand_only'),
)
const summary = computed(() => forecastSummary.value)
const top5WorstByWape = computed(() =>
  forecastMetrics.value
    .filter((m) => m.wape != null)
    .sort((a, b) => (b.wape ?? 0) - (a.wape ?? 0))
    .slice(0, 5)
)

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
  const result = await planActionOperation.runWithOperation(
    'Freeze plan run',
    async () => {
      await store.freezePlanRun(selectedRunId.value!, freezeScope.value)
      return true
    },
    {
      runningMessage: 'Applying freeze...',
      successMessage: 'Freeze applied.',
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh plan runs before retrying.',
      nextActions: ['Refresh plan runs before retrying.'],
    },
  )
  if (!result) return
  await store.fetchPlanRuns()
}

async function doRecalculateDemand() {
  if (!selectedRunId.value) return
  const result = await planActionOperation.runWithOperation(
    'Recalculate demand',
    async () => {
      await store.recalculateDemand(selectedRunId.value!)
      return true
    },
    {
      runningMessage: 'Recalculating non-frozen demand...',
      successMessage: 'Demand recalculated.',
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh plan runs before retrying.',
      nextActions: ['Refresh plan runs before retrying.'],
    },
  )
  if (!result) return
  await store.fetchPlanRuns()
}

async function onForecastRunChange(value: string) {
  if (!selectedRunId.value) return
  const val = value.trim() || null
  const result = await planActionOperation.runWithOperation(
    'Update forecast run',
    async () => {
      try {
        await store.updatePlanRunBaseline(selectedRunId.value!, val)
        return true
      } catch (err: unknown) {
        const msg = err && typeof err === 'object' && 'response' in err && typeof (err as { response?: { data?: { detail?: string } } }).response?.data?.detail === 'string'
          ? (err as { response: { data: { detail: string } } }).response.data.detail
          : 'Failed to update forecast run.'
        throw new Error(msg)
      }
    },
    {
      runningMessage: 'Updating forecast run selection...',
      successMessage: 'Forecast run updated.',
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh plan runs before retrying.',
      nextActions: ['Refresh plan runs before retrying.'],
    },
  )
  if (!result) return
  await store.fetchPlanRuns()
}

async function doResetForecastRun() {
  if (!selectedRunId.value) return
  const result = await planActionOperation.runWithOperation(
    'Reset forecast run',
    async () => {
      await store.resetForecastRun(selectedRunId.value!, false)
      return true
    },
    {
      runningMessage: 'Clearing pinned forecast run...',
      successMessage: 'Pinned forecast run cleared. Next recalc will use the latest available.',
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh plan runs before retrying.',
      nextActions: ['Refresh plan runs before retrying.'],
    },
  )
  if (!result) return
  await store.fetchPlanRuns()
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
.compare-mode-warning {
  margin-bottom: 0.75rem;
  padding: 0.75rem 1rem;
  font-size: 0.875rem;
  border: 1px solid rgb(253 230 138);
  background: rgb(255 251 235);
  color: rgb(120 53 15);
}
.compare-exception-na { color: var(--text-muted, #64748b); font-style: italic; }
.compare-exception-footnote { font-size: 0.75rem; color: var(--text-muted, #64748b); margin: 0.35rem 0 0; line-height: 1.35; }
.scenario-demand-note {
  padding: 0.75rem 1rem;
  font-size: 0.875rem;
  line-height: 1.45;
  border: 1px solid rgb(186 230 253);
  background: rgb(240 249 255);
  color: rgb(12 74 110);
  border-radius: 6px;
}
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
