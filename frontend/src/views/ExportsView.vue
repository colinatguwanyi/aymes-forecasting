<template>
  <div class="page-content-inner">
    <p class="muted">CSV exports: projected inventory, planned orders, exception list, and SKU explanation report by scenario.</p>

    <section class="content-section">
      <h2>Projected inventory</h2>
      <div class="form-row">
        <label class="form-label">Scenario</label>
        <select v-model="selectedRunId" class="app-select" style="max-width: 18rem;">
          <option :value="null">Select scenario</option>
          <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
        </select>
      </div>
      <a v-if="selectedRunId" :href="projectedInventoryExportUrl" class="app-btn app-btn-primary" download>Download projected inventory CSV</a>
    </section>

    <section class="content-section">
      <h2>Planned orders</h2>
      <div class="form-row">
        <label class="form-label">Scenario</label>
        <select v-model="selectedRunIdOrders" class="app-select" style="max-width: 18rem;">
          <option :value="null">Select scenario</option>
          <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
        </select>
      </div>
      <a v-if="selectedRunIdOrders" :href="plannedOrdersExportUrl" class="app-btn app-btn-primary" download>Download planned orders CSV</a>
    </section>

    <section class="content-section">
      <h2>Exception list</h2>
      <p class="muted">Stockout and low-cover exceptions within the horizon.</p>
      <div class="form-row">
        <label class="form-label">Scenario</label>
        <select v-model="selectedRunIdExceptions" class="app-select" style="max-width: 18rem;">
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
      <a v-if="selectedRunIdExceptions" :href="exceptionsExportUrl" class="app-btn app-btn-primary" download>Download exception list CSV</a>
    </section>

    <section class="content-section">
      <h2>SKU explanation report</h2>
      <p class="muted">Explanation-style CSV: policy and projection per SKU-week. Optionally filter by SKU and warehouse.</p>
      <div class="form-row">
        <label class="form-label">Scenario</label>
        <select v-model="selectedRunIdReport" class="app-select" style="max-width: 18rem;">
          <option :value="null">Select scenario</option>
          <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
        </select>
      </div>
      <div class="form-row">
        <label class="form-label">SKU (optional)</label>
        <input v-model="reportSku" class="app-input" placeholder="All SKUs" style="max-width: 12rem;" />
      </div>
      <div class="form-row">
        <label class="form-label">Warehouse (optional)</label>
        <input v-model="reportWarehouse" class="app-input" placeholder="All warehouses" style="max-width: 10rem;" />
      </div>
      <a v-if="selectedRunIdReport" :href="skuExplanationReportUrl" class="app-btn app-btn-primary" download>Download SKU explanation report CSV</a>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { usePlanningStore } from '@/stores/planning'

const store = usePlanningStore()
const planRuns = computed(() => store.planRuns)
const selectedRunId = ref<number | null>(null)
const selectedRunIdOrders = ref<number | null>(null)
const selectedRunIdExceptions = ref<number | null>(null)
const withinWeeks = ref(12)
const selectedRunIdReport = ref<number | null>(null)
const reportSku = ref('')
const reportWarehouse = ref('')

const projectedInventoryExportUrl = computed(() =>
  selectedRunId.value ? `/api/exports/projected-inventory?plan_run_id=${selectedRunId.value}` : '#'
)
const plannedOrdersExportUrl = computed(() =>
  selectedRunIdOrders.value ? `/api/exports/planned-orders?plan_run_id=${selectedRunIdOrders.value}` : '#'
)
const exceptionsExportUrl = computed(() => {
  if (!selectedRunIdExceptions.value) return '#'
  return `/api/exports/exceptions?plan_run_id=${selectedRunIdExceptions.value}&within_weeks=${withinWeeks.value}&include_low_cover=true`
})
const skuExplanationReportUrl = computed(() => {
  if (!selectedRunIdReport.value) return '#'
  const params = new URLSearchParams({ plan_run_id: String(selectedRunIdReport.value) })
  if (reportSku.value.trim()) params.set('sku', reportSku.value.trim())
  if (reportWarehouse.value.trim()) params.set('warehouse_code', reportWarehouse.value.trim())
  return `/api/exports/sku-explanation-report?${params}`
})

onMounted(() => store.fetchPlanRuns())
</script>

<style scoped>
.form-row { margin-bottom: 0.5rem; }
.form-label { display: block; font-size: 0.8125rem; color: var(--muted); margin-bottom: 0.25rem; }
.app-btn { text-decoration: none; display: inline-block; margin-top: 0.25rem; }
</style>
