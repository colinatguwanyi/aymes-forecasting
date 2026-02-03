<template>
  <div class="page-content-inner">
    <p class="muted">What needs attention: projected stockouts and low cover within the horizon. Click a row to open the explanation panel or go to SKU detail.</p>

    <section class="content-section controls">
      <div class="form-row">
        <label class="form-label">Scenario</label>
        <select v-model="selectedRunId" class="app-select" style="max-width: 18rem;">
          <option :value="null">Select scenario</option>
          <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
        </select>
      </div>
      <div class="form-row">
        <label class="form-label">Within weeks</label>
        <select v-model="withinWeeks" class="app-select" style="max-width: 6rem;">
          <option :value="4">4</option>
          <option :value="8">8</option>
          <option :value="12">12</option>
          <option :value="26">26</option>
          <option :value="52">52</option>
        </select>
      </div>
      <div class="form-row form-row-checkbox">
        <label class="checkbox-label">
          <input type="checkbox" v-model="includeLowCover" />
          Include low cover (warnings)
        </label>
      </div>
    </section>

    <section v-if="loading" class="content-section">Loading...</section>
    <template v-else>
      <section class="content-section">
        <h2>Exceptions ({{ exceptions.length }})</h2>
        <div v-if="exceptions.length" class="app-table-wrap">
          <table class="app-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>SKU</th>
                <th>Warehouse</th>
                <th>Week</th>
                <th>Message</th>
                <th>Projected qty</th>
                <th>WOC</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(ex, idx) in exceptions"
                :key="`${ex.sku}-${ex.warehouse_code}-${ex.week_start}-${idx}`"
                :class="['row-clickable', ex.severity === 'error' ? 'row-status-error' : 'row-status-warning']"
                role="button"
                tabindex="0"
                @click="openExplanation(ex)"
                @keydown.enter="openExplanation(ex)"
                @keydown.space.prevent="openExplanation(ex)"
              >
                <td>{{ ex.type }}</td>
                <td>
                  <router-link
                    :to="{ path: '/sku-detail', query: { sku: ex.sku, warehouse_code: ex.warehouse_code, plan_run_id: String(selectedRunId) } }"
                    class="cell-link"
                    @click.stop
                  >{{ ex.sku }}</router-link>
                </td>
                <td>{{ ex.warehouse_code }}</td>
                <td>{{ ex.week_start }}</td>
                <td>{{ ex.message }}</td>
                <td>{{ ex.projected_qty ?? '—' }}</td>
                <td>{{ ex.weeks_of_cover ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="muted">No exceptions in this horizon. Select a scenario and run a plan if needed.</p>
      </section>
    </template>

    <Teleport to="#right-panel-body">
      <div v-if="explanation" class="explanation-panel">
        <template v-if="explanationLoading">Loading…</template>
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
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useLayoutStore } from '@/stores/layout'
import { usePlanningStore } from '@/stores/planning'
import type { PlanningException, SkuWeekExplanation } from '@/api/client'

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
.controls { display: flex; flex-wrap: wrap; gap: 0.75rem 1.5rem; align-items: flex-end; }
.form-row { display: flex; flex-direction: column; gap: 0.25rem; }
.form-label { font-size: 0.8125rem; color: var(--muted); }
.form-row-checkbox { justify-content: center; }
.checkbox-label { font-size: 0.875rem; display: flex; align-items: center; gap: 0.5rem; cursor: pointer; }
.row-clickable { cursor: pointer; }
.row-clickable:hover { background: var(--hover); }
.cell-link { color: var(--accent); text-decoration: none; }
.cell-link:hover { text-decoration: underline; }
.explanation-panel { font-size: 0.875rem; }
.explanation-heading { font-size: 0.9375rem; font-weight: 500; margin: 0.75rem 0 0.25rem; }
.explanation-dl { margin: 0; }
.explanation-dl dt { font-weight: 500; color: var(--muted); margin-top: 0.35rem; }
.explanation-dl dd { margin: 0 0 0 0.5rem; }
</style>
