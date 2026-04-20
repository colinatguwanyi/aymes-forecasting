<template>
  <div class="page-content-inner">
    <h1 class="text-xl font-semibold text-slate-800 mb-1">Stock Coverage Report</h1>
    <p class="muted mb-6">
      Weeks of cover = on-hand qty ÷ avg weekly demand. AAH: CUSTOMER only; BLP: CUSTOMER + SAMPLES. No forecast logic.
    </p>

    <section class="content-section controls">
      <div class="form-row">
        <label class="form-label">Warehouse</label>
        <select v-model="warehouseCode" class="app-select" style="max-width: 10rem;">
          <option value="">All</option>
          <option v-for="code in warehouseOptions" :key="code" :value="code">{{ code }}</option>
        </select>
      </div>
      <div class="form-row">
        <label class="form-label">Weeks (demand avg)</label>
        <select v-model="weeksWindow" class="app-select" style="max-width: 6rem;">
          <option v-for="n in [4, 8, 13, 26]" :key="n" :value="n">{{ n }}</option>
        </select>
      </div>
      <div class="form-row">
        <button
          type="button"
          class="app-btn app-btn-primary"
          :disabled="loading"
          @click="load"
        >
          {{ loading ? 'Loading…' : 'Load report' }}
        </button>
      </div>
    </section>

    <section v-if="loaded" class="content-section">
      <!-- Summary tiles per warehouse -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        <div
          v-for="s in summary"
          :key="s.warehouse_code"
          class="p-4 rounded-lg border border-neutral-200 bg-white"
        >
          <h3 class="font-semibold text-slate-800 mb-2">{{ s.warehouse_code }}</h3>
          <p class="text-sm text-slate-600 mb-1">Latest SOH week: {{ s.latest_soh_week ?? '—' }}</p>
          <p class="text-sm text-slate-600 mb-2">{{ s.row_count }} SKUs</p>
          <div class="flex flex-wrap gap-2 text-xs">
            <span class="px-2 py-0.5 rounded bg-red-100 text-red-800">Critical: {{ s.critical_count }}</span>
            <span class="px-2 py-0.5 rounded bg-amber-100 text-amber-800">Low: {{ s.low_count }}</span>
            <span class="px-2 py-0.5 rounded bg-cyan-100 text-cyan-800">Monitor: {{ s.monitor_count }}</span>
            <span class="px-2 py-0.5 rounded bg-green-100 text-green-800">Healthy: {{ s.healthy_count }}</span>
            <span class="px-2 py-0.5 rounded bg-neutral-100 text-neutral-600">No demand: {{ s.no_demand_count }}</span>
          </div>
        </div>
      </div>

      <div class="flex items-center justify-between gap-4 mb-3">
        <p class="muted">{{ sortedRows.length }} rows · sorted by weeks cover (lowest first)</p>
        <button
          type="button"
          class="app-btn"
          :disabled="!sortedRows.length"
          @click="exportCsv"
        >
          Export CSV
        </button>
      </div>

      <div class="app-table-wrap overflow-x-auto">
        <table class="app-table">
          <thead>
            <tr>
              <th class="cursor-pointer hover:bg-neutral-100" @click="sortBy('sku')">
                SKU {{ sortKey === 'sku' ? (sortAsc ? '↑' : '↓') : '' }}
              </th>
              <th class="cursor-pointer hover:bg-neutral-100" @click="sortBy('warehouse_code')">
                Warehouse {{ sortKey === 'warehouse_code' ? (sortAsc ? '↑' : '↓') : '' }}
              </th>
              <th class="cursor-pointer hover:bg-neutral-100 text-right" @click="sortBy('on_hand_qty')">
                On hand {{ sortKey === 'on_hand_qty' ? (sortAsc ? '↑' : '↓') : '' }}
              </th>
              <th class="cursor-pointer hover:bg-neutral-100 text-right" @click="sortBy('avg_weekly_demand')">
                Avg demand {{ sortKey === 'avg_weekly_demand' ? (sortAsc ? '↑' : '↓') : '' }}
              </th>
              <th class="cursor-pointer hover:bg-neutral-100 text-right" @click="sortBy('weeks_cover')">
                Weeks cover {{ sortKey === 'weeks_cover' ? (sortAsc ? '↑' : '↓') : '' }}
              </th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="6" class="py-8 text-center text-slate-500">Loading…</td>
            </tr>
            <tr v-else-if="!sortedRows.length">
              <td colspan="6" class="py-12 text-center text-slate-500">No data for selected filters.</td>
            </tr>
            <tr
              v-else
              v-for="row in sortedRows"
              :key="`${row.sku}-${row.warehouse_code}`"
              :class="statusRowClass(row.status_bucket)"
            >
              <td class="font-mono text-sm">{{ row.sku }}</td>
              <td>{{ row.warehouse_code }}</td>
              <td class="text-right">{{ formatQty(row.on_hand_qty) }}</td>
              <td class="text-right">{{ formatQty(row.avg_weekly_demand) }}</td>
              <td class="text-right">{{ row.weeks_cover != null ? row.weeks_cover.toFixed(2) : '—' }}</td>
              <td>
                <span :class="statusBadgeClass(row.status_bucket)">{{ row.status_bucket }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import api from '@/api/client'
import { useAdminStore } from '@/stores/admin'

interface SummaryItem {
  warehouse_code: string
  latest_soh_week: string | null
  row_count: number
  critical_count: number
  low_count: number
  monitor_count: number
  healthy_count: number
  no_demand_count: number
}

interface Row {
  sku: string
  warehouse_code: string
  on_hand_qty: number
  avg_weekly_demand: number
  weeks_cover: number | null
  status_bucket: string
}

interface StockCoverageResponse {
  summary: SummaryItem[]
  rows: Row[]
}

const adminStore = useAdminStore()
const warehouseOptions = computed(() => {
  const codes = new Set<string>(['AAH', 'BLP'])
  adminStore.warehouses.forEach((w) => codes.add(w.code))
  return Array.from(codes).sort()
})

const warehouseCode = ref<string>('')
const weeksWindow = ref(13)
const loading = ref(false)
const loaded = ref(false)
const data = ref<StockCoverageResponse>({ summary: [], rows: [] })

const summary = computed(() => data.value.summary || [])

type SortKey = 'sku' | 'warehouse_code' | 'on_hand_qty' | 'avg_weekly_demand' | 'weeks_cover'
const sortKey = ref<SortKey>('weeks_cover')
const sortAsc = ref(false) // Default: ascending for weeks_cover (lowest first)

const sortedRows = computed(() => {
  const rows = [...(data.value.rows || [])]
  rows.sort((a, b) => {
    const key = sortKey.value
    let va: string | number | null = (a as Record<string, unknown>)[key] as string | number | null
    let vb: string | number | null = (b as Record<string, unknown>)[key] as string | number | null

    if (va == null && vb == null) return 0
    if (va == null) return sortAsc.value ? 1 : -1
    if (vb == null) return sortAsc.value ? -1 : 1

    if (typeof va === 'number' && typeof vb === 'number') {
      return sortAsc.value ? va - vb : vb - va
    }
    const sa = String(va)
    const sb = String(vb)
    return sortAsc.value ? sa.localeCompare(sb) : sb.localeCompare(sa)
  })
  return rows
})

function sortBy(key: SortKey) {
  if (sortKey.value === key) {
    sortAsc.value = !sortAsc.value
  } else {
    sortKey.value = key
    sortAsc.value = key === 'weeks_cover' // ascending for weeks_cover by default
  }
}

function formatQty(v: number): string {
  if (v == null || Number.isNaN(v)) return '0'
  return String(Math.round(v * 100) / 100)
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'Critical':
      return 'px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800'
    case 'Low':
      return 'px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800'
    case 'Monitor':
      return 'px-2 py-0.5 rounded text-xs font-medium bg-cyan-100 text-cyan-800'
    case 'Healthy':
      return 'px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800'
    case 'No demand':
      return 'px-2 py-0.5 rounded text-xs font-medium bg-neutral-100 text-neutral-600'
    default:
      return 'px-2 py-0.5 rounded text-xs font-medium bg-neutral-100 text-neutral-600'
  }
}

function statusRowClass(status: string): string {
  switch (status) {
    case 'Critical':
      return 'bg-red-50'
    case 'Low':
      return 'bg-amber-50'
    default:
      return ''
  }
}

function exportCsv() {
  const rows = sortedRows.value
  if (!rows.length) return
  const headers = ['sku', 'warehouse_code', 'on_hand_qty', 'avg_weekly_demand', 'weeks_cover', 'status_bucket']
  const lines = [headers.join(',')]
  for (const r of rows) {
    const wc = r.weeks_cover != null ? r.weeks_cover.toFixed(2) : ''
    lines.push([r.sku, r.warehouse_code, r.on_hand_qty, r.avg_weekly_demand, wc, r.status_bucket].join(','))
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'stock-coverage.csv'
  a.click()
  URL.revokeObjectURL(url)
}

async function load() {
  loading.value = true
  loaded.value = false
  try {
    const params: Record<string, string | number> = { weeks_window: weeksWindow.value }
    if (warehouseCode.value) params.warehouse_code = warehouseCode.value
    const { data: res } = await api.get<StockCoverageResponse>('/v1/reports/stock-coverage', { params })
    data.value = res
    loaded.value = true
  } finally {
    loading.value = false
  }
}

watch([warehouseCode, weeksWindow], () => {
  if (loaded.value) load()
})

onMounted(async () => {
  await adminStore.fetchWarehouses()
  load()
})
</script>

<style scoped>
.controls .form-row {
  margin-bottom: 0.75rem;
}
.form-label {
  display: inline-block;
  min-width: 10rem;
  margin-right: 0.5rem;
}
</style>
