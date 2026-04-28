<template>
  <div class="page-shell workflow-hub space-y-6">
    <header class="page-header workflow-hub__header">
      <div>
        <h1>Run Center</h1>
        <p class="muted mt-1">Run forecasts, check readiness, manage scenarios and export results.</p>
      </div>
      <button type="button" class="btn-secondary" :disabled="loadOperation.isRunning.value" @click="loadHub">
        Refresh
      </button>
    </header>

    <OperationStatusPanel :operation="loadOperation.operation" />

    <section class="run-banner" :class="forecastTone" role="status">
      <div>
        <p class="run-banner__label">Forecast status</p>
        <h2>{{ forecastCheck?.headline ?? 'Forecast check not loaded' }}</h2>
      </div>
      <span>{{ forecastStatusLabel }}</span>
    </section>

    <section class="workflow-summary-grid" aria-label="Run summary">
      <article class="workflow-summary-card">
        <span class="workflow-summary-card__label">Forecast runs</span>
        <strong>{{ formatInt(engineRuns.length) }}</strong>
        <p>{{ latestEngineRunLabel }}</p>
      </article>
      <article class="workflow-summary-card">
        <span class="workflow-summary-card__label">Planning runs</span>
        <strong>{{ formatInt(planRuns.length) }}</strong>
        <p>{{ latestPlanRunLabel }}</p>
      </article>
      <article class="workflow-summary-card" :class="forecastCheck?.forecast_run.status === 'green' ? 'is-ok' : 'is-warn'">
        <span class="workflow-summary-card__label">Latest forecast</span>
        <strong>{{ forecastCheck?.forecast_run.inference_date ?? 'None' }}</strong>
        <p>{{ forecastCheck?.forecast_run.message ?? 'No forecast run status available.' }}</p>
      </article>
      <article class="workflow-summary-card" :class="forecastCheck?.planning_alignment.status === 'green' ? 'is-ok' : 'is-warn'">
        <span class="workflow-summary-card__label">Plan alignment</span>
        <strong>{{ forecastCheck ? statusLabel(forecastCheck.planning_alignment.status) : 'Unknown' }}</strong>
        <p>{{ forecastCheck?.planning_alignment.message ?? 'No alignment check available.' }}</p>
      </article>
    </section>

    <section class="workflow-card-grid" aria-label="Run center actions">
      <router-link v-for="action in actions" :key="action.to" :to="action.to" class="workflow-action-card">
        <h2>{{ action.title }}</h2>
        <p>{{ action.description }}</p>
        <span>{{ action.cta }}</span>
      </router-link>
    </section>

    <section class="card card-body">
      <div class="flex items-center justify-between gap-3 mb-3">
        <h2 class="section-title m-0">Latest activity</h2>
        <router-link to="/forecast/runs" class="btn-secondary text-sm">Open forecast runs</router-link>
      </div>
      <div class="workflow-activity-grid">
        <div>
          <h3>Recent forecast engine runs</h3>
          <ul v-if="engineRuns.length" class="workflow-list">
            <li v-for="run in engineRuns.slice(0, 4)" :key="run.id">
              <span><strong>#{{ run.id }}</strong><small>{{ run.inference_date ?? 'No inference date' }}</small></span>
              <span :class="statusBadgeClass(runStatus(run))">{{ runStatus(run) }}</span>
            </li>
          </ul>
          <p v-else class="muted text-sm">No recent forecast runs.</p>
        </div>
        <div>
          <h3>Recent planning runs</h3>
          <ul v-if="planRuns.length" class="workflow-list">
            <li v-for="run in planRuns.slice(0, 4)" :key="run.id">
              <span><strong>{{ run.scenario_name }}</strong><small>{{ run.run_at }}</small></span>
              <router-link :to="{ path: '/planning-grid', query: { plan_run_id: String(run.id) } }">Open</router-link>
            </li>
          </ul>
          <p v-else class="muted text-sm">No planning runs yet.</p>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import api, {
  formatPlanRunLabel,
  type ForecastCheck,
  type ForecastCheckStatus,
  type PlanRun,
} from '@/api/client'
import OperationStatusPanel from '@/components/common/OperationStatusPanel.vue'
import { useOperation } from '@/composables/useOperation'

interface EngineRun {
  id: number
  status?: string | null
  run_status?: string | null
  inference_date: string | null
  created_at?: string | null
}

const forecastCheck = ref<ForecastCheck | null>(null)
const engineRuns = ref<EngineRun[]>([])
const planRuns = ref<PlanRun[]>([])
const loadOperation = useOperation('Load run center')

const actions = [
  { to: '/forecast/check', title: 'Check forecast readiness', description: 'Plain-English status on whether planners should trust the forecast.', cta: 'Open check' },
  { to: '/forecast/runs', title: 'Run forecast', description: 'Create and inspect forecast engine runs.', cta: 'Open forecast runs' },
  { to: '/forecast/dashboard', title: 'Forecast dashboard', description: 'Review latest published baseline context.', cta: 'Open dashboard' },
  { to: '/planning/scenario-manager', title: 'Scenario manager', description: 'Freeze, recalculate and align planning runs to forecast baselines.', cta: 'Open scenarios' },
  { to: '/forecast/scenarios', title: 'Forecast scenarios', description: 'Compare scenario context and plan run links.', cta: 'Open forecast scenarios' },
  { to: '/forecast/exports', title: 'Forecast exports', description: 'Generate forecast bundles and planning CSV outputs.', cta: 'Open exports' },
]

const forecastTone = computed(() => `run-banner--${forecastCheck.value?.overall_status ?? 'red'}`)
const forecastStatusLabel = computed(() => forecastCheck.value ? statusLabel(forecastCheck.value.overall_status) : 'Unknown')

const latestEngineRunLabel = computed(() => {
  const run = engineRuns.value[0]
  if (!run) return 'No recent runs'
  return `${runStatus(run)}${run.inference_date ? ` · ${run.inference_date}` : ''}`
})

const latestPlanRunLabel = computed(() => {
  const run = planRuns.value[0]
  return run ? formatPlanRunLabel(run) : 'No planning runs'
})

function formatInt(value: number): string {
  return Number.isFinite(value) ? value.toLocaleString() : String(value)
}

function statusLabel(status: ForecastCheckStatus): string {
  if (status === 'green') return 'OK'
  if (status === 'amber') return 'Warning'
  return 'Blocked'
}

function statusBadgeClass(status: string): string {
  const s = status.toLowerCase()
  if (s === 'success' || s === 'completed') return 'badge-success'
  if (s === 'failed') return 'badge-danger'
  if (s === 'running' || s === 'started') return 'badge-info'
  return 'badge-warn'
}

function runStatus(run: EngineRun): string {
  return run.status || run.run_status || 'unknown'
}

async function loadHub(): Promise<void> {
  await loadOperation.runWithOperation(
    'Load run center',
    async () => {
      const [checkRes, engineRes, planRes] = await Promise.allSettled([
        api.get<ForecastCheck>('/v1/forecast/check', { timeout: 10_000 }),
        api.get<EngineRun[]>('/v1/forecast/runs', { params: { limit: 10 }, timeout: 10_000 }),
        api.get<PlanRun[]>('/plan/runs', { timeout: 10_000 }),
      ])
      forecastCheck.value = checkRes.status === 'fulfilled' ? checkRes.value.data : null
      engineRuns.value = engineRes.status === 'fulfilled' && Array.isArray(engineRes.value.data) ? engineRes.value.data : []
      planRuns.value = planRes.status === 'fulfilled' && Array.isArray(planRes.value.data) ? planRes.value.data : []
    },
    {
      timeoutMs: 15_000,
      runningMessage: 'Loading run status...',
      successMessage: 'Run Center refreshed.',
    },
  )
}

onMounted(() => {
  void loadHub()
})
</script>

<style scoped>
.workflow-hub__header,
.run-banner {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}
.run-banner {
  border: 1px solid;
  border-radius: 1rem;
  padding: 1.25rem;
}
.run-banner h2 {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
}
.run-banner__label {
  margin: 0 0 0.25rem;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.run-banner span {
  border-radius: 999px;
  background: rgb(255 255 255 / 0.78);
  padding: 0.4rem 0.75rem;
  font-size: 0.875rem;
  font-weight: 700;
}
.run-banner--green {
  background: rgb(236 253 245);
  border-color: rgb(167 243 208);
  color: rgb(6 78 59);
}
.run-banner--amber {
  background: rgb(255 251 235);
  border-color: rgb(252 211 77);
  color: rgb(120 53 15);
}
.run-banner--red {
  background: rgb(254 242 242);
  border-color: rgb(252 165 165);
  color: rgb(127 29 29);
}
.workflow-summary-grid,
.workflow-card-grid,
.workflow-activity-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 1rem;
}
.workflow-summary-card,
.workflow-action-card {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.75rem;
  background: white;
  padding: 1rem;
}
.workflow-summary-card {
  border-left: 4px solid rgb(148 163 184);
}
.workflow-summary-card.is-ok {
  border-left-color: rgb(34 197 94);
  background: rgb(240 253 244);
}
.workflow-summary-card.is-warn {
  border-left-color: rgb(234 179 8);
  background: rgb(254 252 232);
}
.workflow-summary-card__label {
  display: block;
  color: rgb(100 116 139);
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.workflow-summary-card strong {
  display: block;
  margin-top: 0.35rem;
  color: rgb(15 23 42);
  font-size: 1.15rem;
}
.workflow-summary-card p,
.workflow-action-card p {
  margin: 0.35rem 0 0;
  color: rgb(71 85 105);
  font-size: 0.875rem;
}
.workflow-action-card {
  color: inherit;
  text-decoration: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.workflow-action-card:hover {
  border-color: rgb(147 197 253);
  box-shadow: 0 8px 20px rgb(15 23 42 / 0.08);
}
.workflow-action-card h2,
.workflow-activity-grid h3 {
  margin: 0;
  color: rgb(15 23 42);
  font-size: 1rem;
  font-weight: 700;
}
.workflow-action-card span {
  display: inline-block;
  margin-top: 0.75rem;
  color: rgb(37 99 235);
  font-size: 0.875rem;
  font-weight: 600;
}
.workflow-list {
  margin: 0.75rem 0 0;
  padding: 0;
  list-style: none;
}
.workflow-list li {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.65rem 0;
  border-top: 1px solid rgb(226 232 240);
}
.workflow-list small {
  display: block;
  color: rgb(100 116 139);
}
</style>
