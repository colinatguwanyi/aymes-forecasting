<template>
  <div class="page-content-inner">
    <p class="muted">View and export Breaches and Out-of-stock risk for a projection run. Use the run_id from Stock Projection after generating.</p>
    <p class="mb-4">
      <router-link to="/reports/stock-on-hand-history" class="text-blue-600 hover:underline">Stock On Hand History</router-link>
      — View on-hand units trend by week from imported SOH data (single SKU).
    </p>
    <p class="mb-4">
      <router-link to="/reports/stock-on-hand-grid" class="text-blue-600 hover:underline">SOH History Grid</router-link>
      — All products week-by-week SOH table (paginated).
    </p>
    <p class="mb-4">
      <router-link to="/reports/sales-grid" class="text-blue-600 hover:underline">Sales Grid</router-link>
      — Weekly customer sales by product (demand_facts_weekly CUSTOMER).
    </p>
    <p class="mb-4">
      <router-link to="/reports/data-health" class="text-blue-600 hover:underline">Data Health</router-link>
      — Readiness to run plan (products, demand, SOH, policies).
    </p>

    <section class="content-section controls">
      <div class="form-row">
        <label class="form-label">Run ID</label>
        <input v-model="runId" type="text" class="app-input" placeholder="e.g. from Stock Projection" style="max-width: 24rem;" />
      </div>
      <div class="form-row">
        <label class="form-label">Warehouse (optional)</label>
        <select v-model="warehouseId" class="app-select" style="max-width: 14rem;">
          <option :value="null">All</option>
          <option v-for="w in warehouses" :key="w.id" :value="w.id">{{ w.code }} – {{ w.name || '—' }}</option>
        </select>
      </div>
      <div class="form-row">
        <label class="form-label">Breach status (optional)</label>
        <select v-model="breachStatus" class="app-select" style="max-width: 10rem;">
          <option value="">All (red + amber)</option>
          <option value="red">Red</option>
          <option value="amber">Amber</option>
        </select>
      </div>
    </section>

    <section class="content-section">
      <h2>Breaches (red / amber)</h2>
      <div class="actions">
        <button type="button" class="app-btn app-btn-primary" :disabled="!runId" @click="loadBreaches">Load Breaches</button>
        <a v-if="runId" :href="breachesExportUrl" class="app-btn" download="breaches.csv">Export Breaches CSV</a>
      </div>
      <div v-if="breachesLoading" class="muted">Loading…</div>
      <div v-else-if="breaches.length" class="app-table-wrap">
        <table class="app-table">
          <thead>
            <tr>
              <th>Warehouse</th>
              <th>SKU</th>
              <th>Product</th>
              <th>ISO Year</th>
              <th>ISO Week</th>
              <th>Closing</th>
              <th>Safety target</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in breaches" :key="i">
              <td>{{ r.warehouse_code }}</td>
              <td>{{ r.sku }}</td>
              <td>{{ r.product_name ?? '—' }}</td>
              <td>{{ r.iso_year }}</td>
              <td>{{ r.iso_week }}</td>
              <td>{{ r.closing_units }}</td>
              <td>{{ r.safety_stock_target_units }}</td>
              <td>{{ r.breach_status }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else-if="breachesLoaded && !breaches.length" class="muted">No breaches for this run and filters.</p>
    </section>

    <section class="content-section">
      <h2>Out of stock risk (closing ≤ 0)</h2>
      <div class="actions">
        <button type="button" class="app-btn app-btn-primary" :disabled="!runId" @click="loadOos">Load Out of stock risk</button>
        <a v-if="runId" :href="oosExportUrl" class="app-btn" download="out_of_stock_risk.csv">Export OOS CSV</a>
      </div>
      <div v-if="oosLoading" class="muted">Loading…</div>
      <div v-else-if="oos.length" class="app-table-wrap">
        <table class="app-table">
          <thead>
            <tr>
              <th>Warehouse</th>
              <th>SKU</th>
              <th>Product</th>
              <th>ISO Year</th>
              <th>ISO Week</th>
              <th>Closing</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in oos" :key="i">
              <td>{{ r.warehouse_code }}</td>
              <td>{{ r.sku }}</td>
              <td>{{ r.product_name ?? '—' }}</td>
              <td>{{ r.iso_year }}</td>
              <td>{{ r.iso_week }}</td>
              <td>{{ r.closing_units }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else-if="oosLoaded && !oos.length" class="muted">No out-of-stock rows for this run and filters.</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '@/api/client'
import { useAdminStore } from '@/stores/admin'

const store = useAdminStore()
const warehouses = computed(() => store.warehouses)

const runId = ref('')
const warehouseId = ref<number | null>(null)
const breachStatus = ref('')

const breaches = ref<Array<{ warehouse_code: string; sku: string; product_name: string | null; iso_year: number; iso_week: number; closing_units: number; safety_stock_target_units: number; breach_status: string }>>([])
const breachesLoading = ref(false)
const breachesLoaded = ref(false)

const oos = ref<Array<{ warehouse_code: string; sku: string; product_name: string | null; iso_year: number; iso_week: number; closing_units: number }>>([])
const oosLoading = ref(false)
const oosLoaded = ref(false)

const breachesExportUrl = computed(() => {
  if (!runId.value) return '#'
  const params = new URLSearchParams({ run_id: runId.value })
  if (warehouseId.value != null) params.set('warehouse_id', String(warehouseId.value))
  if (breachStatus.value) params.set('status', breachStatus.value)
  return `/api/backbone/reports/breaches/export?${params.toString()}`
})

const oosExportUrl = computed(() => {
  if (!runId.value) return '#'
  const p = new URLSearchParams({ run_id: runId.value })
  if (warehouseId.value != null) p.set('warehouse_id', String(warehouseId.value))
  return `/api/backbone/reports/out-of-stock-risk/export?${p.toString()}`
})

async function loadBreaches() {
  if (!runId.value) return
  breachesLoading.value = true
  breachesLoaded.value = false
  try {
    const params: Record<string, string> = { run_id: runId.value }
    if (warehouseId.value != null) params.warehouse_id = String(warehouseId.value)
    if (breachStatus.value) params.status = breachStatus.value
    const { data } = await api.get('/backbone/reports/breaches', { params })
    breaches.value = data
    breachesLoaded.value = true
  } finally {
    breachesLoading.value = false
  }
}

async function loadOos() {
  if (!runId.value) return
  oosLoading.value = true
  oosLoaded.value = false
  try {
    const params: Record<string, string> = { run_id: runId.value }
    if (warehouseId.value != null) params.warehouse_id = String(warehouseId.value)
    const { data } = await api.get('/backbone/reports/out-of-stock-risk', { params })
    oos.value = data
    oosLoaded.value = true
  } finally {
    oosLoading.value = false
  }
}

onMounted(async () => {
  await store.fetchWarehouses()
})
</script>

<style scoped>
.controls .form-row { margin-bottom: 0.5rem; }
.form-label { display: inline-block; min-width: 10rem; margin-right: 0.5rem; }
.actions { display: flex; gap: 0.5rem; margin-bottom: 0.5rem; }
</style>
