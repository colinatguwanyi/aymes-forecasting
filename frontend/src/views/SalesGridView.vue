<template>
  <div class="page-content-inner">
    <h1 class="text-xl font-semibold text-slate-800 mb-1">Sales Grid</h1>
    <p class="muted mb-6">Weekly customer sales (demand_facts_weekly CUSTOMER) by product. No SKU selection — table shows all products with week-by-week columns.</p>

    <section class="sales-grid-toolbar content-section">
      <div class="sales-grid-toolbar__fields">
        <div class="sales-grid-field">
          <label class="sales-grid-field__label" for="sales-grid-wh">Warehouse</label>
          <select id="sales-grid-wh" v-model="warehouseCode" class="sales-grid-field__control app-select">
            <option v-for="code in warehouseOptions" :key="code" :value="code">{{ code }}</option>
          </select>
        </div>
        <div class="sales-grid-field">
          <label class="sales-grid-field__label" for="sales-grid-weeks">Weeks</label>
          <select id="sales-grid-weeks" v-model="weeks" class="sales-grid-field__control app-select sales-grid-field__control--narrow">
            <option v-for="n in [4, 8, 12, 26]" :key="n" :value="n">{{ n }}</option>
          </select>
        </div>
        <div class="sales-grid-field sales-grid-field--grow">
          <label class="sales-grid-field__label" for="sales-grid-search">Search</label>
          <input
            id="sales-grid-search"
            v-model="searchText"
            type="text"
            class="sales-grid-field__control app-input"
            placeholder="SKU or name…"
            autocomplete="off"
          />
        </div>
        <div class="sales-grid-field sales-grid-field--action">
          <span class="sales-grid-field__label sales-grid-field__label--spacer" aria-hidden="true">Load</span>
          <button
            type="button"
            class="sales-grid-toolbar__btn app-btn app-btn-primary"
            :disabled="loading"
            @click="loadGrid"
          >
            {{ loading ? 'Loading…' : 'Load grid' }}
          </button>
        </div>
      </div>
    </section>

    <section v-if="loaded" class="content-section">
      <p v-if="!gridData.week_starts.length" class="muted">No sales data for this warehouse.</p>
      <template v-else>
        <p class="muted mb-2">
          Anchor week: {{ gridData.anchor_week_start }} · {{ gridData.total_products }} products
        </p>
        <div class="grid-table-wrap sales-grid-table-shell">
          <table class="app-table sales-grid-table">
            <thead>
              <tr>
                <th class="sticky-col sku-col">SKU</th>
                <th class="sticky-col name-col">Name</th>
                <th v-for="ws in gridData.week_starts" :key="ws" class="week-col">{{ formatWeek(ws) }}</th>
                <th class="total-col">Latest</th>
                <th class="total-col">Total ({{ weeks }})</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td :colspan="gridData.week_starts.length + 5" class="py-8 text-center text-slate-500">Loading…</td>
              </tr>
              <tr v-else-if="!gridData.rows.length">
                <td :colspan="gridData.week_starts.length + 5" class="py-12 text-center text-slate-500">No products match filters.</td>
              </tr>
              <tr v-else v-for="row in gridData.rows" :key="row.sku">
                <td class="sticky-col sku-col font-mono text-sm">{{ row.sku }}</td>
                <td class="sticky-col name-col text-slate-700">{{ row.name || '—' }}</td>
                <td v-for="(val, i) in row.values" :key="i" class="week-col text-right">{{ formatQty(val) }}</td>
                <td class="total-col text-right font-medium">{{ formatQty(row.latest ?? latestValue(row)) }}</td>
                <td class="total-col text-right font-medium">{{ formatQty(row.total ?? sumValues(row)) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div
          v-if="gridData.total_products > 0"
          class="flex items-center justify-between gap-4 mt-3 px-2 py-2 border-t border-neutral-200 bg-neutral-50 text-sm text-neutral-600"
        >
          <div class="flex items-center gap-2">
            <span>Rows per page</span>
            <select
              :value="pageSize"
              class="border border-neutral-300 rounded px-2 py-1 text-sm bg-white"
              @change="onPageSizeChange($event)"
            >
              <option v-for="n in [25, 50, 100]" :key="n" :value="n">{{ n }}</option>
            </select>
          </div>
          <div class="flex items-center gap-4">
            <span>
              {{ (page - 1) * pageSize + 1 }}–{{ Math.min(page * pageSize, gridData.total_products) }}
              of {{ gridData.total_products }}
            </span>
            <div class="flex gap-1">
              <button
                type="button"
                class="px-2 py-1 rounded border border-neutral-300 bg-white hover:bg-neutral-100 disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="page <= 1"
                @click="page = 1; loadGrid()"
              >
                First
              </button>
              <button
                type="button"
                class="px-2 py-1 rounded border border-neutral-300 bg-white hover:bg-neutral-100 disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="page <= 1"
                @click="page--; loadGrid()"
              >
                Previous
              </button>
              <button
                type="button"
                class="px-2 py-1 rounded border border-neutral-300 bg-white hover:bg-neutral-100 disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="page >= totalPages"
                @click="page++; loadGrid()"
              >
                Next
              </button>
              <button
                type="button"
                class="px-2 py-1 rounded border border-neutral-300 bg-white hover:bg-neutral-100 disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="page >= totalPages"
                @click="page = totalPages; loadGrid()"
              >
                Last
              </button>
            </div>
          </div>
        </div>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import api from '@/api/client'
import { useAdminStore } from '@/stores/admin'

interface GridRow {
  sku: string
  name: string
  values: number[]
  latest?: number
  total?: number
}

interface GridResponse {
  warehouse_code: string
  anchor_week_start: string | null
  week_starts: string[]
  total_products: number
  rows: GridRow[]
}

const adminStore = useAdminStore()
const warehouseOptions = computed(() => {
  const codes = new Set<string>(['AAH'])
  adminStore.warehouses.forEach((w) => codes.add(w.code))
  return Array.from(codes).sort()
})

const warehouseCode = ref('AAH')
const weeks = ref(12)
const searchText = ref('')
const page = ref(1)
const pageSize = ref(50)
const loading = ref(false)
const loaded = ref(false)
const gridData = ref<GridResponse>({
  warehouse_code: '',
  anchor_week_start: null,
  week_starts: [],
  total_products: 0,
  rows: [],
})

const totalPages = computed(() =>
  gridData.value.total_products > 0
    ? Math.max(1, Math.ceil(gridData.value.total_products / pageSize.value))
    : 1
)

function formatWeek(ws: string): string {
  if (!ws) return '—'
  const d = new Date(ws)
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: '2-digit' })
}

function formatQty(v: number): string {
  if (v == null || Number.isNaN(v)) return '0'
  return String(Math.round(v))
}

function latestValue(row: GridRow): number {
  return row.values?.[0] ?? 0
}

function sumValues(row: GridRow): number {
  return (row.values ?? []).reduce((a, b) => a + b, 0)
}

function onPageSizeChange(e: Event) {
  pageSize.value = Number((e.target as HTMLSelectElement).value)
  page.value = 1
  loadGrid()
}

let searchDebounce: ReturnType<typeof setTimeout> | null = null
watch(searchText, () => {
  if (searchDebounce) clearTimeout(searchDebounce)
  searchDebounce = setTimeout(() => {
    page.value = 1
    loadGrid()
  }, 300)
})

async function loadGrid() {
  loading.value = true
  loaded.value = false
  try {
    const params: Record<string, string | number> = {
      warehouse_code: warehouseCode.value,
      weeks: weeks.value,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    }
    if (searchText.value.trim()) params.q = searchText.value.trim()
    const { data } = await api.get<GridResponse>('/v1/reports/sales/grid', { params })
    gridData.value = data
    loaded.value = true
  } finally {
    loading.value = false
  }
}

watch([warehouseCode, weeks], () => {
  page.value = 1
  loadGrid()
})

onMounted(async () => {
  await adminStore.fetchWarehouses()
  loadGrid()
})
</script>

<style scoped>
.sales-grid-toolbar {
  margin-bottom: 1.25rem;
  padding: 1rem 1.1rem;
  border-radius: 0.75rem;
  border: 1px solid rgb(226 232 240);
  background: rgb(248 250 252);
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.04);
}
.sales-grid-toolbar__fields {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 1rem 1.25rem;
}
.sales-grid-field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  min-width: 0;
}
.sales-grid-field--grow {
  flex: 1 1 12rem;
  min-width: 10rem;
}
.sales-grid-field--action {
  flex: 0 0 auto;
}
.sales-grid-field__label {
  font-size: 0.75rem;
  font-weight: 600;
  color: rgb(71 85 105);
  letter-spacing: 0.02em;
}
.sales-grid-field__label--spacer {
  visibility: hidden;
  min-height: 1em;
  margin: 0;
}
.sales-grid-field__control {
  border-radius: 0.5rem;
  min-height: 2.375rem;
}
.sales-grid-field__control--narrow {
  max-width: 5.5rem;
}
.sales-grid-toolbar__btn {
  border-radius: 0.5rem;
  padding-left: 1.1rem;
  padding-right: 1.1rem;
  min-height: 2.375rem;
}
.grid-table-wrap {
  overflow-x: auto;
  max-width: 100%;
}
.sales-grid-table-shell {
  border-radius: 0.75rem;
  border: 1px solid rgb(226 232 240);
  box-shadow: 0 1px 3px rgb(15 23 42 / 0.06);
  background: white;
}
.sales-grid-table {
  min-width: 600px;
}
.sticky-col {
  position: sticky;
  background: white;
  z-index: 1;
}
.sku-col {
  left: 0;
  min-width: 8rem;
  border-right: 1px solid rgb(226 232 240);
}
.name-col {
  left: 8rem;
  min-width: 14rem;
  max-width: 18rem;
  border-right: 1px solid rgb(226 232 240);
}
.week-col {
  min-width: 4rem;
  white-space: nowrap;
}
.total-col {
  min-width: 4.5rem;
  background: rgb(248 250 252);
  font-weight: 500;
}
thead .sticky-col {
  background: var(--table-header-bg, #153256);
  color: var(--table-header-text, #f8fafc);
}
thead .total-col {
  background: var(--table-header-bg, #153256);
  color: var(--table-header-text, #f8fafc);
}
.sales-grid-table thead .week-col {
  background: var(--table-header-bg, #153256);
  color: var(--table-header-text, #f8fafc);
}
</style>
