<template>
  <div class="page-content-inner">
    <p class="muted">Decision-focused summary: run a plan, view stockout risk for the next 8–13 weeks, and top SKUs at risk. For freeze, recalculate, compare scenarios, and forecast health, go to <router-link to="/planning/scenario-manager" class="text-blue-600 hover:underline">Advanced Planning</router-link>.</p>

    <section v-if="dataHealth && !dataHealthLoading" class="data-readiness-strip">
      <span>Demand: {{ dataHealth.demand?.latest_week ?? '—' }}</span>
      <span>SOH: {{ dataHealth.soh?.latest_week ?? '—' }}</span>
      <span>Policies: {{ dataHealth.planning_policies?.count ?? 0 }} ok</span>
      <router-link v-if="!dataHealth.ready_to_plan" to="/setup" class="text-amber-600 hover:underline font-medium">Complete setup →</router-link>
    </section>

    <section v-if="planCreatedSuccess" class="content-section plan-created-banner">
      <strong>Plan created successfully.</strong> {{ planCreatedSuccess }} Select it below to see stockout risk, or <router-link to="/inventory-projection" class="text-blue-600 hover:underline font-medium">view projections in Inventory Projection</router-link>.
    </section>

    <section v-if="planRuns.length && !selectedRunId" class="content-section info-banner">
      You have {{ planRuns.length }} plan run{{ planRuns.length === 1 ? '' : 's' }}. Select one below to see stockout risk, or <router-link to="/inventory-projection" class="text-blue-600 hover:underline">go to Inventory Projection</router-link> to view week-by-week data.
    </section>

    <section v-if="loading" class="content-section">Loading...</section>
    <template v-else>
      <section class="content-section">
        <h2>Run a scenario</h2>
        <p class="text-sm text-slate-600 mb-3">Create a new plan run. Check <router-link to="/reports/data-health" class="text-blue-600 hover:underline">Data Health</router-link> if the run fails.</p>
        <form @submit.prevent="runScenario" class="form-inline plan-run-form">
          <div>
            <button
              type="submit"
              class="app-btn app-btn-primary"
              :disabled="runPlanLoading || !readyToPlan"
              :title="readyToPlan ? 'Create a new plan run.' : 'Complete setup first.'"
            >
              {{ runPlanLoading ? 'Running…' : runPlanButtonLabel }}
            </button>
            <p class="text-xs text-slate-500 mt-1">Uses Sales Out (demand_actuals) and latest SOH.</p>
          </div>
          <details class="ml-3">
            <summary class="text-sm text-slate-600 cursor-pointer hover:text-slate-800">Advanced run options</summary>
            <div class="form-inline plan-run-form mt-2">
              <label class="form-label">Run name</label>
              <input v-model="runName" type="text" class="app-input" placeholder="e.g. Q1 baseline" style="max-width: 14rem;" title="Optional. If blank, uses scenario + date (e.g. baseline 2025-02-24)." />
              <label class="form-label">Scenario</label>
              <select v-model="scenarioName" class="app-select" required style="max-width: 12rem;">
                <option value="baseline">Baseline</option>
                <option value="blended">Blended</option>
                <option value="actuals">Actuals</option>
                <option value="Conservative">Conservative</option>
                <option value="Aggressive">Aggressive</option>
                <option value="Promo uplift">Promo uplift</option>
              </select>
              <label class="form-label">Demand source</label>
              <select v-model="demandSource" class="app-select" style="max-width: 14rem;">
                <option value="actuals">Actuals (Sales Out)</option>
                <option value="baseline">Baseline forecast</option>
                <option value="blended">Blended</option>
              </select>
              <label class="form-label">Freeze weeks</label>
              <input v-model.number="freezeWeeks" type="number" min="0" max="52" class="app-input" style="max-width: 4rem;" />
            </div>
          </details>
        </form>
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
        <select v-model="selectedRunId" class="app-select" style="max-width: 20rem; margin-bottom: 0.5rem;" title="Choose a plan run to see its stockout risk.">
          <option :value="null">Select scenario</option>
          <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ formatPlanRunLabel(r) }}</option>
        </select>
        <div v-if="selectedRunId && topRisks.length" class="app-table-wrap">
          <table class="app-table">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Warehouse</th>
                <th>Weeks at risk</th>
                <th>Min weeks of cover</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(row, i) in topRisks"
                :key="i"
                class="top-risk-row"
                @click="goToPlanningGrid(row)"
              >
                <td>{{ row.sku }}</td>
                <td>{{ row.warehouse_code }}</td>
                <td>{{ row.stockoutWeeks }}</td>
                <td>{{ row.minWoc }}</td>
                <td>
                  <router-link
                    :to="planningGridLink(row)"
                    class="view-icon"
                    title="View in Weekly Planning Grid"
                    @click.stop
                  >View</router-link>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else-if="selectedRunId && !topRisks.length" class="muted">No stockout risk in projection.</p>
      </section>

      <section class="content-section">
        <h2>Plan runs</h2>
        <p class="text-sm text-slate-600 mb-2">Click a row to select it. Selected run drives stockout risk above. For advanced actions, go to <router-link to="/planning/scenario-manager" class="text-blue-600 hover:underline">Advanced Planning</router-link>.</p>
        <div class="app-table-wrap">
          <table class="app-table">
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Demand source</th>
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
                <td>{{ formatPlanRunLabel(r) }}</td>
                <td>{{ r.demand_source ?? 'actuals' }}</td>
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
import { useRouter } from 'vue-router'
import { usePlanningStore } from '@/stores/planning'
import type { ProjectedInventory } from '@/api/client'
import { formatPlanRunLabel, fetchPlanningReadiness } from '@/api/client'
import { useBannerStore } from '@/stores/banner'
import api from '@/api/client'

interface DataHealth {
  demand: { latest_week: string | null }
  soh: { latest_week: string | null }
  planning_policies: { count: number }
  ready_to_plan: boolean
}

const router = useRouter()
const store = usePlanningStore()
const bannerStore = useBannerStore()
const loading = ref(true)
const runPlanLoading = ref(false)
const planCreatedSuccess = ref('')
const runName = ref('')
const scenarioName = ref('baseline')
const demandSource = ref<'actuals' | 'baseline' | 'blended'>('actuals')
const freezeWeeks = ref(4)
const selectedRunId = ref<number | null>(null)
const dataHealth = ref<DataHealth | null>(null)
const dataHealthLoading = ref(true)

const planRuns = computed(() => store.planRuns)
const readyToPlan = computed(() => !!dataHealth.value?.ready_to_plan)
const runPlanButtonLabel = computed(() => {
  const scenario = scenarioName.value.charAt(0).toUpperCase() + scenarioName.value.slice(1)
  const demand = demandSource.value === 'actuals' ? 'Actuals' : demandSource.value === 'baseline' ? 'Baseline' : 'Blended'
  return `Run plan (${scenario} • ${demand} • Freeze ${freezeWeeks.value}w)`
})

function planningGridLink(row: { sku: string; warehouse_code: string }) {
  return {
    path: '/planning-grid',
    query: {
      plan_run_id: String(selectedRunId.value),
      sku: row.sku,
      warehouse_code: row.warehouse_code,
    },
  }
}

function goToPlanningGrid(row: { sku: string; warehouse_code: string }) {
  router.push(planningGridLink(row))
}
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

async function runScenario() {
  runPlanLoading.value = true
  planCreatedSuccess.value = ''
  const notes = runName.value.trim() || `${scenarioName.value} ${new Date().toISOString().slice(0, 10)}`
  try {
    const run = await store.runPlan(scenarioName.value, undefined, demandSource.value, freezeWeeks.value, notes)
    await store.fetchPlanRuns()
    if (store.planRuns.length) selectedRunId.value = store.planRuns[0].id
    const diag = await fetchPlanningReadiness(run.id)
    const proj = diag.stats.projected_inventory_rows_for_run
    const orders = diag.stats.planned_orders_rows_for_run
    planCreatedSuccess.value = `"${run.scenario_name}" created.`
    bannerStore.add({
      type: 'success',
      title: 'Plan run created',
      message: `plan_run_id: ${run.id} — Projected inventory: ${proj} rows, Planned orders: ${orders} rows.`,
    })
    setTimeout(() => { planCreatedSuccess.value = '' }, 8000)
  } finally {
    runPlanLoading.value = false
  }
}

async function loadDataHealth() {
  dataHealthLoading.value = true
  try {
    const { data } = await api.get<DataHealth>('/v1/reports/data-health')
    dataHealth.value = data
  } finally {
    dataHealthLoading.value = false
  }
}

onMounted(async () => {
  await Promise.all([store.fetchPlanRuns(), loadDataHealth()])
  if (store.planRuns.length && selectedRunId.value == null) selectedRunId.value = store.planRuns[0].id
  loading.value = false
})

watch(selectedRunId, async (id) => {
  if (id) {
    projected.value = await store.fetchProjectedInventory(id)
  } else {
    projected.value = []
  }
}, { immediate: true })
</script>

<style scoped>
.form-inline { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
.risk-summary p { margin: 0.25rem 0; font-size: 0.875rem; }
.plan-run-form .form-label { margin-left: 0.5rem; margin-right: 0.25rem; }
.form-label { font-size: 0.875rem; }
.app-table tbody tr { cursor: pointer; }
.app-table tbody tr.row-selected { background: var(--border); }
.plan-created-banner {
  background: rgb(220 252 231);
  border: 1px solid rgb(134 239 172);
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
  color: rgb(22 101 52);
}
.info-banner {
  background: rgb(239 246 255);
  border: 1px solid rgb(191 219 254);
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
  color: rgb(30 64 175);
}
.data-readiness-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem 1.5rem;
  align-items: center;
  padding: 0.5rem 0.75rem;
  background: rgb(248 250 252);
  border: 1px solid rgb(226 232 240);
  border-radius: 0.375rem;
  font-size: 0.8125rem;
  color: rgb(71 85 105);
  margin-bottom: 1rem;
}
.top-risk-row {
  cursor: pointer;
}
.top-risk-row:hover {
  background: rgb(248 250 252);
}
.view-icon {
  font-size: 0.75rem;
  color: rgb(59 130 246);
  text-decoration: none;
}
.view-icon:hover {
  text-decoration: underline;
}
</style>
