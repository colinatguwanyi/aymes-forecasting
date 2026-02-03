<template>
  <div class="page-content-inner">
    <p class="muted">Exportable table by scenario.</p>

    <section class="content-section controls">
      <div class="form-row">
        <label class="form-label">Scenario</label>
        <select v-model="selectedRunId" class="app-select" style="max-width: 18rem;">
          <option :value="null">Select scenario</option>
          <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
        </select>
      </div>
      <a v-if="selectedRunId" :href="exportUrl" class="app-btn app-btn-primary" download>Export CSV</a>
    </section>

    <section class="content-section">
      <div v-if="orders.length" class="app-table-wrap">
        <table class="app-table">
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
      </div>
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
.controls { display: flex; flex-wrap: wrap; gap: 0.75rem 1.5rem; align-items: flex-end; }
.form-row { display: flex; flex-direction: column; gap: 0.25rem; }
.form-label { font-size: 0.8125rem; color: var(--muted); }
.app-btn { text-decoration: none; display: inline-block; }
</style>
