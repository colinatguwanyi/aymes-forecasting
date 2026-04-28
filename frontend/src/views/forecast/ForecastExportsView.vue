<template>
  <div class="page-shell space-y-6">
    <header class="page-header">
      <h1>Forecast exports</h1>
      <p class="muted mt-1 max-w-3xl m-0">
        <strong>Exports</strong> are files or database writes you generate <em>after</em> a forecast or plan is ready: they package numbers for finance, SAP-style tables, or offline analysis.
        Use <strong>Quick export</strong> below for common downloads; the rest of this page explains how exports fit together.
      </p>
    </header>

    <section class="card card-body border border-slate-200" aria-labelledby="quick-export-heading">
      <h2 id="quick-export-heading" class="text-base font-medium text-slate-800 m-0 mb-3">Quick export</h2>
      <p class="text-sm text-slate-600 m-0 mb-4">
        Planning CSVs use a <strong>plan run</strong> (supply scenario). Engine file bundles use a <strong>forecast engine run</strong> from MySQL (same IDs as
        <router-link to="/forecast/runs" class="text-primary-600 hover:underline">Run forecast</router-link>).
      </p>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="space-y-3">
          <h3 class="text-sm font-semibold text-slate-800 m-0">Planning CSV</h3>
          <div>
            <label class="form-label">Plan run</label>
            <select v-model="selectedPlanRunId" class="select w-full max-w-md">
              <option :value="null">Select plan run</option>
              <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ formatPlanRunLabel(r) }}</option>
            </select>
          </div>
          <p
            v-if="selectedPlanRunId != null && isDemandOnlyPlanRun"
            class="p-2 rounded-md bg-sky-50 border border-sky-200 text-sky-900 text-sm m-0"
          >
            <strong>Demand-only run.</strong> CSV downloads may use a <code class="text-xs bg-sky-100 px-1 rounded">_demand_only</code> filename. Contents are modeled ledger outputs, not physical warehouse stock projections.
          </p>
          <p v-if="selectedPlanRunId == null" class="text-sm text-slate-600 m-0">
            Select a run or go to
            <router-link to="/exports" class="text-primary-600 hover:underline">Planning exports</router-link>
            for more CSV types.
          </p>
          <div v-else class="flex flex-wrap gap-2">
            <a :href="projectedInventoryExportUrl" class="btn-primary inline-block" download>Projected inventory CSV</a>
            <a :href="plannedOrdersExportUrl" class="btn-secondary inline-block" download>Planned orders CSV</a>
          </div>
        </div>

        <div class="space-y-3">
          <h3 class="text-sm font-semibold text-slate-800 m-0">Engine file bundle</h3>
          <div>
            <label class="form-label">Engine run</label>
            <select v-model="selectedEngineRunId" class="select w-full max-w-md" :disabled="engineRunsLoading">
              <option :value="null">{{ engineRunsLoading ? 'Loading runs…' : 'Select engine run' }}</option>
              <option v-for="r in engineRuns" :key="r.id" :value="r.id">
                #{{ r.id }} · {{ r.run_status }} · {{ r.inference_date || '—' }}
              </option>
            </select>
          </div>
          <p v-if="selectedEngineRunId == null" class="text-sm text-slate-600 m-0">
            Select a run or go to
            <router-link to="/forecast/runs" class="text-primary-600 hover:underline">Run Forecast</router-link>.
          </p>
          <div v-else class="space-y-2">
            <button
              type="button"
              class="btn-primary text-sm"
              :disabled="engineExportLoading"
              @click="doEngineExportFiles"
            >
              {{ engineExportLoading ? 'Exporting…' : 'Generate file bundle' }}
            </button>
            <OperationStatusPanel :operation="engineExportOperation.operation" />
          </div>
        </div>
      </div>
    </section>

    <section class="card card-body text-sm space-y-4" aria-labelledby="types-heading">
      <h2 id="types-heading" class="text-base font-medium text-slate-800 m-0">Three kinds of “export” in this app</h2>
      <ul class="list-disc pl-5 space-y-2 text-slate-700 m-0">
        <li>
          <strong>Forecast engine outputs</strong> — Weekly model results, legacy table writes, and bundled files from the MySQL forecast pipeline. Created from a specific
          <strong>engine run</strong> in Forecast Settings (execute run first, then export).
        </li>
        <li>
          <strong>Planning exports</strong> — CSV downloads tied to a <strong>plan run</strong> (scenario): projected inventory, planned orders, exceptions, SKU explanation reports.
          You can start from <strong>Quick export</strong> above or use the full <router-link to="/exports" class="text-primary-600 hover:underline">Planning exports</router-link> page.
        </li>
        <li>
          <strong>Baseline forecast data used downstream</strong> — Published weekly baselines (training week × SKU × warehouse) that planning uses when demand source is baseline or blended.
          That data is produced/imported through your normal forecast pipeline; pinning which week to use is done in Scenario Manager, not on this page.
        </li>
      </ul>
    </section>

    <section class="card card-body border-primary-100 bg-primary-50/40" aria-labelledby="chooser-heading">
      <h2 id="chooser-heading" class="text-base font-medium text-slate-800 m-0 mb-2">Which page should I use?</h2>
      <dl class="space-y-3 text-sm text-slate-700 m-0">
        <div>
          <dt class="font-medium text-slate-900 m-0">I need CSVs for a planning scenario I already ran</dt>
          <dd class="m-0 mt-0.5">
            → <router-link to="/exports" class="text-primary-600 hover:underline">Planning exports</router-link>
            (and pick the plan run in each section).
          </dd>
        </div>
        <div>
          <dt class="font-medium text-slate-900 m-0">I need legacy / file exports from the forecast engine</dt>
          <dd class="m-0 mt-0.5">
            → <router-link to="/admin/forecast-engine" class="text-primary-600 hover:underline">Forecast Settings</router-link>
            — open the <strong>Runs</strong> section, select a run, then use export actions there.
          </dd>
        </div>
        <div>
          <dt class="font-medium text-slate-900 m-0">I want to see engine run status before exporting</dt>
          <dd class="m-0 mt-0.5">
            → <router-link to="/forecast/runs" class="text-primary-600 hover:underline">Run forecast</router-link>
            for a read-only list, or Forecast Settings for the full console.
          </dd>
        </div>
        <div>
          <dt class="font-medium text-slate-900 m-0">I need to pin which baseline forecast week a scenario uses</dt>
          <dd class="m-0 mt-0.5">
            → <router-link to="/planning/scenario-manager" class="text-primary-600 hover:underline">Scenario Manager</router-link>
            (not an export — it changes demand inputs for recalc).
          </dd>
        </div>
      </dl>
    </section>

    <section aria-labelledby="actions-heading">
      <h2 id="actions-heading" class="text-base font-medium text-slate-800 mb-3">Go to the right screen</h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        <router-link
          v-for="item in actionCards"
          :key="item.to"
          :to="item.to"
          class="card card-body block no-underline text-inherit transition-shadow hover:shadow-md hover:border-primary-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
        >
          <h3 class="text-sm font-semibold text-primary-800 mb-1">{{ item.title }}</h3>
          <p class="text-sm text-slate-600 m-0">{{ item.blurb }}</p>
        </router-link>
      </div>
    </section>

    <section class="card card-body text-sm text-slate-700" aria-labelledby="workflows-heading">
      <h2 id="workflows-heading" class="text-base font-medium text-slate-800 m-0 mb-2">What you can do from this area</h2>
      <ul class="list-disc pl-5 space-y-1.5 m-0">
        <li>Understand whether you need an <strong>engine</strong> export, a <strong>planning</strong> CSV, or a <strong>baseline</strong> configuration change.</li>
        <li>Jump to Forecast Settings when the run is in the MySQL engine and you need legacy writes or file bundles.</li>
        <li>Use Quick export or Planning exports when you already have a plan run and need operational CSVs.</li>
        <li>Use Scenario Manager when the issue is <strong>which forecast week</strong> feeds demand, not downloading a file.</li>
      </ul>
      <p class="muted mt-3 mb-0">
        There is no central “export history” list in the app today; completed downloads are not tracked here. Use the run or plan run you care about on the target page.
      </p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import api, { formatPlanRunLabel, planRunPlanningMode } from '@/api/client'
import { usePlanningStore } from '@/stores/planning'
import OperationStatusPanel from '@/components/common/OperationStatusPanel.vue'
import { useOperation } from '@/composables/useOperation'

interface EngineRunOption {
  id: number
  run_status: string
  inference_date: string
}

const store = usePlanningStore()
const planRuns = computed(() => store.planRuns)
const selectedPlanRunId = ref<number | null>(null)
const selectedPlanRun = computed(() =>
  selectedPlanRunId.value != null ? planRuns.value.find((r) => r.id === selectedPlanRunId.value) ?? null : null
)
const isDemandOnlyPlanRun = computed(
  () => selectedPlanRun.value != null && planRunPlanningMode(selectedPlanRun.value) === 'demand_only'
)
const selectedEngineRunId = ref<number | null>(null)
const engineRuns = ref<EngineRunOption[]>([])
const engineRunsLoading = ref(false)
const engineExportOperation = useOperation('Generate forecast file bundle')
const engineExportLoading = engineExportOperation.isRunning

const projectedInventoryExportUrl = computed(() =>
  selectedPlanRunId.value != null
    ? `/api/exports/projected-inventory?plan_run_id=${selectedPlanRunId.value}`
    : '#',
)
const plannedOrdersExportUrl = computed(() =>
  selectedPlanRunId.value != null
    ? `/api/exports/planned-orders?plan_run_id=${selectedPlanRunId.value}`
    : '#',
)

function apiError(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail) return JSON.stringify(detail)
  return err instanceof Error ? err.message : String(err)
}

async function loadEngineRuns(): Promise<void> {
  engineRunsLoading.value = true
  try {
    const { data } = await api.get<EngineRunOption[]>('/v1/forecast/runs?limit=50')
    engineRuns.value = Array.isArray(data) ? data : []
  } catch {
    engineRuns.value = []
  } finally {
    engineRunsLoading.value = false
  }
}

async function doEngineExportFiles(): Promise<void> {
  const runId = selectedEngineRunId.value
  if (runId == null) return
  const data = await engineExportOperation.runWithOperation(
    'Generate forecast file bundle',
    async () => {
      try {
        const response = await api.post<Record<string, unknown>>(`/v1/forecast/runs/${runId}/export-files`)
        return response.data
      } catch (e: unknown) {
        throw new Error(apiError(e))
      }
    },
    {
      runningMessage: `Generating files for engine run #${runId}...`,
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh run status before retrying.',
      nextActions: ['Refresh run status before retrying.', 'Check the forecast output folder for a completed bundle.'],
    },
  )
  if (!data) return
  const path = data && typeof data.output_path === 'string' ? data.output_path : null
  const files = data && Array.isArray(data.files_generated) ? (data.files_generated as string[]).join(', ') : ''
  engineExportOperation.completeOperation({
    message: path ? `Output: ${path}${files ? ` - ${files}` : ''}` : 'Export completed.',
    technicalDetails: data,
  })
}

onMounted(() => {
  void store.fetchPlanRuns()
  void loadEngineRuns()
})

const actionCards = [
  {
    to: '/admin/forecast-engine',
    title: 'Forecast Settings',
    blurb: 'Engine runs: execute, then legacy export, file bundles, validation — primary place for forecast engine outputs.',
  },
  {
    to: '/exports',
    title: 'Planning exports',
    blurb: 'CSV downloads per plan run — projected inventory, planned orders, exceptions, SKU explanation report.',
  },
  {
    to: '/forecast/runs',
    title: 'Run forecast',
    blurb: 'Recent engine runs and status; use Forecast Settings from there for export actions.',
  },
  {
    to: '/planning/scenario-manager',
    title: 'Scenario Manager',
    blurb: 'Pin baseline training weeks and recalc demand — configures what forecasts feed planning.',
  },
  {
    to: '/forecast/dashboard',
    title: 'Forecast dashboard',
    blurb: 'Overview and latest published baseline context for planning (warehouse-scoped).',
  },
  {
    to: '/forecast/scenarios',
    title: 'Forecast scenarios',
    blurb: 'Plan runs overview and links to grids — helpful before choosing exports for a scenario.',
  },
] as const
</script>
