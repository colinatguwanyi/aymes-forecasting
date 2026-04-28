<template>
  <div class="page-shell space-y-6">
    <header class="page-header">
      <h1>Exceptions</h1>
      <p class="muted mt-1">What needs attention: projected stockouts and low cover within the horizon. Click a row to open the explanation panel or go to SKU detail.</p>
    </header>

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
          <label class="form-label">Within weeks</label>
          <select v-model="withinWeeks" class="select w-full max-w-24">
            <option :value="4">4</option>
            <option :value="8">8</option>
            <option :value="12">12</option>
            <option :value="26">26</option>
            <option :value="52">52</option>
          </select>
        </div>
        <div class="flex items-end">
          <label class="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
            <input type="checkbox" v-model="includeLowCover" class="rounded border-slate-300" />
            Include low cover (warnings)
          </label>
        </div>
      </div>
    </section>

    <!-- demand_only: API intentionally returns no physical stock-risk exception queue. -->
    <section v-if="selectedRunId && isDemandOnlyRun" class="mb-4 p-3 rounded-lg bg-sky-50 border border-sky-200 text-sky-900 text-sm">
      <strong>Demand-only run.</strong> Stockout and low-cover alerts are turned off here so nothing is mistaken for physical warehouse risk. Use the planning grid or CSV exports for this scenario’s modeled outputs.
    </section>

    <section class="card">
      <div class="card-header">
        <h3 class="section-title mb-0">Exceptions ({{ exceptions.length }})</h3>
      </div>
      <div v-if="loading" class="px-5 py-8 text-sm text-slate-500">Loading…</div>
      <template v-else>
        <DataTable
          v-if="exceptionRows.length"
          :columns="exceptionColumns"
          :rows="exceptionRows"
          row-key="_key"
          density="compact"
          :on-row-click="(row) => openExplanation(row as unknown as PlanningException)"
        >
          <template #cell-sku="{ row }">
            <router-link
              :to="{ path: '/sku-detail', query: { sku: (row as unknown as PlanningException).sku, warehouse_code: (row as unknown as PlanningException).warehouse_code, plan_run_id: String(selectedRunId) } }"
              class="text-primary-600 hover:underline"
              @click.stop
            >
              {{ (row as unknown as PlanningException).sku }}
            </router-link>
          </template>
          <template #empty>
            <p class="text-slate-500">No exceptions in this horizon. Select a scenario and run a plan if needed.</p>
          </template>
        </DataTable>
        <p v-else class="px-5 py-8 text-sm text-slate-500">
          <template v-if="isDemandOnlyRun">No rows here by design for demand-only runs (physical stock-risk exceptions are not listed).</template>
          <template v-else>No exceptions in this horizon. Select a scenario and run a plan if needed.</template>
        </p>
      </template>
    </section>

    <Teleport to="#right-panel-body">
      <div v-if="explanation" class="explanation-panel p-4">
        <template v-if="explanationLoading">Loading…</template>
        <template v-else-if="explanationData">
          <h3 class="text-sm font-semibold text-slate-800 mb-2">Week {{ explanationData.projection?.week_start }}</h3>
          <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm" v-if="explanationData.projection">
            <dt class="text-slate-500">Start qty</dt><dd>{{ explanationData.projection.start_qty ?? '—' }}</dd>
            <dt class="text-slate-500">Receipts</dt><dd>{{ explanationData.projection.receipts_qty ?? '—' }}</dd>
            <dt class="text-slate-500">Demand</dt><dd>{{ explanationData.projection.demand_qty ?? '—' }}</dd>
            <dt class="text-slate-500">Projected qty</dt><dd>{{ explanationData.projection.projected_qty }}</dd>
            <dt class="text-slate-500">Weeks of cover</dt><dd>{{ explanationData.projection.weeks_of_cover ?? '—' }}</dd>
            <dt class="text-slate-500">Stockout</dt><dd>{{ explanationData.projection.stockout ? 'Yes' : 'No' }}</dd>
          </dl>
          <h3 class="text-sm font-semibold text-slate-800 mt-3 mb-1">Policy</h3>
          <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm" v-if="explanationData.policy">
            <dt class="text-slate-500">Mode</dt><dd>{{ explanationData.policy.mode ?? '—' }}</dd>
            <dt class="text-slate-500">Target weeks</dt><dd>{{ explanationData.policy.target_weeks ?? '—' }}</dd>
            <dt class="text-slate-500">Safety stock weeks</dt><dd>{{ explanationData.policy.safety_stock_weeks ?? '—' }}</dd>
            <dt class="text-slate-500">Forecast window</dt><dd>{{ explanationData.policy.forecast_window_weeks ?? '—' }}</dd>
            <dt class="text-slate-500">Lead time</dt>
            <dd>{{ [explanationData.policy.lead_time_production_weeks, explanationData.policy.lead_time_slot_wait_weeks, explanationData.policy.lead_time_haulage_weeks, explanationData.policy.lead_time_putaway_weeks, explanationData.policy.lead_time_padding_weeks].filter(Boolean).join(' / ') || '—' }}</dd>
          </dl>
          <p class="text-slate-500 text-sm mt-2">Forecast method: {{ explanationData.forecast_method }}</p>
        </template>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useLayoutStore } from '@/stores/layout'
import { usePlanningStore } from '@/stores/planning'
import DataTable from '@/components/console/DataTable.vue'
import type { DataTableColumn } from '@/components/console/DataTable.vue'
import type { PlanningException, SkuWeekExplanation } from '@/api/client'
import { formatPlanRunLabel, planRunPlanningMode } from '@/api/client'

const store = usePlanningStore()
const layout = useLayoutStore()
const loading = ref(true)
const selectedRunId = ref<number | null>(null)
const withinWeeks = ref(12)
const includeLowCover = ref(true)
const exceptions = ref<PlanningException[]>([])
const explanation = ref(false)
const explanationLoading = ref(false)
const explanationData = ref<SkuWeekExplanation | null>(null)

const planRuns = computed(() => store.planRuns)
const selectedRun = computed(() =>
  selectedRunId.value != null ? planRuns.value.find((r) => r.id === selectedRunId.value) ?? null : null
)
const isDemandOnlyRun = computed(
  () => selectedRun.value != null && planRunPlanningMode(selectedRun.value) === 'demand_only'
)

const exceptionColumns: DataTableColumn[] = [
  { key: 'type', label: 'Type' },
  { key: 'sku', label: 'SKU' },
  { key: 'warehouse_code', label: 'Warehouse' },
  { key: 'week_start', label: 'Week' },
  { key: 'message', label: 'Message' },
  { key: 'projected_qty', label: 'Projected qty', align: 'right' },
  { key: 'weeks_of_cover', label: 'WOC', align: 'right' },
]

const exceptionRows = computed(() =>
  exceptions.value.map((ex, idx) => ({
    ...ex,
    _key: `${ex.sku}-${ex.warehouse_code}-${ex.week_start}-${idx}`,
  }))
)

async function openExplanation(ex: PlanningException) {
  if (!selectedRunId.value) return
  explanation.value = true
  explanationData.value = null
  explanationLoading.value = true
  layout.openRightPanel(`Explain: ${ex.sku} / ${ex.warehouse_code} — ${ex.week_start}`)
  try {
    const data = await store.fetchSkuWeekExplanation(
      selectedRunId.value,
      ex.sku,
      ex.warehouse_code,
      ex.week_start
    )
    explanationData.value = data
  } finally {
    explanationLoading.value = false
  }
}

async function load() {
  if (!selectedRunId.value) {
    exceptions.value = []
    loading.value = false
    return
  }
  loading.value = true
  try {
    exceptions.value = await store.fetchExceptions(
      selectedRunId.value,
      withinWeeks.value,
      includeLowCover.value
    )
  } finally {
    loading.value = false
  }
}

watch([selectedRunId, withinWeeks, includeLowCover], load)
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
.section-title {
  font-size: 1rem;
  font-weight: 500;
  color: rgb(30 41 59);
}
</style>
