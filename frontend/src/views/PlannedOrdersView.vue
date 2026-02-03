<template>
  <div class="planned-orders">
    <h1>Planned Orders</h1>
    <p class="muted">Exportable table by scenario.</p>

    <section class="card controls">
      <label>Scenario</label>
      <select v-model="selectedRunId" class="select">
        <option :value="null">Select scenario</option>
        <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
      </select>
      <a v-if="selectedRunId" :href="exportUrl" class="btn" download>Export CSV</a>
    </section>

    <section class="card">
      <table v-if="orders.length" class="table">
        <thead>
          <tr>
            <th>Week start</th>
            <th>SKU</th>
            <th>Warehouse</th>
            <th>Order qty</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="o in orders" :key="o.id">
            <td>{{ o.week_start }}</td>
            <td>{{ o.sku }}</td>
            <td>{{ o.warehouse_code }}</td>
            <td>{{ o.order_qty }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">No planned orders. Select a scenario or run a plan.</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { usePlanningStore } from '@/stores/planning'
import type { PlannedOrder } from '@/api/client'

const store = usePlanningStore()
const selectedRunId = ref<number | null>(null)
const orders = ref<PlannedOrder[]>([])

const planRuns = computed(() => store.planRuns)

const exportUrl = computed(() =>
  selectedRunId.value ? `/api/exports/planned-orders?plan_run_id=${selectedRunId.value}` : '#'
)

watch(selectedRunId, async (id) => {
  if (id) {
    orders.value = await store.fetchPlannedOrders(id)
  } else {
    orders.value = []
  }
}, { immediate: true })

onMounted(() => store.fetchPlanRuns())
</script>

<style scoped>
.planned-orders { display: flex; flex-direction: column; gap: 1rem; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 1rem; }
.controls { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; }
.controls label { margin-right: 0.25rem; }
.select { padding: 0.35rem 0.5rem; border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg); color: var(--text); }
.btn { padding: 0.35rem 0.75rem; background: var(--accent); color: var(--bg); border-radius: var(--radius); text-decoration: none; display: inline-block; }
.table { width: 100%; border-collapse: collapse; }
.table th, .table td { text-align: left; padding: 0.5rem; border-bottom: 1px solid var(--border); }
.muted { color: var(--muted); margin: 0.5rem 0; }
</style>
