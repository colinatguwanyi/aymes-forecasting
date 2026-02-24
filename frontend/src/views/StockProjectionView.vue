<template>
  <div class="page-content-inner">
    <p class="muted">Admin-first weekly supply planning: generate projection, view grid (closing / WOS / R-A-G), export CSV.</p>

    <section class="content-section controls">
      <div class="form-row">
        <label class="form-label">Warehouse</label>
        <select v-model="warehouseId" class="app-select" style="max-width: 14rem;">
          <option :value="null">All warehouses</option>
          <option v-for="w in warehouses" :key="w.id" :value="w.id">{{ w.code }} – {{ w.name || '—' }}</option>
        </select>
      </div>
      <div class="form-row">
        <label class="form-label">Start week (ISO year)</label>
        <input v-model.number="startIsoYear" type="number" class="app-input" min="2020" max="2030" style="max-width: 6rem;" />
      </div>
      <div class="form-row">
        <label class="form-label">Start week (ISO week)</label>
        <input v-model.number="startIsoWeek" type="number" class="app-input" min="1" max="53" style="max-width: 5rem;" />
      </div>
      <div class="form-row">
        <label class="form-label">Horizon weeks</label>
        <input v-model.number="horizonWeeks" type="number" class="app-input" min="1" max="52" style="max-width: 5rem;" />
      </div>
      <div class="form-row">
        <button type="button" class="app-btn app-btn-primary" :disabled="generating" @click="generateProjection">
          {{ generating ? 'Generating…' : 'Generate Projection' }}
        </button>
      </div>
    </section>

    <section v-if="runId && !gridLoading && gridData.length" class="content-section">
      <h2>Grid (run {{ runId.slice(0, 8) }})</h2>
      <p class="muted">R = red, A = amber, G = green. Cells: closing_units / WOS / breach.</p>
      <a v-if="runId" :href="exportUrl" class="app-btn" download>Export CSV</a>
      <div class="grid-wrap app-table-wrap">
        <table class="planning-grid app-table">
          <thead>
            <tr>
              <th class="sticky-col sticky-header">SKU / Product</th>
              <th v-for="col in weekColumns" :key="col.key" class="sticky-header week-header">{{ col.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in gridRows" :key="row.key">
              <td class="sticky-col row-label">{{ row.sku }} – {{ row.product_name || '—' }}</td>
              <td
                v-for="col in weekColumns"
                :key="col.key"
                :class="cellClass(row, col)"
                class="grid-cell"
              >{{ cellText(row, col) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
    <section v-else-if="runId && gridLoading" class="content-section">Loading grid…</section>
    <section v-else-if="runId && !gridLoading && !gridData.length" class="content-section">
      <p class="muted">No projection rows. Ensure warehouse has warehouse-product config and stock/demand data, then generate again.</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '@/api/client'

interface ProjectionRow {
  run_id: string
  warehouse_code: string
  sku: string
  product_name: string | null
  iso_year: number
  iso_week: number
  week_label: string
  closing_units: number
  weeks_of_supply: number | null
  breach_status: string
}

const warehouses = ref<{ id: number; code: string; name: string | null }[]>([])
const warehouseId = ref<number | null>(null)
const startIsoYear = ref(new Date().getFullYear())
const startIsoWeek = ref(1)
const horizonWeeks = ref(26)
const generating = ref(false)
const runId = ref<string | null>(null)
const gridLoading = ref(false)
const gridData = ref<ProjectionRow[]>([])

const weekColumns = computed(() => {
  const seen = new Map<string, { key: string; label: string }>()
  for (const r of gridData.value) {
    const k = `${r.iso_year}-W${String(r.iso_week).padStart(2, '0')}`
    if (!seen.has(k)) seen.set(k, { key: k, label: k })
  }
  return Array.from(seen.values()).sort((a, b) => a.key.localeCompare(b.key))
})

const gridRows = computed(() => {
  const byKey = new Map<string, { key: string; sku: string; product_name: string | null; cells: Map<string, ProjectionRow> }>()
  for (const r of gridData.value) {
    const rowKey = `${r.warehouse_code}|${r.sku}`
    if (!byKey.has(rowKey)) {
      byKey.set(rowKey, { key: rowKey, sku: r.sku, product_name: r.product_name, cells: new Map() })
    }
    const row = byKey.get(rowKey)!
    const weekKey = `${r.iso_year}-W${String(r.iso_week).padStart(2, '0')}`
    row.cells.set(weekKey, r)
  }
  return Array.from(byKey.values())
})

function cellClass(row: { cells: Map<string, ProjectionRow> }, col: { key: string }): string[] {
  const c = ['grid-cell']
  const p = row.cells.get(col.key)
  if (!p) return c
  if (p.breach_status === 'red') c.push('cell-status-error')
  else if (p.breach_status === 'amber') c.push('cell-status-warning')
  else c.push('cell-status-ok')
  return c
}

function cellText(row: { cells: Map<string, ProjectionRow> }, col: { key: string }): string {
  const p = row.cells.get(col.key)
  if (!p) return '—'
  const wos = p.weeks_of_supply != null ? p.weeks_of_supply.toFixed(1) : '—'
  return `${p.closing_units} / ${wos} / ${p.breach_status.slice(0, 1).toUpperCase()}`
}

const exportUrl = computed(() => {
  if (!runId.value) return '#'
  let u = `/api/projections/export?run_id=${encodeURIComponent(runId.value)}`
  if (warehouseId.value != null) u += `&warehouse_id=${warehouseId.value}`
  return u
})

async function generateProjection() {
  generating.value = true
  runId.value = null
  gridData.value = []
  try {
    const params = new URLSearchParams()
    params.set('start_iso_year', String(startIsoYear.value))
    params.set('start_iso_week', String(startIsoWeek.value))
    params.set('horizon_weeks', String(horizonWeeks.value))
    if (warehouseId.value != null) params.set('warehouse_id', String(warehouseId.value))
    const { data } = await api.post<{ run_id: string }>(`/projections/run?${params}`)
    runId.value = data.run_id
    await loadGrid()
  } finally {
    generating.value = false
  }
}

async function loadGrid() {
  if (!runId.value) return
  gridLoading.value = true
  try {
    const params = new URLSearchParams({ run_id: runId.value })
    if (warehouseId.value != null) params.set('warehouse_id', String(warehouseId.value))
    const { data } = await api.get<ProjectionRow[]>(`/projections?${params}`)
    gridData.value = data
  } finally {
    gridLoading.value = false
  }
}

onMounted(async () => {
  const { data: wh } = await api.get<{ id: number; code: string; name: string | null }[]>('/warehouses')
  warehouses.value = wh
  const now = new Date()
  const jan4 = new Date(now.getFullYear(), 0, 4)
  const week1Monday = new Date(jan4)
  week1Monday.setDate(jan4.getDate() - jan4.getDay() + 1)
  const msPerDay = 86400000
  const days = Math.floor((now.getTime() - week1Monday.getTime()) / msPerDay)
  startIsoWeek.value = Math.min(52, Math.floor(days / 7) + 1)
  startIsoYear.value = now.getFullYear()
})
</script>

<style scoped>
.controls { display: flex; flex-wrap: wrap; gap: 0.75rem 1.5rem; align-items: flex-end; }
.form-row { display: flex; flex-direction: column; gap: 0.25rem; }
.form-label { font-size: 0.8125rem; color: var(--muted); }
.grid-wrap { overflow: auto; max-height: min(70vh, 600px); border: 1px solid var(--border); }
.planning-grid { table-layout: fixed; min-width: max-content; }
.planning-grid .sticky-col { position: sticky; left: 0; z-index: 2; background: var(--main-bg); border-right: 1px solid var(--border); min-width: 140px; }
.planning-grid .sticky-header { position: sticky; top: 0; z-index: 3; background: var(--main-bg); }
.planning-grid .sticky-col.sticky-header { z-index: 4; }
.planning-grid .week-header { min-width: 80px; font-size: 0.75rem; }
.planning-grid .row-label { font-size: 0.8125rem; }
.planning-grid .grid-cell { min-width: 72px; font-size: 0.8125rem; text-align: right; }
.planning-grid .grid-cell.cell-status-error { background: rgba(153, 27, 27, 0.12); color: var(--error); }
.planning-grid .grid-cell.cell-status-warning { background: rgba(180, 83, 9, 0.12); color: var(--warning); }
.planning-grid .grid-cell.cell-status-ok { background: rgba(22, 101, 52, 0.08); color: var(--success); }
.app-btn { margin-right: 0.5rem; text-decoration: none; display: inline-block; }
</style>
