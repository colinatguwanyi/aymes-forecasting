<template>
  <div class="page-content-inner reports-hub layout-data-wide w-full">
    <header class="reports-hub__header">
      <h1 class="reports-hub__title">Reports</h1>
      <p class="reports-hub__lede text-sm text-slate-600 m-0">
        Open a catalog report below, or use run-based tools with a projection <strong>run ID</strong> from Stock Projection.
      </p>
    </header>

    <section class="reports-hub__grid reports-hub__grid--links" aria-label="Report catalog">
      <article class="report-card report-card--link">
        <h2 class="report-card__title">Stock On Hand History</h2>
        <p class="report-card__desc">On-hand units by week for one SKU from imported SOH.</p>
        <router-link to="/reports/stock-on-hand-history" class="app-btn app-btn-primary report-card__action">Open</router-link>
      </article>
      <article class="report-card report-card--link">
        <h2 class="report-card__title">SOH history grid</h2>
        <p class="report-card__desc">All products, week-by-week SOH table (paginated).</p>
        <router-link to="/reports/stock-on-hand-grid" class="app-btn app-btn-primary report-card__action">Open</router-link>
      </article>
      <article class="report-card report-card--link">
        <h2 class="report-card__title">Sales grid</h2>
        <p class="report-card__desc">Weekly customer sales by product (demand_facts_weekly CUSTOMER).</p>
        <router-link to="/reports/sales-grid" class="app-btn app-btn-primary report-card__action">Open</router-link>
      </article>
      <article class="report-card report-card--link">
        <h2 class="report-card__title">Stock coverage</h2>
        <p class="report-card__desc">Weeks of cover by warehouse (on-hand ÷ avg demand).</p>
        <router-link to="/reports/stock-coverage" class="app-btn app-btn-primary report-card__action">Open</router-link>
      </article>
      <article class="report-card report-card--link">
        <h2 class="report-card__title">Data health</h2>
        <p class="report-card__desc">Readiness to run a plan: products, demand, SOH, policies.</p>
        <router-link to="/reports/data-health" class="app-btn app-btn-primary report-card__action">Open</router-link>
      </article>
    </section>

    <section class="reports-hub__run-tools" aria-label="Projection run reports">
      <h2 class="reports-hub__section-heading">Projection run reports</h2>
      <p class="reports-hub__section-note text-sm text-slate-600 m-0 mb-4">
        Same <strong>run ID</strong> and <strong>warehouse</strong> apply to both tools below.
      </p>

      <div class="reports-hub__grid reports-hub__grid--tools">
        <article class="report-card report-card--tool">
          <h2 class="report-card__title">Breaches (red / amber)</h2>
          <p class="report-card__desc">Target vs closing for a run; filter by warehouse and breach colour.</p>
          <div class="report-card__controls">
            <div class="report-field">
              <label class="report-field__label" for="reports-run-breaches">Run ID</label>
              <input id="reports-run-breaches" v-model="runId" type="text" class="app-input report-field__input" placeholder="e.g. from Stock Projection" />
            </div>
            <div class="report-field">
              <label class="report-field__label" for="reports-wh-breaches">Warehouse</label>
              <select id="reports-wh-breaches" v-model="warehouseId" class="app-select report-field__input">
                <option :value="null">All</option>
                <option v-for="w in warehouses" :key="w.id" :value="w.id">{{ w.code }} – {{ w.name || '—' }}</option>
              </select>
            </div>
            <div class="report-field">
              <label class="report-field__label" for="reports-breach-status">Breach status</label>
              <select id="reports-breach-status" v-model="breachStatus" class="app-select report-field__input">
                <option value="">All (red + amber)</option>
                <option value="red">Red</option>
                <option value="amber">Amber</option>
              </select>
            </div>
          </div>
          <div class="report-card__actions">
            <button type="button" class="app-btn app-btn-primary" :disabled="!runId" @click="loadBreaches">Load breaches</button>
            <a v-if="runId" :href="breachesExportUrl" class="app-btn" download="breaches.csv">Export CSV</a>
          </div>
          <div v-if="breachesLoading" class="report-card__status muted">Loading…</div>
          <div v-else-if="breaches.length" class="app-table-wrap report-card__table">
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
          <p v-else-if="breachesLoaded && !breaches.length" class="report-card__status muted m-0">No breaches for this run and filters.</p>
        </article>

        <article class="report-card report-card--tool">
          <h2 class="report-card__title">Out of stock risk</h2>
          <p class="report-card__desc">Weeks where closing ≤ 0 for the same run (optional warehouse).</p>
          <div class="report-card__controls">
            <div class="report-field">
              <label class="report-field__label" for="reports-run-oos">Run ID</label>
              <input id="reports-run-oos" v-model="runId" type="text" class="app-input report-field__input" placeholder="e.g. from Stock Projection" />
            </div>
            <div class="report-field">
              <label class="report-field__label" for="reports-wh-oos">Warehouse</label>
              <select id="reports-wh-oos" v-model="warehouseId" class="app-select report-field__input">
                <option :value="null">All</option>
                <option v-for="w in warehouses" :key="'o-' + w.id" :value="w.id">{{ w.code }} – {{ w.name || '—' }}</option>
              </select>
            </div>
          </div>
          <div class="report-card__actions">
            <button type="button" class="app-btn app-btn-primary" :disabled="!runId" @click="loadOos">Load out of stock risk</button>
            <a v-if="runId" :href="oosExportUrl" class="app-btn" download="out_of_stock_risk.csv">Export CSV</a>
          </div>
          <div v-if="oosLoading" class="report-card__status muted">Loading…</div>
          <div v-else-if="oos.length" class="app-table-wrap report-card__table">
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
          <p v-else-if="oosLoaded && !oos.length" class="report-card__status muted m-0">No out-of-stock rows for this run and filters.</p>
        </article>
      </div>
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
.reports-hub {
  width: 100%;
}
.reports-hub__header {
  margin-bottom: 1.25rem;
}
.reports-hub__title {
  font-size: 1.25rem;
  font-weight: 600;
  color: rgb(15 23 42);
  margin: 0 0 0.35rem;
}
.reports-hub__lede {
  max-width: 40rem;
  line-height: 1.45;
}
.reports-hub__section-heading {
  font-size: 1.0625rem;
  font-weight: 600;
  color: rgb(30 41 59);
  margin: 2rem 0 0;
}
.reports-hub__section-note {
  max-width: 40rem;
  line-height: 1.45;
}
.reports-hub__grid {
  display: grid;
  gap: 1rem;
}
.reports-hub__grid--links {
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
}
.reports-hub__grid--tools {
  grid-template-columns: 1fr;
}
@media (min-width: 960px) {
  .reports-hub__grid--tools {
    grid-template-columns: 1fr 1fr;
    align-items: start;
  }
}
.report-card {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.5rem;
  padding: 1rem 1.125rem;
  background: rgb(255 255 255);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.report-card--link {
  min-height: 8.5rem;
}
.report-card__title {
  font-size: 1rem;
  font-weight: 600;
  color: rgb(30 41 59);
  margin: 0;
  line-height: 1.3;
}
.report-card__desc {
  font-size: 0.8125rem;
  color: rgb(71 85 105);
  margin: 0;
  line-height: 1.4;
  flex: 1;
}
.report-card__action {
  align-self: flex-start;
  margin-top: 0.25rem;
  text-decoration: none;
  text-align: center;
}
.report-card__controls {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  margin-top: 0.25rem;
}
.report-field__label {
  display: block;
  font-size: 0.8125rem;
  font-weight: 500;
  color: rgb(51 65 85);
  margin-bottom: 0.2rem;
}
.report-field__input {
  width: 100%;
  box-sizing: border-box;
}
.report-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.25rem;
}
.report-card__actions .app-btn {
  text-decoration: none;
}
.report-card__status {
  font-size: 0.875rem;
}
.report-card__table {
  margin-top: 0.75rem;
  max-height: 22rem;
  overflow: auto;
  width: 100%;
}
.report-card__table .app-table {
  width: 100%;
}
</style>
