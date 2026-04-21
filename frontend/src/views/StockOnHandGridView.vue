<template>
  <div class="page-content-inner">
    <h1 class="text-xl font-semibold text-slate-800 mb-1">SOH History Grid</h1>
    <p class="muted mb-6">All products stock-on-hand by week. No SKU selection — table shows all products with week-by-week columns.</p>

    <section class="content-section controls">
      <div class="form-row">
        <label class="form-label">Warehouse</label>
        <select v-model="warehouseCode" class="app-select" style="max-width: 10rem;">
          <option v-for="code in warehouseOptions" :key="code" :value="code">{{ code }}</option>
        </select>
      </div>
      <div class="form-row">
        <label class="form-label">Weeks</label>
        <select v-model="weeks" class="app-select" style="max-width: 6rem;">
          <option v-for="n in [4, 8, 12, 26]" :key="n" :value="n">{{ n }}</option>
        </select>
      </div>
      <div class="form-row">
        <label class="form-label">Search</label>
        <input
          v-model="searchText"
          type="text"
          class="app-input"
          placeholder="SKU or name…"
          style="max-width: 16rem;"
        />
      </div>
      <div class="form-row">
        <button
          type="button"
          class="app-btn app-btn-primary"
          :disabled="loading"
          @click="loadGrid"
        >
          {{ loading ? 'Loading…' : 'Load grid' }}
        </button>
      </div>
    </section>

    <section class="content-section">
      <p v-if="loadError" class="text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm">{{ loadError }}</p>
      <p v-else-if="loading && !hasGridContent" class="muted">Loading grid…</p>
      <p v-else-if="!gridData.week_starts.length" class="muted">No SOH data for this warehouse.</p>
      <template v-else>
        <p class="muted mb-2">
          Anchor week: {{ gridData.anchor_week_start }} · {{ gridData.total_products }} products
        </p>
        <div class="grid-table-wrap">
          <table class="app-table soh-grid-table">
            <thead>
              <tr>
                <th class="sticky-col sku-col">SKU</th>
                <th class="sticky-col name-col">Name</th>
                <th v-for="ws in gridData.week_starts" :key="ws" class="week-col">{{ formatWeek(ws) }}</th>
                <th class="total-col">Latest</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td :colspan="gridData.week_starts.length + 3" class="py-8 text-center text-slate-500">Loading…</td>
              </tr>
              <tr v-else-if="!gridData.rows.length">
                <td :colspan="gridData.week_starts.length + 3" class="py-12 text-center text-slate-500">No products match filters.</td>
              </tr>
              <tr v-else v-for="row in gridData.rows" :key="row.sku">
                <td class="sticky-col sku-col font-mono text-sm">{{ row.sku }}</td>
                <td class="sticky-col name-col text-slate-700">{{ row.name || '—' }}</td>
                <td v-for="(val, i) in row.values" :key="i" class="week-col text-right">{{ formatQty(val) }}</td>
                <td class="total-col text-right font-medium">{{ formatQty(latestValue(row)) }}</td>
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
const loadError = ref<string | null>(null)
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

/** True once we have weeks or rows (avoids "No SOH data" flash while first request is in flight). */
const hasGridContent = computed(
  () => gridData.value.week_starts.length > 0 || gridData.value.rows.length > 0,
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
  loadError.value = null
  try {
    const params: Record<string, string | number> = {
      warehouse_code: warehouseCode.value,
      weeks: weeks.value,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    }
    if (searchText.value.trim()) params.q = searchText.value.trim()
    const { data } = await api.get<GridResponse>('/v1/reports/stock-on-hand/grid', { params })
    gridData.value = data
  } catch (err: unknown) {
    loadError.value = formatGridError(err)
    gridData.value = {
      warehouse_code: warehouseCode.value,
      anchor_week_start: null,
      week_starts: [],
      total_products: 0,
      rows: [],
    }
  } finally {
    loading.value = false
  }
}

function formatGridError(err: unknown): string {
  const res = err && typeof err === 'object' && 'response' in err ? (err as { response?: { status?: number; data?: { detail?: unknown } } }).response : null
  if (res?.status === 503) {
    const d = res.data?.detail
    return typeof d === 'string' ? d : 'Server unavailable (database?). Check API is running and MySQL is up.'
  }
  const d = res?.data?.detail
  if (d != null) return typeof d === 'string' ? d : JSON.stringify(d)
  if (err && typeof err === 'object' && 'message' in err && typeof (err as { message: string }).message === 'string') {
    const m = (err as { message: string }).message
    if (/Network Error|ECONNREFUSED/i.test(m)) return 'Cannot reach API. Start the backend (uvicorn) and ensure Vite proxy targets port 8000.'
  }
  return 'Failed to load grid.'
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
.controls .form-row {
  margin-bottom: 0.75rem;
}
.form-label {
  display: inline-block;
  min-width: 7rem;
  margin-right: 0.5rem;
}
.grid-table-wrap {
  overflow-x: auto;
  max-width: 100%;
}
.soh-grid-table {
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
.soh-grid-table thead .week-col {
  background: var(--table-header-bg, #153256);
  color: var(--table-header-text, #f8fafc);
}
</style>
