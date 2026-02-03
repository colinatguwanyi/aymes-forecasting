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
            <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
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
        <p class="muted">Scenario: {{ selectedRunName ?? planRunId }}</p>
      </header>

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
        <SkuTimeline
          v-else
          :projected="projected"
          :planned-orders="plannedOrders"
          :receipts="receipts"
        />
      </section>

      <section v-if="activeTab === 'explanation'" class="content-section">
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
import SkuTimeline from '@/components/SkuTimeline.vue'
import type {
  SkuWeekExplanation,
  PlanningPolicy,
  ProjectedInventory,
  PlannedOrder,
  Receipt,
  DemandActual,
  InventorySnapshot,
} from '@/api/client'

const route = useRoute()
const router = useRouter()
const store = usePlanningStore()
const adminStore = useAdminStore()

const tabs = [
  { id: 'timeline', label: 'Timeline' },
  { id: 'explanation', label: 'Explanation' },
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

const planRuns = computed(() => store.planRuns)
const selectedRunName = computed(() => {
  const id = planRunId.value
  if (id == null) return null
  const r = store.planRuns.find((x) => x.id === id)
  return r?.scenario_name ?? null
})
const explanationWeeks = computed(() => {
  const weeks = new Set(projected.value.map((p) => p.week_start))
  return Array.from(weeks).sort()
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

watch([sku, warehouseCode, planRunId], () => {
  loadTimeline()
  loadOrders()
  loadHistory()
  loadParameters()
  explanationWeek.value = ''
  explanationData.value = null
}, { immediate: true })

watch(activeTab, (tab) => {
  if (tab === 'orders' && plannedOrders.value.length === 0) loadOrders()
  if (tab === 'history') loadHistory()
  if (tab === 'parameters') loadParameters()
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
code { font-size: 0.8125rem; background: var(--hover); padding: 0.1rem 0.3rem; border-radius: 2px; }
</style>
