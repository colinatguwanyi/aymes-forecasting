<template>
  <div class="page-content-inner">
    <p class="muted">CSV exports for projected inventory and planned orders by scenario.</p>

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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { usePlanningStore } from '@/stores/planning'

const store = usePlanningStore()
const planRuns = computed(() => store.planRuns)
const selectedRunId = ref<number | null>(null)
const selectedRunIdOrders = ref<number | null>(null)

const projectedInventoryExportUrl = computed(() =>
  selectedRunId.value ? `/api/exports/projected-inventory?plan_run_id=${selectedRunId.value}` : '#'
)
const plannedOrdersExportUrl = computed(() =>
  selectedRunIdOrders.value ? `/api/exports/planned-orders?plan_run_id=${selectedRunIdOrders.value}` : '#'
)

onMounted(() => store.fetchPlanRuns())
</script>

<style scoped>
.form-row { margin-bottom: 0.5rem; }
.form-label { display: block; font-size: 0.8125rem; color: var(--muted); margin-bottom: 0.25rem; }
.app-btn { text-decoration: none; display: inline-block; margin-top: 0.25rem; }
</style>
