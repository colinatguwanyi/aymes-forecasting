<template>
  <div class="page-content-inner">
    <template v-if="!sku || !warehouseCode">
      <p class="muted">Open this page with <code>sku</code>, <code>warehouse_code</code>, and <code>plan_run_id</code> in the URL (e.g. from Weekly Planning Grid or Inventory Projection).</p>
      <p class="muted">You can also enter them below.</p>
      <section class="content-section controls">
        <div class="form-row">
          <label class="form-label">SKU</label>
          <input v-model="skuInput" class="app-input" placeholder="SKU" style="max-width: 12rem;" />
        </div>
        <div class="form-row">
          <label class="form-label">Warehouse</label>
          <input v-model="warehouseInput" class="app-input" placeholder="Warehouse code" style="max-width: 10rem;" />
        </div>
        <div class="form-row">
          <label class="form-label">Scenario</label>
          <select v-model="planRunIdInput" class="app-select" style="max-width: 18rem;">
            <option :value="null">Select scenario</option>
            <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ formatPlanRunLabel(r) }}</option>
          </select>
        </div>
        <div class="form-row">
          <button type="button" class="app-btn app-btn-primary" @click="goToDetail">Open SKU detail</button>
        </div>
      </section>
    </template>

    <template v-else>
      <header class="content-section sku-header">
        <h2>{{ sku }} / {{ warehouseCode }}</h2>
        <p class="muted">Scenario: {{ selectedPlanRun ? formatPlanRunLabel(selectedPlanRun) : (selectedRunName ?? planRunId) }}</p>
      </header>

      <!-- demand_only: timeline/explanation use modeled ledger — not physical SOH. -->
      <section v-if="isDemandOnlyRun" class="content-section mb-3 p-3 rounded-lg bg-sky-50 border border-sky-200 text-sky-900 text-sm">
        <strong>Demand-only run.</strong> Timeline and explanation use a modeled position (synthetic starts where applicable), not warehouse on-hand. Treat stockout and cover as model signals only.
      </section>

      <div class="tabs">
        <button
          v-for="t in tabs"
          :key="t.id"
          type="button"
          class="tab-btn"
          :class="{ active: activeTab === t.id }"
          @click="activeTab = t.id"
        >{{ t.label }}</button>
      </div>

      <section v-if="activeTab === 'timeline'" class="content-section">
        <div v-if="timelineLoading" class="muted">Loading timeline…</div>
        <template v-else>
          <div
            v-if="projected.length === 0 && plannedOrders.length > 0"
            class="mb-3 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 text-sm"
          >
            <strong>No projected inventory rows</strong> for this SKU and warehouse in this scenario, but
            <strong> planned orders</strong> exist. Usually that means the API returned no matching
            <code>projected_inventory</code> rows (check SKU / warehouse spelling vs the plan) or the plan outputs
            are inconsistent. Try the same scenario on the Weekly Planning Grid; if the grid shows projected qty here
            but this page does not, report it as a bug.
          </div>
          <SkuTimeline
            :projected="projected"
            :planned-orders="plannedOrders"
            :receipts="receipts"
          />
        </template>
      </section>

      <section v-if="activeTab === 'metrics'" class="content-section">
        <p class="muted">WAPE and Bias for this SKU/warehouse (last 12 weeks with actuals).</p>
        <div class="form-row" style="max-width: 20rem;">
          <label class="form-label">Forecast run (train end week)</label>
          <select v-model="metricsRunKey" class="app-select" @change="loadMetrics">
            <option value="">— Select run —</option>
            <option v-for="opt in metricsRunOptions" :key="opt.key" :value="opt.key">{{ opt.label }}</option>
          </select>
        </div>
        <div v-if="metricsLoading" class="muted">Loading…</div>
        <template v-else-if="currentMetric">
          <div class="metrics-panel">
            <dl class="explanation-dl">
              <dt>WAPE</dt>
              <dd>{{ currentMetric.wape != null ? (currentMetric.wape * 100).toFixed(2) + '%' : '—' }}</dd>
              <dt>Bias</dt>
              <dd>{{ currentMetric.bias != null ? currentMetric.bias.toFixed(4) : '—' }}</dd>
              <dt>Eval weeks</dt>
              <dd>{{ currentMetric.eval_weeks ?? '—' }}</dd>
            </dl>
            <span class="metric-badge" :class="wapeBadgeClass">{{ wapeBadgeLabel }}</span>
          </div>
        </template>
        <p v-else-if="metricsRunKey && !metricsLoading" class="muted">No metrics for this run.</p>
      </section>

      <section v-if="activeTab === 'explanation'" class="content-section">
        <div v-if="stockBreakdownLoading" class="muted text-sm mb-3">Loading target &amp; ROP (stock position breakdown)…</div>
        <div v-else-if="stockBreakdownRow" class="stock-target-snippet mb-4">
          <h3 class="explanation-heading">Target &amp; ROP (units)</h3>
          <p class="muted text-sm stock-target-snippet__note">
            These values come from the <strong>stock position breakdown</strong> logic (policy and planning parameters for this scenario), not from new calculations on this page.
            They describe a planning view of target level and reorder point in units, using average weekly demand from this plan run’s demand inputs.
            <template v-if="isDemandOnlyRun">
              For this demand-only run, <strong>projected position</strong> in the week detail below is a <strong>modeled ledger</strong>, not warehouse on-hand truth (see banner above); breakdown on-hand still reflects snapshots where present.
            </template>
          </p>
          <dl class="explanation-dl">
            <dt>Target stock (units)</dt><dd>{{ stockBreakdownRow.target_stock_units }}</dd>
            <dt>Reorder point (units)</dt><dd>{{ stockBreakdownRow.reorder_point_units }}</dd>
            <dt>Avg weekly demand</dt><dd>{{ stockBreakdownRow.avg_weekly_demand }}</dd>
          </dl>
        </div>
        <p v-else-if="!stockBreakdownLoading && planRunId && sku && warehouseCode" class="muted text-sm mb-3">
          No stock position breakdown row for this SKU and warehouse in this run (the breakdown needs projected inventory for the pair).
        </p>
        <p class="muted">Select a week to see the explain-the-forecast breakdown.</p>
        <div class="form-row" style="max-width: 14rem;">
          <label class="form-label">Week</label>
          <select v-model="explanationWeek" class="app-select" @change="loadExplanation">
            <option value="">— Select week —</option>
            <option v-for="w in explanationWeeks" :key="w" :value="w">{{ w }}</option>
          </select>
        </div>
        <div v-if="explanationLoading" class="muted">Loading…</div>
        <template v-else-if="explanationData">
          <h3 class="explanation-heading">Week {{ explanationData.projection?.week_start }}</h3>
          <dl class="explanation-dl" v-if="explanationData.projection">
            <dt>Start qty</dt><dd>{{ explanationData.projection.start_qty ?? '—' }}</dd>
            <dt>Receipts</dt><dd>{{ explanationData.projection.receipts_qty ?? '—' }}</dd>
            <dt>Demand</dt><dd>{{ explanationData.projection.demand_qty ?? '—' }}</dd>
            <template v-if="explanationData.demand_breakdown">
              <dt>Demand composition</dt>
              <dd>
                <span v-if="explanationData.demand_breakdown.OVERRIDE">Override ({{ explanationData.demand_breakdown.reason_code ?? '—' }})</span>
                <template v-else-if="explanationData.demand_breakdown.FORECAST_TOTAL != null">Forecast total</template>
                <template v-else>
                  <span v-if="demandBreakdownIncludedLabel">In: {{ demandBreakdownIncludedLabel }}</span>
                  <span v-if="demandBreakdownExcludedLabel"> · Ex: {{ demandBreakdownExcludedLabel }}</span>
                  <span v-if="explanationData.demand_breakdown.CUSTOMER != null"> · CUSTOMER {{ explanationData.demand_breakdown.CUSTOMER }}</span>
                  <span v-if="explanationData.demand_breakdown.SAMPLES != null"> SAMPLES {{ explanationData.demand_breakdown.SAMPLES }}</span>
                  <span v-if="explanationData.demand_breakdown.ADJUSTMENT != null"> ADJUSTMENT {{ explanationData.demand_breakdown.ADJUSTMENT }}</span>
                  <span v-if="explanationData.demand_includes_samples === false" class="muted"> (samples excluded)</span>
                </template>
              </dd>
            </template>
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
            <dt>Lead time</dt>
            <dd>{{ [explanationData.policy.lead_time_production_weeks, explanationData.policy.lead_time_slot_wait_weeks, explanationData.policy.lead_time_haulage_weeks, explanationData.policy.lead_time_putaway_weeks, explanationData.policy.lead_time_padding_weeks].filter(Boolean).join(' / ') || '—' }}</dd>
          </dl>
          <p class="muted">Forecast method: {{ explanationData.forecast_method }}</p>
        </template>
      </section>

      <section v-if="activeTab === 'parameters'" class="content-section">
        <div v-if="paramsLoading" class="muted">Loading parameters…</div>
        <div v-else-if="policies.length" class="app-table-wrap">
          <table class="app-table">
            <thead>
              <tr>
                <th>Mode</th>
                <th>Target weeks</th>
                <th>Safety stock</th>
                <th>Forecast window</th>
                <th>Lead times (prod/slot/haul/putaway/padding)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in policies" :key="p.id">
                <td>{{ p.mode }}</td>
                <td>{{ p.target_weeks }}</td>
                <td>{{ p.safety_stock_weeks }} ({{ p.safety_stock_method }})</td>
                <td>{{ p.forecast_window_weeks }}</td>
                <td>{{ p.lead_time_production_weeks }} / {{ p.lead_time_slot_wait_weeks }} / {{ p.lead_time_haulage_weeks }} / {{ p.lead_time_putaway_weeks }} / {{ p.lead_time_padding_weeks }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="muted">No planning policy for this SKU/warehouse.</p>
      </section>

      <section v-if="activeTab === 'history'" class="content-section">
        <h3>Demand actuals</h3>
        <div v-if="historyLoading" class="muted">Loading…</div>
        <div v-else-if="demandActuals.length" class="app-table-wrap">
          <table class="app-table">
            <thead>
              <tr>
                <th>Week</th>
                <th>Type</th>
                <th>Qty</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in demandActuals" :key="d.id">
                <td>{{ d.week_start }}</td>
                <td>{{ d.demand_type }}</td>
                <td>{{ d.qty }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="muted">No demand history.</p>
        <h3 style="margin-top: 1rem;">Inventory snapshots</h3>
        <div v-if="!historyLoading && inventorySnapshots.length" class="app-table-wrap">
          <table class="app-table">
            <thead>
              <tr>
                <th>Week</th>
                <th>On hand</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in inventorySnapshots" :key="s.id">
                <td>{{ s.week_start }}</td>
                <td>{{ s.on_hand_qty }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else-if="!historyLoading" class="muted">No inventory snapshots.</p>
      </section>

      <section v-if="activeTab === 'orders'" class="content-section">
        <div v-if="ordersLoading" class="muted">Loading…</div>
        <div v-else-if="plannedOrders.length" class="app-table-wrap">
          <table class="app-table">
            <thead>
              <tr>
                <th>Week start</th>
                <th>Order qty</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="o in plannedOrders" :key="o.id">
                <td>{{ o.week_start }}</td>
                <td>{{ o.order_qty }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="muted">No planned orders for this scenario.</p>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePlanningStore } from '@/stores/planning'
import { useAdminStore } from '@/stores/admin'
import api, {
  formatPlanRunLabel,
  planRunPlanningMode,
  type SkuWeekExplanation,
  type PlanningPolicy,
  type ProjectedInventory,
  type PlannedOrder,
  type Receipt,
  type DemandActual,
  type InventorySnapshot,
  type StockPositionBreakdown,
} from '@/api/client'
import SkuTimeline from '@/components/SkuTimeline.vue'

interface ForecastMetricRow {
  model_name: string
  model_version: string
  train_end_week_start: string
  sku: string
  warehouse_code: string
  eval_weeks?: number | null
  wape: number | null
  bias: number | null
}

const route = useRoute()
const router = useRouter()
const store = usePlanningStore()
const adminStore = useAdminStore()

const tabs = [
  { id: 'timeline', label: 'Timeline' },
  { id: 'explanation', label: 'Explanation' },
  { id: 'metrics', label: 'Forecast metrics' },
  { id: 'parameters', label: 'Parameters' },
  { id: 'history', label: 'History' },
  { id: 'orders', label: 'Orders' },
]

const skuInput = ref('')
const warehouseInput = ref('')
const planRunIdInput = ref<number | null>(null)

const sku = computed(() => (route.query.sku as string) || skuInput.value || '')
const warehouseCode = computed(() => (route.query.warehouse_code as string) || warehouseInput.value || '')
const planRunId = computed(() => {
  const q = route.query.plan_run_id
  if (typeof q === 'string' && q) return parseInt(q, 10)
  return planRunIdInput.value ?? null
})

const activeTab = ref('timeline')
const projected = ref<ProjectedInventory[]>([])
const plannedOrders = ref<PlannedOrder[]>([])
const receipts = ref<Receipt[]>([])
const demandActuals = ref<DemandActual[]>([])
const inventorySnapshots = ref<InventorySnapshot[]>([])
const policies = ref<PlanningPolicy[]>([])
const timelineLoading = ref(false)
const ordersLoading = ref(false)
const historyLoading = ref(false)
const paramsLoading = ref(false)
const explanationWeek = ref('')
const explanationData = ref<SkuWeekExplanation | null>(null)
const explanationLoading = ref(false)
const stockBreakdownRow = ref<StockPositionBreakdown | null>(null)
const stockBreakdownLoading = ref(false)
const forecastMetricsRows = ref<ForecastMetricRow[]>([])
const metricsLoading = ref(false)
const metricsRunKey = ref('')

const planRuns = computed(() => store.planRuns)
const selectedPlanRun = computed(() => {
  const id = planRunId.value
  if (id == null) return null
  return store.planRuns.find((x) => x.id === id) ?? null
})
const isDemandOnlyRun = computed(
  () => selectedPlanRun.value != null && planRunPlanningMode(selectedPlanRun.value) === 'demand_only'
)
const selectedRunName = computed(() => selectedPlanRun.value?.scenario_name ?? null)
const explanationWeeks = computed(() => {
  const weeks = new Set(projected.value.map((p) => p.week_start))
  return Array.from(weeks).sort()
})

const demandBreakdownIncludedLabel = computed(() => {
  const b = explanationData.value?.demand_breakdown as Record<string, unknown> | undefined
  const inc = b?.included
  return Array.isArray(inc) ? (inc as string[]).join(', ') : ''
})
const demandBreakdownExcludedLabel = computed(() => {
  const b = explanationData.value?.demand_breakdown as Record<string, unknown> | undefined
  const exc = b?.excluded
  return Array.isArray(exc) ? (exc as string[]).join(', ') : ''
})

const metricsRunOptions = computed(() => {
  const seen = new Set<string>()
  const opts: { key: string; label: string }[] = []
  for (const m of forecastMetricsRows.value) {
    const key = `${m.model_name}|${m.model_version}|${m.train_end_week_start}`
    if (!seen.has(key)) {
      seen.add(key)
      opts.push({ key, label: `${m.model_name} ${m.model_version} — ${m.train_end_week_start}` })
    }
  }
  opts.sort((a, b) => b.key.localeCompare(a.key))
  return opts
})

const currentMetric = computed(() => {
  if (!metricsRunKey.value) return null
  const [model_name, model_version, train_end_week_start] = metricsRunKey.value.split('|')
  return forecastMetricsRows.value.find(
    (m) =>
      m.model_name === model_name &&
      m.model_version === model_version &&
      m.train_end_week_start === train_end_week_start
  ) ?? null
})

const wapeBadgeLabel = computed(() => {
  const w = currentMetric.value?.wape
  if (w == null) return '—'
  if (w < 0.2) return 'Good'
  if (w < 0.4) return 'OK'
  return 'Poor'
})

const wapeBadgeClass = computed(() => {
  const w = currentMetric.value?.wape
  if (w == null) return 'metric-badge--none'
  if (w < 0.2) return 'metric-badge--good'
  if (w < 0.4) return 'metric-badge--ok'
  return 'metric-badge--poor'
})

function goToDetail() {
  if (!skuInput.value || !warehouseInput.value || !planRunIdInput.value) return
  router.push({
    path: '/sku-detail',
    query: {
      sku: skuInput.value,
      warehouse_code: warehouseInput.value,
      plan_run_id: String(planRunIdInput.value),
    },
  })
}

async function loadTimeline() {
  if (!sku.value || !warehouseCode.value || !planRunId.value) return
  timelineLoading.value = true
  try {
    const [proj, orders, recs] = await Promise.all([
      store.fetchProjectedInventory(planRunId.value, sku.value, warehouseCode.value),
      store.fetchPlannedOrders(planRunId.value, sku.value, warehouseCode.value),
      store.fetchReceipts(sku.value, warehouseCode.value),
    ])
    projected.value = proj
    plannedOrders.value = orders
    receipts.value = recs
  } finally {
    timelineLoading.value = false
  }
}

async function loadOrders() {
  if (!sku.value || !warehouseCode.value || !planRunId.value) return
  ordersLoading.value = true
  try {
    plannedOrders.value = await store.fetchPlannedOrders(planRunId.value, sku.value, warehouseCode.value)
  } finally {
    ordersLoading.value = false
  }
}

async function loadHistory() {
  if (!sku.value || !warehouseCode.value) return
  historyLoading.value = true
  try {
    const [demand, snapshots] = await Promise.all([
      store.fetchDemandActuals(sku.value, warehouseCode.value),
      store.fetchInventorySnapshots(sku.value, warehouseCode.value),
    ])
    demandActuals.value = demand
    inventorySnapshots.value = snapshots
  } finally {
    historyLoading.value = false
  }
}

async function loadParameters() {
  if (!sku.value || !warehouseCode.value) return
  paramsLoading.value = true
  try {
    policies.value = await adminStore.fetchPlanningPolicies(sku.value, warehouseCode.value)
  } finally {
    paramsLoading.value = false
  }
}

async function loadExplanation() {
  if (!explanationWeek.value || !planRunId.value) return
  explanationLoading.value = true
  explanationData.value = null
  try {
    explanationData.value = await store.fetchSkuWeekExplanation(
      planRunId.value,
      sku.value,
      warehouseCode.value,
      explanationWeek.value
    )
  } finally {
    explanationLoading.value = false
  }
}

async function loadStockBreakdownSnippet() {
  if (!sku.value || !warehouseCode.value || !planRunId.value) {
    stockBreakdownRow.value = null
    return
  }
  stockBreakdownLoading.value = true
  stockBreakdownRow.value = null
  try {
    const rows = await store.fetchStockPositionBreakdown(planRunId.value, {
      sku: sku.value,
      warehouseCode: warehouseCode.value,
      limit: 5,
    })
    stockBreakdownRow.value = rows[0] ?? null
  } finally {
    stockBreakdownLoading.value = false
  }
}

async function loadMetrics() {
  if (!sku.value || !warehouseCode.value) return
  metricsLoading.value = true
  try {
    const { data } = await api.get<ForecastMetricRow[]>('/forecast/metrics', {
      params: { sku: sku.value, warehouse_code: warehouseCode.value, limit: 200 },
    })
    forecastMetricsRows.value = data
    if (data.length && !metricsRunKey.value) {
      const first = data[0]
      metricsRunKey.value = `${first.model_name}|${first.model_version}|${first.train_end_week_start}`
    }
  } finally {
    metricsLoading.value = false
  }
}

watch([sku, warehouseCode, planRunId], () => {
  loadTimeline()
  loadOrders()
  loadHistory()
  loadParameters()
  explanationWeek.value = ''
  explanationData.value = null
  stockBreakdownRow.value = null
  if (activeTab.value === 'explanation') loadStockBreakdownSnippet()
}, { immediate: true })

watch(activeTab, (tab) => {
  if (tab === 'orders' && plannedOrders.value.length === 0) loadOrders()
  if (tab === 'history') loadHistory()
  if (tab === 'parameters') loadParameters()
  if (tab === 'metrics') loadMetrics()
  if (tab === 'explanation') loadStockBreakdownSnippet()
})

onMounted(async () => {
  await store.fetchPlanRuns()
  if (store.planRuns.length && !planRunIdInput.value) planRunIdInput.value = store.planRuns[0].id
  if (sku.value && warehouseCode.value && planRunId.value) {
    await loadTimeline()
    if (explanationWeeks.value.length) {
      explanationWeek.value = explanationWeeks.value[0]
      await loadExplanation()
    }
  }
})
</script>

<style scoped>
.controls { display: flex; flex-wrap: wrap; gap: 0.75rem 1.5rem; align-items: flex-end; }
.form-row { display: flex; flex-direction: column; gap: 0.25rem; }
.form-label { font-size: 0.8125rem; color: var(--muted); }
.sku-header { margin-bottom: 0.5rem; }
.sku-header h2 { margin-bottom: 0.25rem; }
.tabs { display: flex; gap: 2px; margin-bottom: 1rem; border-bottom: 1px solid var(--border); }
.tab-btn {
  padding: 0.5rem 1rem;
  border: none;
  background: transparent;
  color: var(--muted);
  font-size: 0.875rem;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.tab-btn:hover { color: var(--text); }
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 500; }
.explanation-heading { font-size: 0.9375rem; font-weight: 500; margin: 0.75rem 0 0.25rem; }
.explanation-dl { margin: 0; }
.explanation-dl dt { font-weight: 500; color: var(--muted); margin-top: 0.35rem; }
.explanation-dl dd { margin: 0 0 0 0.5rem; }
.metrics-panel { display: flex; align-items: flex-start; gap: 1rem; flex-wrap: wrap; }
.metric-badge {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.875rem;
  font-weight: 500;
}
.metric-badge--good { background: #d4edda; color: #155724; }
.metric-badge--ok { background: #fff3cd; color: #856404; }
.metric-badge--poor { background: #f8d7da; color: #721c24; }
.metric-badge--none { background: var(--hover); color: var(--muted); }
.stock-target-snippet {
  padding: 0.75rem 1rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--main-bg);
}
.stock-target-snippet__note { margin: 0 0 0.5rem; line-height: 1.45; }
.text-sm { font-size: 0.8125rem; }
code { font-size: 0.8125rem; background: var(--hover); padding: 0.1rem 0.3rem; border-radius: 2px; }
</style>
