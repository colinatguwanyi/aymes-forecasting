<template>
  <div class="exports-view">
    <h1>Exports</h1>
    <p class="muted">CSV exports for projected inventory and planned orders by scenario.</p>

    <section class="card">
      <h2>Projected inventory</h2>
      <select v-model="selectedRunId" class="select">
        <option :value="null">Select scenario</option>
        <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
      </select>
      <a v-if="selectedRunId" :href="projectedInventoryExportUrl" class="btn" download>Download projected inventory CSV</a>
    </section>

    <section class="card">
      <h2>Planned orders</h2>
      <select v-model="selectedRunIdOrders" class="select">
        <option :value="null">Select scenario</option>
        <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
      </select>
      <a v-if="selectedRunIdOrders" :href="plannedOrdersExportUrl" class="btn" download>Download planned orders CSV</a>
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
.exports-view { display: flex; flex-direction: column; gap: 1rem; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 1rem; }
.card h2 { margin: 0 0 0.5rem 0; font-size: 1rem; }
.select { padding: 0.35rem 0.5rem; border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg); color: var(--text); margin-right: 0.5rem; }
.btn { display: inline-block; padding: 0.35rem 0.75rem; background: var(--accent); color: var(--bg); border-radius: var(--radius); text-decoration: none; margin-top: 0.5rem; }
.muted { color: var(--muted); margin: 0.5rem 0; }
</style>
