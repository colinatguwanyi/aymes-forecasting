<template>
  <div class="page-shell space-y-6">
    <header class="page-header">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1>Run forecast</h1>
          <p class="muted mt-1 max-w-3xl m-0">
            A <strong>forecast run</strong> is one batch job in the MySQL forecast engine: it fixes an inference (as-of) date and horizon,
            fits or applies the configured models, and writes scored weekly outputs you can inspect, validate, and export.
            This page lists recent engine runs and their status; create, execute, and deep-dive results live in Forecast Settings.
          </p>
        </div>
        <router-link to="/admin/forecast-engine" class="btn-primary whitespace-nowrap shrink-0 self-start">
          Open Forecast Settings
        </router-link>
      </div>
    </header>

    <section v-if="runsLoading" class="card card-body">
      <p class="muted m-0">Loading forecast runs…</p>
    </section>

    <section v-else-if="loadError" class="card card-body border-amber-200 bg-amber-50/50">
      <p class="text-sm text-slate-800 font-medium m-0 mb-1">Could not load engine runs</p>
      <p class="text-sm text-slate-600 m-0">{{ loadError }}</p>
      <p class="muted text-sm mt-2 mb-3 m-0">
        If the forecast database is offline or unset, runs will not appear here. You can still open Forecast Settings to check configuration.
      </p>
      <div class="flex flex-wrap gap-2">
        <router-link to="/admin/forecast-engine" class="btn-primary">Forecast Settings</router-link>
        <button type="button" class="btn-secondary" @click="loadRuns">Retry</button>
      </div>
    </section>

    <template v-else>
      <section class="card card-body" aria-labelledby="latest-status-heading">
        <h2 id="latest-status-heading" class="text-base font-medium text-slate-800 mb-3">Latest run status</h2>
        <template v-if="latestRun">
          <div class="latest-summary-grid text-sm">
            <div>
              <dt class="text-slate-500 font-normal m-0">Run</dt>
              <dd class="m-0 mt-0.5 font-medium text-slate-900 font-mono">#{{ latestRun.id }} · {{ shortUuid(latestRun.run_uuid) }}</dd>
            </div>
            <div>
              <dt class="text-slate-500 font-normal m-0">Status</dt>
              <dd class="m-0 mt-0.5">
                <span :class="statusBadgeClass(latestRun.run_status)">{{ latestRun.run_status }}</span>
              </dd>
            </div>
            <div v-if="isFailedRunStatus(latestRun.run_status)">
              <dt class="text-slate-500 font-normal m-0">Fail note</dt>
              <dd class="m-0 mt-0.5">
                <span
                  v-if="hasRecordedFailReason(latestRun)"
                  class="inline-block text-xs font-semibold px-1.5 py-0.5 rounded bg-sky-100 text-sky-800"
                  :title="String(latestRun.error_message).trim()"
                >Has reason</span>
                <span
                  v-else
                  class="inline-block text-xs font-semibold px-1.5 py-0.5 rounded bg-amber-100 text-amber-800"
                >No reason</span>
              </dd>
            </div>
            <div>
              <dt class="text-slate-500 font-normal m-0">Inference date</dt>
              <dd class="m-0 mt-0.5 font-medium text-slate-900">{{ formatDateOnly(latestRun.inference_date) }}</dd>
            </div>
            <div>
              <dt class="text-slate-500 font-normal m-0">Horizon</dt>
              <dd class="m-0 mt-0.5 font-medium text-slate-900">{{ latestRun.horizon_weeks }} weeks</dd>
            </div>
            <div>
              <dt class="text-slate-500 font-normal m-0">Type</dt>
              <dd class="m-0 mt-0.5 text-slate-800">{{ latestRun.run_type }}</dd>
            </div>
            <div>
              <dt class="text-slate-500 font-normal m-0">Created</dt>
              <dd class="m-0 mt-0.5 text-slate-800">{{ latestRun.created_at ? formatDateTime(latestRun.created_at) : '—' }}</dd>
            </div>
            <div>
              <dt class="text-slate-500 font-normal m-0">Started</dt>
              <dd class="m-0 mt-0.5 text-slate-800">{{ latestRun.started_at ? formatDateTime(latestRun.started_at) : '—' }}</dd>
            </div>
            <div>
              <dt class="text-slate-500 font-normal m-0">Completed</dt>
              <dd class="m-0 mt-0.5 text-slate-800">{{ latestRun.completed_at ? formatDateTime(latestRun.completed_at) : '—' }}</dd>
            </div>
            <div>
              <dt class="text-slate-500 font-normal m-0">Created by</dt>
              <dd class="m-0 mt-0.5 text-slate-800">{{ latestRun.created_by?.trim() || '—' }}</dd>
            </div>
          </div>
          <p
            v-if="isFailedRunStatus(latestRun.run_status) && hasRecordedFailReason(latestRun)"
            class="text-sm text-red-800 bg-red-50 border border-red-100 rounded-lg px-3 py-2 mt-3 m-0"
          >
            {{ String(latestRun.error_message).trim() }}
          </p>
          <p
            v-else-if="isFailedRunStatus(latestRun.run_status) && !hasRecordedFailReason(latestRun)"
            class="text-sm text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 mt-3 m-0"
          >
            No failure reason recorded for this run.
          </p>
        </template>
        <p v-else-if="!engineRuns.length" class="muted m-0">
          No engine runs yet. Use <router-link to="/admin/forecast-engine" class="text-primary-600 hover:underline">Forecast Settings</router-link>
          to create and execute a run; it will show up here afterward.
        </p>
        <p v-else-if="hideFailedRuns && engineRuns.length" class="muted m-0">
          All loaded runs are failed and hidden. Turn off <strong>Hide failed runs</strong> below to see them.
        </p>
      </section>

      <section class="card card-body" aria-labelledby="recent-runs-heading">
        <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mb-3">
          <h2 id="recent-runs-heading" class="text-base font-medium text-slate-800 m-0">Recent forecast runs</h2>
          <div class="flex flex-wrap items-center gap-3">
            <div class="flex items-center gap-2">
              <input id="hideFailedRunsForecast" v-model="hideFailedRuns" type="checkbox" class="rounded" />
              <label for="hideFailedRunsForecast" class="text-sm cursor-pointer text-slate-700 m-0">Hide failed runs</label>
            </div>
            <button type="button" class="btn-secondary text-sm" :disabled="runsLoading" @click="loadRuns">Refresh</button>
          </div>
        </div>
        <p class="text-xs text-slate-500 m-0 mb-3">
          Data from <code class="bg-slate-100 px-1 rounded">GET /v1/forecast/runs</code> (newest first). Per-model breakdown and result tables are available in Forecast Settings.
        </p>
        <div v-if="!engineRuns.length" class="muted text-sm py-4 m-0">No runs to show.</div>
        <div v-else-if="!runsForDisplay.length" class="muted text-sm py-4 m-0">
          All recent runs are failed and hidden. Uncheck <strong>Hide failed runs</strong> to list them.
        </div>
        <div v-else class="app-table-wrap">
          <table class="app-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>UUID</th>
                <th>Status</th>
                <th class="whitespace-nowrap">Fail note</th>
                <th>Type</th>
                <th>Inference</th>
                <th>Horizon</th>
                <th>Created by</th>
                <th>Created</th>
                <th>Started</th>
                <th>Completed</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="run in runsForDisplay" :key="run.id">
                <td class="font-mono tabular-nums">#{{ run.id }}</td>
                <td class="font-mono text-xs">{{ shortUuid(run.run_uuid) }}</td>
                <td><span :class="statusBadgeClass(run.run_status)">{{ run.run_status }}</span></td>
                <td class="text-xs align-top">
                  <template v-if="isFailedRunStatus(run.run_status)">
                    <span
                      v-if="hasRecordedFailReason(run)"
                      class="inline-block font-semibold px-1.5 py-0.5 rounded bg-sky-100 text-sky-800"
                      :title="String(run.error_message).trim()"
                    >Has reason</span>
                    <span
                      v-else
                      class="inline-block font-semibold px-1.5 py-0.5 rounded bg-amber-100 text-amber-800"
                    >No reason</span>
                  </template>
                  <span v-else class="text-slate-400">—</span>
                </td>
                <td class="text-slate-600">{{ run.run_type }}</td>
                <td class="tabular-nums">{{ formatDateOnly(run.inference_date) }}</td>
                <td class="tabular-nums">{{ run.horizon_weeks }}w</td>
                <td class="text-slate-600 text-sm">{{ run.created_by?.trim() || '—' }}</td>
                <td class="text-slate-600 text-sm">{{ run.created_at ? formatDateTime(run.created_at) : '—' }}</td>
                <td class="text-slate-600 text-sm">{{ run.started_at ? formatDateTime(run.started_at) : '—' }}</td>
                <td class="text-slate-600 text-sm">{{ run.completed_at ? formatDateTime(run.completed_at) : '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import api from '@/api/client'

/** Matches backend ForecastRunOut (forecast_v2). */
interface V1ForecastRun {
  id: number
  run_uuid: string
  run_status: string
  run_type: string
  inference_date: string
  horizon_weeks: number
  source_config_id: number | null
  runtime_config_id: number | null
  error_message: string | null
  created_by: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string | null
}

const RUNS_LIMIT = 50

const runsLoading = ref(true)
const loadError = ref<string | null>(null)
const engineRuns = ref<V1ForecastRun[]>([])
/** Client-side only; default off — does not change API requests. */
const hideFailedRuns = ref(false)

const runsForDisplay = computed(() => {
  if (!hideFailedRuns.value) return engineRuns.value
  return engineRuns.value.filter((r) => !isFailedRunStatus(r.run_status))
})

const latestRun = computed(() => runsForDisplay.value[0] ?? null)

function shortUuid(uuid: string): string {
  const u = uuid?.trim() || ''
  if (u.length <= 12) return u || '—'
  return `${u.slice(0, 8)}…`
}

function formatDateOnly(d: string): string {
  if (!d) return '—'
  if (/^\d{4}-\d{2}-\d{2}$/.test(d)) return d
  const x = new Date(d)
  if (Number.isNaN(x.getTime())) return d
  return x.toISOString().slice(0, 10)
}

function formatDateTime(iso: string): string {
  const x = new Date(iso)
  if (Number.isNaN(x.getTime())) return iso
  return x.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function statusBadgeClass(status: string): string {
  const s = String(status || '').toLowerCase()
  if (s === 'success') return 'badge-success'
  if (s === 'failed') return 'badge-danger'
  if (s === 'running' || s === 'queued') return 'badge-warn'
  if (s === 'partial') return 'badge-warn'
  return 'badge-info'
}

function hasRecordedFailReason(run: V1ForecastRun): boolean {
  return !!(run.error_message && String(run.error_message).trim())
}

/** Case-insensitive match for API run_status values (e.g. Failed, FAILED). */
function isFailedRunStatus(status: string | null | undefined): boolean {
  return String(status ?? '').trim().toLowerCase() === 'failed'
}

async function loadRuns(): Promise<void> {
  runsLoading.value = true
  loadError.value = null
  try {
    const { data } = await api.get<V1ForecastRun[]>(`/v1/forecast/runs?limit=${RUNS_LIMIT}`)
    engineRuns.value = Array.isArray(data) ? data : []
  } catch (e: unknown) {
    engineRuns.value = []
    const msg = e && typeof e === 'object' && 'response' in e
      ? (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      : undefined
    const detailStr = typeof msg === 'string' ? msg : msg != null ? JSON.stringify(msg) : null
    loadError.value =
      detailStr ||
      (e instanceof Error ? e.message : 'Request failed. Check network and server logs.')
  } finally {
    runsLoading.value = false
  }
}

onMounted(() => {
  void loadRuns()
})
</script>

<style scoped>
.latest-summary-grid {
  display: grid;
  gap: 1rem 1.5rem;
  grid-template-columns: repeat(1, minmax(0, 1fr));
}
@media (min-width: 640px) {
  .latest-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (min-width: 1024px) {
  .latest-summary-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
</style>
