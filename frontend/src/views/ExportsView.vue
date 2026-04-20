<template>
  <div class="page-shell space-y-6">
    <header class="page-header">
      <h1>Exports</h1>
      <p class="muted mt-1">CSV exports: projected inventory, planned orders, exception list, and SKU explanation report by scenario.</p>
    </header>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <section class="card card-body">
        <h3 class="section-title mb-2">Projected inventory</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label class="form-label">Scenario</label>
            <select v-model="selectedRunId" class="select w-full max-w-xs">
              <option :value="null">Select scenario</option>
              <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
            </select>
          </div>
        </div>
        <a v-if="selectedRunId" :href="projectedInventoryExportUrl" class="btn-primary inline-block mt-3" download>Download projected inventory CSV</a>
      </section>

      <section class="card card-body">
        <h3 class="section-title mb-2">Planned orders</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label class="form-label">Scenario</label>
            <select v-model="selectedRunIdOrders" class="select w-full max-w-xs">
              <option :value="null">Select scenario</option>
              <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
            </select>
          </div>
        </div>
        <a v-if="selectedRunIdOrders" :href="plannedOrdersExportUrl" class="btn-primary inline-block mt-3" download>Download planned orders CSV</a>
      </section>

      <section class="card card-body md:col-span-2">
        <h3 class="section-title mb-2">Exception list</h3>
        <p class="text-sm text-slate-600 mb-3">Stockout and low-cover exceptions within the horizon.</p>
        <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div>
            <label class="form-label">Scenario</label>
            <select v-model="selectedRunIdExceptions" class="select w-full max-w-xs">
              <option :value="null">Select scenario</option>
              <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
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
        </div>
        <a v-if="selectedRunIdExceptions" :href="exceptionsExportUrl" class="btn-primary inline-block mt-3" download>Download exception list CSV</a>
      </section>

      <section class="card card-body md:col-span-2">
        <h3 class="section-title mb-2">SKU explanation report</h3>
        <p class="text-sm text-slate-600 mb-3">Explanation-style CSV: policy and projection per SKU-week. Optionally filter by SKU and warehouse.</p>
        <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div>
            <label class="form-label">Scenario</label>
            <select v-model="selectedRunIdReport" class="select w-full max-w-xs">
              <option :value="null">Select scenario</option>
              <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
            </select>
          </div>
          <div>
            <label class="form-label">SKU (optional)</label>
            <input v-model="reportSku" class="input w-full max-w-xs" placeholder="All SKUs" />
          </div>
          <div>
            <label class="form-label">Warehouse (optional)</label>
            <input v-model="reportWarehouse" class="input w-full max-w-xs" placeholder="All warehouses" />
          </div>
        </div>
        <a v-if="selectedRunIdReport" :href="skuExplanationReportUrl" class="btn-primary inline-block mt-3" download>Download SKU explanation report CSV</a>
      </section>
    </div>
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
.section-title {
  font-size: 1rem;
  font-weight: 500;
  color: rgb(30 41 59);
}
</style>
