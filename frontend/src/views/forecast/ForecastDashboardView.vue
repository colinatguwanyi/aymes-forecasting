<template>
  <div class="page-shell space-y-6">
    <header class="page-header">
      <h1>Forecast dashboard</h1>
      <p class="muted mt-1 max-w-3xl">
        Use this area to work with <strong>demand forecasts</strong> for supply planning: pick which baseline training week plans use,
        compare scenarios, and export outputs. The main planning screens (inventory projection, stock projection, and the supply dashboard)
        consume the <strong>baseline forecast</strong> you select here. Administrators can also run the separate MySQL forecast engine and
        push legacy-compatible files from
        <router-link to="/admin/forecast-engine" class="text-primary-600 hover:underline">Forecast Settings</router-link>.
      </p>
    </header>

    <section aria-labelledby="forecast-sections-heading">
      <h2 id="forecast-sections-heading" class="text-base font-medium text-slate-800 mb-3">Forecast sections</h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        <router-link
          v-for="item in sectionCards"
          :key="item.to"
          :to="item.to"
          class="card card-body block no-underline text-inherit transition-shadow hover:shadow-md hover:border-primary-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
        >
          <h3 class="text-sm font-semibold text-primary-800 mb-1">{{ item.title }}</h3>
          <p class="text-sm text-slate-600 m-0">{{ item.blurb }}</p>
        </router-link>
      </div>
    </section>

    <section class="card card-body" aria-labelledby="latest-run-heading">
      <h2 id="latest-run-heading" class="text-base font-medium text-slate-800 mb-3">Latest baseline run (planning)</h2>
      <div class="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between mb-3">
        <div class="max-w-md w-full">
          <label for="baseline-wh" class="form-label">Warehouse (published baseline)</label>
          <select
            id="baseline-wh"
            v-model="baselineWarehouseCode"
            class="select w-full"
            :disabled="warehousesLoading"
            @change="onBaselineWarehouseChange"
          >
            <option v-for="w in warehouseSelectOptions" :key="w.id" :value="w.code">
              {{ w.code }} – {{ w.name || '—' }}
            </option>
            <option v-if="!warehouseSelectOptions.length" value="AAH">AAH (default — no warehouse list loaded)</option>
          </select>
        </div>
      </div>
      <p v-if="warehousesListEmpty" class="text-xs text-amber-800 bg-amber-50/80 border border-amber-100 rounded-lg px-3 py-2 m-0 mb-3">
        Warehouse directory did not load; the selector falls back to <strong>AAH</strong>. Open
        <router-link to="/admin/warehouses" class="text-primary-700 hover:underline">Admin → Warehouses</router-link>
        if codes are missing.
      </p>
      <p class="text-sm text-slate-600 mb-3 m-0">
        Summary for warehouse <strong>{{ baselineWarehouseCode }}</strong> from
        <code class="text-xs bg-slate-100 px-1.5 py-0.5 rounded">GET /forecast/runs</code>
        — the same list used when pinning a forecast in Scenario Manager. Newest training week is listed first.
      </p>
      <div v-if="runsLoading" class="muted m-0">Loading…</div>
      <div v-else-if="runsError" class="text-sm text-slate-600 space-y-2">
        <p class="m-0">{{ runsError }}</p>
        <p class="muted m-0">Open Run Forecast or Forecast Settings below when you are ready; the summary will load automatically when the API succeeds.</p>
      </div>
      <div v-else-if="latestBaselineRun" class="latest-run-grid text-sm">
        <div>
          <dt class="text-slate-500 font-normal m-0">Training week end</dt>
          <dd class="m-0 mt-0.5 font-medium text-slate-900">{{ latestBaselineRun.train_end_week_start }}</dd>
        </div>
        <div>
          <dt class="text-slate-500 font-normal m-0">Model</dt>
          <dd class="m-0 mt-0.5 font-medium text-slate-900">{{ latestBaselineRun.model_name?.trim() || '—' }}</dd>
        </div>
        <div>
          <dt class="text-slate-500 font-normal m-0">Row count</dt>
          <dd class="m-0 mt-0.5 font-medium text-slate-900 tabular-nums">{{ formatInt(latestBaselineRun.count_rows) }}</dd>
        </div>
        <div v-if="latestBaselineRun.created_at" class="sm:col-span-2 xl:col-span-3">
          <dt class="text-slate-500 font-normal m-0">Created</dt>
          <dd class="m-0 mt-0.5 font-medium text-slate-900">{{ formatDate(latestBaselineRun.created_at) }}</dd>
        </div>
        <div v-if="latestBaselineRun.notes?.trim()" class="sm:col-span-2 xl:col-span-3">
          <dt class="text-slate-500 font-normal m-0">Notes</dt>
          <dd class="m-0 mt-0.5 text-slate-800">{{ latestBaselineRun.notes.trim() }}</dd>
        </div>
      </div>
      <p v-else class="muted m-0">
        No baseline forecast runs were returned for warehouse {{ baselineWarehouseCode }}. After demand history is available and baseline runs exist,
        the newest training week and row counts will show here automatically.
      </p>
    </section>

    <section class="card card-body" aria-labelledby="current-state-heading">
      <h2 id="current-state-heading" class="text-base font-medium text-slate-800 mb-2">Current forecast state</h2>
      <p class="text-xs text-slate-500 m-0 mb-4">
        Live snapshot: MySQL engine runs from <code class="bg-slate-100 px-1 rounded text-xs">GET /v1/forecast/runs</code> and your newest plan run from the planning store.
      </p>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm">
        <div class="space-y-2">
          <h3 class="text-sm font-semibold text-slate-800 m-0">Forecast engine (MySQL)</h3>
          <div v-if="engineRunsLoading" class="muted m-0">Loading…</div>
          <p v-else-if="engineRunsError" class="text-slate-600 m-0">{{ engineRunsError }}</p>
          <template v-else-if="latestEngineRun">
            <dl class="state-dl m-0">
              <div>
                <dt class="text-slate-500 font-normal m-0">Latest run</dt>
                <dd class="m-0 mt-0.5 font-mono text-slate-900">#{{ latestEngineRun.id }}</dd>
              </div>
              <div>
                <dt class="text-slate-500 font-normal m-0">Status</dt>
                <dd class="m-0 mt-0.5">
                  <span :class="engineStatusBadgeClass(latestEngineRun.run_status)">{{ latestEngineRun.run_status }}</span>
                </dd>
              </div>
              <div>
                <dt class="text-slate-500 font-normal m-0">Inference date</dt>
                <dd class="m-0 mt-0.5 tabular-nums text-slate-800">{{ latestEngineRun.inference_date || '—' }}</dd>
              </div>
              <div>
                <dt class="text-slate-500 font-normal m-0">Loaded</dt>
                <dd class="m-0 mt-0.5 tabular-nums text-slate-800">{{ engineRuns.length }} recent run{{ engineRuns.length === 1 ? '' : 's' }}</dd>
              </div>
            </dl>
          </template>
          <p v-else class="muted m-0">No engine runs returned.</p>
          <div class="flex flex-wrap gap-x-3 gap-y-1 pt-1">
            <router-link to="/forecast/runs" class="text-primary-600 hover:underline text-xs">Run forecast</router-link>
            <router-link to="/admin/forecast-engine" class="text-primary-600 hover:underline text-xs">Forecast Settings</router-link>
          </div>
        </div>
        <div class="space-y-2">
          <h3 class="text-sm font-semibold text-slate-800 m-0">Planning (latest plan run)</h3>
          <div v-if="planRunsLoading" class="muted m-0">Loading…</div>
          <p v-else-if="planRunsError" class="text-slate-600 m-0">{{ planRunsError }}</p>
          <template v-else-if="latestPlanRun">
            <dl class="state-dl m-0">
              <div class="md:col-span-2">
                <dt class="text-slate-500 font-normal m-0">Run</dt>
                <dd class="m-0 mt-0.5 text-slate-900">{{ formatPlanRunLabel(latestPlanRun) }}</dd>
              </div>
              <div>
                <dt class="text-slate-500 font-normal m-0">Scenario</dt>
                <dd class="m-0 mt-0.5 text-slate-800">{{ latestPlanRun.scenario_name }}</dd>
              </div>
              <div>
                <dt class="text-slate-500 font-normal m-0">Demand source</dt>
                <dd class="m-0 mt-0.5 text-slate-800">{{ latestPlanRun.demand_source ?? '—' }}</dd>
              </div>
              <div>
                <dt class="text-slate-500 font-normal m-0">Baseline week</dt>
                <dd class="m-0 mt-0.5 tabular-nums text-slate-800">{{ planRunBaselineWeek(latestPlanRun) }}</dd>
              </div>
              <div class="md:col-span-2">
                <dt class="text-slate-500 font-normal m-0">Scope</dt>
                <dd class="m-0 mt-0.5 text-slate-800 break-words">
                  {{ latestPlanRunScopeSummary }}
                  <span
                    v-if="latestPlanRunScopeSourceFootnote"
                    class="block text-xs text-slate-500 mt-1 font-normal"
                  >{{ latestPlanRunScopeSourceFootnote }}</span>
                </dd>
              </div>
              <div>
                <dt class="text-slate-500 font-normal m-0">Plan runs loaded</dt>
                <dd class="m-0 mt-0.5 tabular-nums text-slate-800">{{ planning.planRuns.length }}</dd>
              </div>
            </dl>
          </template>
          <p v-else class="muted m-0">No plan runs yet.</p>
          <p v-if="!planRunsLoading && !planRunsError && !latestPlanRun" class="text-xs text-slate-600 m-0 mt-1">
            <span class="text-slate-500">Scope</span>: —
          </p>
          <div class="flex flex-wrap gap-x-3 gap-y-1 pt-1">
            <router-link to="/planning/scenario-manager" class="text-primary-600 hover:underline text-xs">Scenario Manager</router-link>
            <router-link to="/" class="text-primary-600 hover:underline text-xs">Supply Dashboard</router-link>
          </div>
        </div>
      </div>

      <div
        v-if="!runsLoading && !planRunsLoading"
        class="mt-4 pt-4 border-t border-slate-200 text-sm"
      >
        <p class="text-xs font-medium text-slate-500 m-0 mb-1">Baseline alignment (published week for {{ baselineWarehouseCode }})</p>
        <p class="m-0 mb-2 text-xs text-slate-600 border-l-2 border-slate-200 pl-2.5 py-0.5 bg-slate-50/80 rounded-r">
          {{ planRunScopeHintText }}
        </p>
        <p
          v-if="baselineAlignment.kind === 'aligned'"
          class="m-0 rounded-lg border border-emerald-200 bg-emerald-50/70 px-3 py-2 text-emerald-950"
        >
          <strong>Aligned.</strong> The newest plan run is using the same training week as the latest published baseline
          (<span class="tabular-nums">{{ baselineAlignment.published }}</span>).
        </p>
        <p
          v-else-if="baselineAlignment.kind === 'not_aligned'"
          class="m-0 rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2 text-amber-950"
        >
          <strong>Not aligned.</strong> Latest published baseline week is
          <span class="tabular-nums">{{ baselineAlignment.published }}</span>, but the newest plan run is pinned to
          <span class="tabular-nums">{{ baselineAlignment.plan }}</span>. Use Scenario Manager if you meant to match the latest baseline.
        </p>
        <p
          v-else
          class="m-0 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-slate-700"
        >
          <strong>Not enough data to compare.</strong> {{ baselineAlignment.message }}
        </p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { ForecastRunOption, PlanRun } from '@/api/client'
import { formatPlanRunLabel } from '@/api/client'
import api from '@/api/client'
import { useAdminStore } from '@/stores/admin'
import { usePlanningStore } from '@/stores/planning'

const planning = usePlanningStore()
const adminStore = useAdminStore()

/** Drives GET /forecast/runs?warehouse_code=… and the alignment hint for that published baseline. */
const baselineWarehouseCode = ref('AAH')
const warehousesLoading = ref(false)

const warehouseSelectOptions = computed(() =>
  [...adminStore.warehouses]
    .filter((w) => w.active)
    .sort((a, b) => a.code.localeCompare(b.code)),
)

const warehousesListEmpty = computed(() => !warehousesLoading.value && warehouseSelectOptions.value.length === 0)

const sectionCards = [
  {
    to: '/forecast/runs',
    title: 'Run forecast',
    blurb: 'Entry point for forecast runs — full create / execute / results console lives under Forecast Settings.',
  },
  {
    to: '/forecast/scenarios',
    title: 'Scenarios',
    blurb: 'Shortcuts for scenario workflows tied to forecasts and planning.',
  },
  {
    to: '/forecast/exports',
    title: 'Forecast export',
    blurb: 'Download forecast outputs and legacy-compatible exports.',
  },
  {
    to: '/planning/scenario-manager',
    title: 'Scenario Manager',
    blurb: 'Pin baseline training weeks, recalculate demand, and view forecast health for plan runs.',
  },
  {
    to: '/admin/forecast-engine',
    title: 'Forecast Settings',
    blurb: 'MySQL forecast engine: runtime config, runs, diagnostics, supply-adjusted output, and file exports.',
  },
  {
    to: '/admin/forecast-methods',
    title: 'Forecasting methods',
    blurb: 'Method documentation and acknowledgements for baseline / blended forecasting.',
  },
] as const

const runsLoading = ref(false)
const runsError = ref<string | null>(null)
const forecastRuns = ref<ForecastRunOption[]>([])

const latestBaselineRun = computed(() => forecastRuns.value[0] ?? null)

interface V1EngineRunRow {
  id: number
  run_status: string
  inference_date: string
}

const engineRuns = ref<V1EngineRunRow[]>([])
const engineRunsLoading = ref(false)
const engineRunsError = ref<string | null>(null)
const planRunsLoading = ref(false)
const planRunsError = ref<string | null>(null)

const latestEngineRun = computed(() => engineRuns.value[0] ?? null)
const latestPlanRun = computed((): PlanRun | null =>
  planning.planRuns.length ? planning.planRuns[0]! : null,
)

/** Normalized YYYY-MM-DD for comparison, or null if missing. */
function normalizeTrainWeekKey(s: string | null | undefined): string | null {
  if (s == null || String(s).trim() === '') return null
  const t = String(s).trim()
  if (/^\d{4}-\d{2}-\d{2}/.test(t)) return t.slice(0, 10)
  return t.length >= 10 ? t.slice(0, 10) : t
}

const publishedBaselineWeekKey = computed(() =>
  normalizeTrainWeekKey(latestBaselineRun.value?.train_end_week_start),
)

const planRunBaselineWeekKey = computed(() => {
  const r = latestPlanRun.value
  if (!r) return null
  return normalizeTrainWeekKey(r.baseline_train_end_week_start ?? r.selected_train_end_week_start ?? undefined)
})

const baselineAlignment = computed(() => {
  const p = publishedBaselineWeekKey.value
  const pl = planRunBaselineWeekKey.value
  if (p && pl) {
    if (p === pl) return { kind: 'aligned' as const, published: p, plan: pl }
    return { kind: 'not_aligned' as const, published: p, plan: pl }
  }
  const parts: string[] = []
  if (!p) {
    parts.push(
      runsError.value
        ? 'The published baseline list did not load, or there is no baseline for this warehouse yet.'
        : `There is no published baseline training week for warehouse ${baselineWarehouseCode.value} yet.`,
    )
  }
  if (!latestPlanRun.value) {
    parts.push('There is no plan run in the list yet.')
  } else if (!pl) {
    parts.push(
      'The newest plan run has no baseline training week set, or it uses demand that does not rely on a pinned baseline week.',
    )
  }
  return {
    kind: 'insufficient' as const,
    published: p,
    plan: pl,
    message: parts.join(' '),
  }
})

function normalizeWarehouseCode(code: string): string {
  return String(code ?? '').trim().toUpperCase()
}

type PlanRunScopeField = 'warehouses_scope' | 'warehouses_planned' | 'warehouses_planned_detail'

/**
 * Same precedence everywhere in this view: warehouses_scope, then progress_meta.warehouses_planned,
 * then progress_meta.warehouses_planned_detail[].warehouse_code.
 */
function derivePlanRunScope(r: PlanRun): { set: Set<string>; source: PlanRunScopeField | null } {
  const scope = r.warehouses_scope
  if (scope?.length) {
    return {
      set: new Set(scope.map((c) => normalizeWarehouseCode(c)).filter(Boolean)),
      source: 'warehouses_scope',
    }
  }
  const planned = r.progress_meta?.warehouses_planned
  if (planned?.length) {
    return {
      set: new Set(planned.map((c) => normalizeWarehouseCode(c)).filter(Boolean)),
      source: 'warehouses_planned',
    }
  }
  const detail = r.progress_meta?.warehouses_planned_detail
  if (detail?.length) {
    return {
      set: new Set(detail.map((d) => normalizeWarehouseCode(d.warehouse_code)).filter(Boolean)),
      source: 'warehouses_planned_detail',
    }
  }
  return { set: new Set(), source: null }
}

/** Non-null set only when a source branch matched and at least one usable code exists (hint + alignment). */
function planRunScopedWarehouseSet(r: PlanRun): Set<string> | null {
  const { set, source } = derivePlanRunScope(r)
  if (source === null || set.size === 0) return null
  return set
}

/** Same derivation as the alignment scope hint: explicit codes or plain "not explicit". */
const latestPlanRunScopeSummary = computed(() => {
  const r = latestPlanRun.value
  if (!r) return '—'
  const set = planRunScopedWarehouseSet(r)
  if (set == null || set.size === 0) return 'Not explicit in loaded data'
  const sorted = [...set].sort((a, b) => a.localeCompare(b))
  const maxShow = 6
  if (sorted.length <= maxShow) return sorted.join(', ')
  return `${sorted.slice(0, maxShow).join(', ')} (+${sorted.length - maxShow} more)`
})

const latestPlanRunScopeSourceFootnote = computed(() => {
  const r = latestPlanRun.value
  if (!r) return ''
  const { set, source } = derivePlanRunScope(r)
  if (source === null) {
    return 'Not explicit: this payload has no list on warehouses_scope, progress_meta.warehouses_planned, or progress_meta.warehouses_planned_detail.'
  }
  const label =
    source === 'warehouses_scope'
      ? 'warehouses_scope'
      : source === 'warehouses_planned'
        ? 'progress_meta.warehouses_planned'
        : 'progress_meta.warehouses_planned_detail (warehouse_code)'
  if (set.size === 0) {
    return `Source field ${label} was present, but no usable warehouse codes were found.`
  }
  return `Source: ${label}.`
})

const planRunScopeHintText = computed(() => {
  const wh = baselineWarehouseCode.value.trim()
  const sel = normalizeWarehouseCode(wh)
  const r = latestPlanRun.value
  if (!r) {
    return 'There is no plan run in the loaded list, so warehouse scope on the plan side is unknown.'
  }
  const codes = planRunScopedWarehouseSet(r)
  if (codes == null || codes.size === 0) {
    return (
      'Warehouse scope for the newest plan run is not explicit in the data shown here. ' +
      `The alignment below still compares the published baseline for warehouse ${wh} to the pinned week on that plan run — it may or may not apply to ${wh}.`
    )
  }
  if (codes.has(sel)) {
    return `The newest plan run's recorded scope includes warehouse ${wh}.`
  }
  const listed = [...codes].sort().join(', ')
  return (
    `The newest plan run's recorded scope lists only: ${listed}. Warehouse ${wh} is not in that list — ` +
    'do not treat the alignment verdict as specific to this site unless you know that run covered it.'
  )
})

function planRunBaselineWeek(r: PlanRun): string {
  const w = r.baseline_train_end_week_start ?? r.selected_train_end_week_start
  if (w != null && String(w).trim() !== '') return String(w).slice(0, 10)
  return '—'
}

function engineStatusBadgeClass(status: string): string {
  const s = String(status || '').toLowerCase()
  if (s === 'success') return 'badge-success'
  if (s === 'failed') return 'badge-danger'
  if (s === 'running' || s === 'queued') return 'badge-warn'
  if (s === 'partial') return 'badge-warn'
  return 'badge-info'
}

function formatInt(n: number): string {
  return Number.isFinite(n) ? n.toLocaleString() : String(n)
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function pickInitialBaselineWarehouseCode(): void {
  const opts = warehouseSelectOptions.value
  if (!opts.length) return
  const codes = new Set(opts.map((w) => w.code))
  if (codes.has(baselineWarehouseCode.value)) return
  baselineWarehouseCode.value = codes.has('AAH') ? 'AAH' : opts[0]!.code
}

async function loadPublishedBaselines(): Promise<void> {
  runsLoading.value = true
  runsError.value = null
  try {
    forecastRuns.value = await planning.getForecastRuns(baselineWarehouseCode.value)
  } catch (e: unknown) {
    runsError.value = e instanceof Error ? e.message : 'Could not load forecast runs.'
    forecastRuns.value = []
  } finally {
    runsLoading.value = false
  }
}

function onBaselineWarehouseChange(): void {
  void loadPublishedBaselines()
}

onMounted(async () => {
  warehousesLoading.value = true
  try {
    await adminStore.fetchWarehouses()
  } catch {
    /* keep fallback option in select */
  } finally {
    warehousesLoading.value = false
  }
  pickInitialBaselineWarehouseCode()
  await loadPublishedBaselines()

  engineRunsLoading.value = true
  engineRunsError.value = null
  try {
    const { data } = await api.get<V1EngineRunRow[]>('/v1/forecast/runs?limit=25')
    engineRuns.value = Array.isArray(data) ? data : []
  } catch (e: unknown) {
    engineRuns.value = []
    engineRunsError.value =
      e instanceof Error ? e.message : 'Engine runs could not be loaded. Open Run forecast when the service is available.'
  } finally {
    engineRunsLoading.value = false
  }

  planRunsLoading.value = true
  planRunsError.value = null
  try {
    await planning.fetchPlanRuns()
  } catch (e: unknown) {
    planRunsError.value =
      e instanceof Error ? e.message : 'Plan runs could not be loaded. Try again from Scenario Manager or the Supply Dashboard.'
  } finally {
    planRunsLoading.value = false
  }
})
</script>

<style scoped>
.latest-run-grid {
  display: grid;
  gap: 1rem 1.5rem;
  grid-template-columns: repeat(1, minmax(0, 1fr));
}
@media (min-width: 640px) {
  .latest-run-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (min-width: 1280px) {
  .latest-run-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.state-dl {
  display: grid;
  gap: 0.65rem 1rem;
  grid-template-columns: repeat(1, minmax(0, 1fr));
}
@media (min-width: 400px) {
  .state-dl {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
