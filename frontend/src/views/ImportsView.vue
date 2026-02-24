<template>
  <div class="page-shell space-y-6">
    <header class="page-header">
      <h1>Imports</h1>
      <p class="muted mt-1">Upload CSV. Backbone imports validate and import in one step; legacy imports support dry-run then confirm.</p>
    </header>

    <!-- 2x2 card grid: core imports -->
    <section class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div
        v-for="card in importCards"
        :key="card.type"
        class="card card-body"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <h3 class="text-lg font-medium text-slate-800">{{ card.title }}</h3>
            <p class="text-sm text-slate-600 mt-0.5">{{ card.description }}</p>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2 mt-4">
          <button
            type="button"
            class="btn-primary"
            @click="selectTypeAndUpload(card.type)"
          >
            Upload
          </button>
          <a
            v-if="card.templateHref"
            :href="card.templateHref"
            download
            class="btn-secondary"
          >
            Template
          </a>
        </div>
        <p v-if="selectedType === card.type && file" class="text-xs text-slate-500 mt-2">Selected: {{ file.name }}</p>
      </div>
    </section>

    <!-- Hidden file input for backbone/legacy -->
    <input
      ref="fileInput"
      type="file"
      accept=".csv"
      class="hidden"
      @change="onFileSelect"
    />

    <!-- Actions after file select -->
    <section v-if="file" class="card card-body">
      <h3 class="section-title mb-2">Import: {{ selectedCard?.title ?? importType }}</h3>
      <div class="flex flex-wrap items-center gap-3">
        <template v-if="isBackboneImport">
          <button type="button" class="btn-primary" @click="uploadBackbone">Upload and import</button>
        </template>
        <template v-else>
          <button type="button" class="btn-primary" @click="dryRun">Dry run (validate)</button>
          <button
            type="button"
            class="btn-primary bg-emerald-600 hover:bg-emerald-700"
            :disabled="!legacyResult?.valid_rows"
            @click="confirmImport"
          >
            Confirm import
          </button>
        </template>
        <button type="button" class="btn-secondary" @click="clearFile">Cancel</button>
      </div>
    </section>

    <!-- Backbone result -->
    <section v-if="backboneResult" class="card card-body">
      <h3 class="section-title mb-2">Backbone import result</h3>
      <p class="text-sm text-slate-600">Rows processed: {{ backboneResult.rows_processed }} · Failed: {{ backboneResult.rows_failed }}</p>
      <div v-if="backboneResult.errors?.length" class="mt-3 overflow-x-auto">
        <table class="app-table">
          <thead><tr><th>Row</th><th>Message</th></tr></thead>
          <tbody>
            <tr v-for="(e, i) in backboneResult.errors" :key="i">
              <td>{{ e.row_number }}</td>
              <td>{{ e.message }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Legacy result -->
    <section v-if="legacyResult" class="card card-body">
      <h3 class="section-title mb-2">Result</h3>
      <p class="text-sm text-slate-600">Valid: {{ legacyResult.valid ? 'Yes' : 'No' }} · Total: {{ legacyResult.total_rows }} · Valid rows: {{ legacyResult.valid_rows }}</p>
      <div v-if="legacyResult.errors?.length" class="mt-3 overflow-x-auto">
        <table class="app-table">
          <thead><tr><th>Row</th><th>Errors</th></tr></thead>
          <tbody>
            <tr v-for="e in legacyResult.errors" :key="e.row">
              <td>{{ e.row }}</td>
              <td>{{ e.errors.join(', ') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Collapsible Templates -->
    <section class="card">
      <button
        type="button"
        class="card-header w-full text-left flex items-center justify-between"
        @click="templatesOpen = !templatesOpen"
      >
        <span>Templates</span>
        <span class="text-slate-400">{{ templatesOpen ? '▼' : '▶' }}</span>
      </button>
      <div v-show="templatesOpen" class="card-body border-t border-slate-200">
        <p class="text-sm text-slate-600 mb-2">Backbone: warehouse_code, sku, iso_year, iso_week, on_hand_units (stock positions); inbound_units (inbound); demand_units (demand).</p>
        <ul class="space-y-1 text-sm">
          <li><a href="/api/templates/inventory-snapshots" download class="text-primary-600 hover:underline">Inventory snapshots</a></li>
          <li><a href="/api/templates/receipts" download class="text-primary-600 hover:underline">Receipts</a></li>
          <li><a href="/api/templates/demand-actuals" download class="text-primary-600 hover:underline">Demand actuals</a></li>
          <li><a href="/api/templates/samples-withdrawals" download class="text-primary-600 hover:underline">Samples withdrawals</a></li>
          <li><a href="/api/templates/products" download class="text-primary-600 hover:underline">Products</a></li>
          <li><a href="/api/templates/sku-code-map" download class="text-primary-600 hover:underline">SKU code map</a></li>
          <li><a href="/api/templates/demand-weekly" download class="text-primary-600 hover:underline">Demand weekly (W-TUE)</a></li>
          <li><a href="/api/templates/demand-daily" download class="text-primary-600 hover:underline">Demand daily</a></li>
          <li><a href="/api/templates/stock-on-hand" download class="text-primary-600 hover:underline">Stock On Hand (SOH)</a></li>
          <li><a href="/api/templates/product-master" download class="text-primary-600 hover:underline">Product Master</a></li>
        </ul>
      </div>
    </section>

    <!-- Ingestion pipeline (demand → canonical weekly) -->
    <section class="card card-body">
      <h3 class="section-title mb-2">Ingestion pipeline (demand → canonical weekly)</h3>
      <p class="text-sm text-slate-600 mb-3">Upload demand CSV; stage; then execute to build demand_facts_weekly. Week bucketing: W-TUE.</p>
      <div class="flex flex-wrap items-end gap-3 md:grid md:grid-cols-4">
        <div>
          <label class="form-label">Entity</label>
          <select v-model="ingestionEntity" class="select w-full max-w-xs">
            <option value="demand">Demand</option>
            <option value="product_master">Product Master</option>
            <option value="forecast_output">Forecast output</option>
            <option value="sales_out">Sales Out</option>
            <option value="stock_on_hand">Stock On Hand (SOH)</option>
          </select>
        </div>
        <div>
          <label class="form-label">File</label>
          <input type="file" ref="ingestionFileInput" :accept="ingestionEntity === 'sales_out' || ingestionEntity === 'stock_on_hand' ? '.csv,.xlsx,.xls' : '.csv'" @change="onIngestionFileSelect" class="block w-full text-sm text-slate-600 file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border file:border-slate-300 file:bg-white file:text-slate-700 file:text-sm hover:file:bg-slate-50" />
        </div>
        <div>
          <button type="button" @click="uploadIngestion" :disabled="!ingestionFile" class="btn-primary">Upload &amp; stage</button>
        </div>
      </div>
      <div v-if="ingestionUploadResult" class="mt-3 text-sm text-slate-600 flex flex-wrap items-center gap-2">
        <span>Run ID: <code class="text-xs bg-slate-100 px-1.5 py-0.5 rounded">{{ ingestionUploadResult.run_id.slice(0, 8) }}</code></span>
        <span>Staged {{ ingestionUploadResult.staged_count }}, rejected {{ ingestionUploadResult.rejected_count }}</span>
        <template v-if="ingestionEntity === 'sales_out'">
          <button type="button" @click="buildSalesOutWeekly(ingestionUploadResult.run_id)" class="btn-primary text-sm">Execute build-weekly</button>
        </template>
        <template v-else>
          <button type="button" @click="executeIngestionRun(ingestionUploadResult.run_id)" class="btn-secondary text-sm">Execute transform</button>
        </template>
      </div>
    </section>

    <!-- Sales Out (big transactional file → W-TUE demand) -->
    <section class="card card-body">
      <h3 class="section-title mb-2">Sales Out</h3>
      <p class="text-sm text-slate-600 mb-3">Upload CSV or XLSX (AAH_Product_Code, Invoiced_Qty, Business_Processed_Date DD/MM/YYYY, etc.). Stage then build weekly demand (AAH, W-TUE).</p>
      <div class="flex flex-wrap items-end gap-3 md:grid md:grid-cols-4">
        <div>
          <label class="form-label">File</label>
          <input type="file" ref="salesOutFileInput" accept=".csv,.xlsx,.xls" @change="onSalesOutFileSelect" class="block w-full text-sm text-slate-600 file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border file:border-slate-300 file:bg-white file:text-slate-700 file:text-sm hover:file:bg-slate-50" />
        </div>
        <div>
          <button type="button" @click="uploadSalesOut" :disabled="!salesOutFile" class="btn-primary">Upload &amp; stage</button>
        </div>
      </div>
      <div v-if="salesOutUploadResult" class="mt-3 text-sm text-slate-600 flex flex-wrap items-center gap-2">
        <span>Run ID: <code class="text-xs bg-slate-100 px-1.5 py-0.5 rounded">{{ salesOutUploadResult.run_id.slice(0, 8) }}</code></span>
        <span>Staged {{ salesOutUploadResult.staged_count }}, rejected {{ salesOutUploadResult.rejected_count }}</span>
        <button type="button" @click="buildSalesOutWeekly(salesOutUploadResult.run_id)" class="btn-primary text-sm">Execute build-weekly</button>
      </div>
      <div v-if="salesOutBuildResult" class="mt-2 text-sm text-slate-600">
        <span>Rows staged: {{ salesOutBuildResult.rows_staged }}</span>
        <span>Weeks written: {{ salesOutBuildResult.weeks_written }}</span>
        <span>Rows rejected: {{ salesOutBuildResult.rows_rejected }}</span>
      </div>
    </section>

    <!-- Stock On Hand (SOH): daily history → weekly canonical -->
    <section class="card card-body">
      <h3 class="section-title mb-2">Stock On Hand (SOH)</h3>
      <p class="text-sm text-slate-600 mb-3">Upload CSV or XLSX: Stock at (date), Branch Name, AAH Code, STOCK, ON ORDER. Branch Name must exist in warehouse branch mapping. Stage then Execute to build daily and weekly canonical (W-TUE).</p>
      <div class="flex flex-wrap items-center gap-2 mb-2">
        <a href="/api/templates/stock-on-hand" download class="btn-secondary">Download SOH template</a>
      </div>
      <div class="flex flex-wrap items-end gap-3 md:grid md:grid-cols-4">
        <div>
          <label class="form-label">File</label>
          <input type="file" ref="sohFileInput" accept=".csv,.xlsx,.xls" @change="onSohFileSelect" class="block w-full text-sm text-slate-600 file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border file:border-slate-300 file:bg-white file:text-slate-700 file:text-sm hover:file:bg-slate-50" />
        </div>
        <div>
          <button type="button" @click="uploadSoh" :disabled="!sohFile" class="btn-primary">Upload &amp; stage</button>
        </div>
      </div>
      <div v-if="sohUploadResult" class="mt-3 text-sm text-slate-600 flex flex-wrap items-center gap-2">
        <span>Run ID: <code class="text-xs bg-slate-100 px-1.5 py-0.5 rounded">{{ sohUploadResult.run_id.slice(0, 8) }}</code></span>
        <span>Staged {{ sohUploadResult.staged_count }}, rejected {{ sohUploadResult.rejected_count }}</span>
        <button type="button" @click="executeSohRun(sohUploadResult.run_id)" class="btn-primary text-sm">Execute (daily → weekly)</button>
      </div>
    </section>

    <!-- Ingestion runs table -->
    <section class="card">
      <div class="card-header flex items-center justify-between">
        <h3 class="section-title mb-0">Ingestion runs</h3>
        <button type="button" @click="loadIngestionRuns" class="btn-secondary text-sm">Refresh</button>
      </div>
      <div class="overflow-x-auto">
        <DataTable
          :columns="runColumns"
          :rows="ingestionRunsForTable"
          row-key="id"
          density="compact"
        >
          <template #cell-id="{ value }">
            <code class="text-xs bg-slate-100 px-1.5 py-0.5 rounded">{{ String(value).slice(0, 8) }}</code>
          </template>
          <template #cell-status="{ value }">
            <span :class="statusBadgeClass(String(value ?? ''))">{{ value }}</span>
          </template>
          <template #cell-actions="{ row }">
            <button type="button" @click="openRunDrawer(getRunRow(row))" class="btn-secondary text-xs py-1 px-2">Details</button>
            <button v-if="getRunRow(row).status === 'pending'" type="button" @click="executePendingRun(row)" class="btn-primary text-xs py-1 px-2 ml-1">Execute</button>
          </template>
          <template #empty>
            <p class="text-slate-500">No runs yet. Upload and stage a file above.</p>
          </template>
        </DataTable>
      </div>
    </section>

    <!-- Run detail drawer -->
    <div v-if="drawerRunId" class="fixed inset-0 bg-black/30 z-100 flex justify-end" @click.self="closeRunDrawer">
      <div class="w-full max-w-md bg-white shadow-xl overflow-auto">
        <div class="flex justify-between items-center px-5 py-3 border-b border-slate-200">
          <h3 class="text-lg font-medium">Run {{ drawerRunId?.slice(0, 8) }}</h3>
          <button type="button" @click="closeRunDrawer" class="text-slate-500 hover:text-slate-700 text-2xl leading-none">×</button>
        </div>
        <div v-if="drawerRun" class="p-5 space-y-3 text-sm">
          <p><strong>Status:</strong> {{ drawerRun.status }}</p>
          <p><strong>Entity:</strong> {{ drawerRun.entity }}</p>
          <p><strong>File:</strong> {{ drawerRun.file_name || '—' }}</p>
          <p><strong>Rows:</strong> {{ drawerRun.row_count }} — Inserted: {{ drawerRun.inserted_count }}, Updated: {{ drawerRun.updated_count }}, Rejected: {{ drawerRun.rejected_count }}</p>
          <p v-if="drawerRun.error_summary" class="text-red-600">{{ drawerRun.error_summary }}</p>
          <h4 class="font-medium text-slate-800 mt-4">Rejections sample</h4>
          <div class="overflow-x-auto">
            <table class="app-table">
              <thead><tr><th>Row</th><th>Reason</th><th>Payload</th></tr></thead>
              <tbody>
                <tr v-for="(rej, i) in drawerRun.rejections_sample" :key="i">
                  <td>{{ rej.row_number }}</td>
                  <td>{{ rej.reason }}</td>
                  <td><pre class="text-xs max-w-48 overflow-auto whitespace-pre-wrap">{{ JSON.stringify(rej.raw_payload) }}</pre></td>
                </tr>
              </tbody>
            </table>
          </div>
          <button type="button" @click="downloadRejectionsCsv" class="btn-secondary">Download rejections CSV</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '@/api/client'
import DataTable from '@/components/console/DataTable.vue'
import type { DataTableColumn } from '@/components/console/DataTable.vue'
import type { ImportDryRunResult, BackboneImportResult } from '@/api/client'

interface IngestionRunRow {
  id: string
  entity: string
  file_name: string | null
  status: string
  row_count: number
  inserted_count: number
  updated_count: number
  rejected_count: number
  started_at: string | null
}
interface IngestionRunDetail extends IngestionRunRow {
  rejections_sample: { row_number: number; reason: string; raw_payload: unknown }[]
  error_summary: string | null
}
interface IngestionUploadResult {
  run_id: string
  row_count: number
  staged_count: number
  rejected_count: number
}

type ImportType =
  | 'backbone-stock-positions'
  | 'backbone-inbound-orders'
  | 'backbone-demand-weekly'
  | 'inventory-snapshots'
  | 'receipts'
  | 'demand-actuals'
  | 'samples-withdrawals'
  | 'products'

const importCards = [
  { type: 'backbone-stock-positions' as ImportType, title: 'Stock positions weekly', description: 'Warehouse, SKU, iso year/week, on_hand_units.', templateHref: null },
  { type: 'backbone-inbound-orders' as ImportType, title: 'Inbound orders weekly', description: 'Warehouse, SKU, iso year/week, inbound_units.', templateHref: null },
  { type: 'backbone-demand-weekly' as ImportType, title: 'Demand weekly', description: 'Warehouse, SKU, iso year/week, demand_units.', templateHref: '/api/templates/demand-weekly' },
  { type: 'products' as ImportType, title: 'Product master', description: 'Legacy product import. Dry run then confirm.', templateHref: '/api/templates/product-master' },
]

const runColumns: DataTableColumn[] = [
  { key: 'id', label: 'Run ID', format: 'text' },
  { key: 'entity', label: 'Entity' },
  { key: 'file_name', label: 'File' },
  { key: 'status', label: 'Status' },
  { key: 'row_count', label: 'Rows', align: 'right' },
  { key: 'inserted_count', label: 'Inserted', align: 'right' },
  { key: 'updated_count', label: 'Updated', align: 'right' },
  { key: 'rejected_count', label: 'Rejected', align: 'right' },
  { key: 'started_at', label: 'Started' },
  { key: 'actions', label: '' },
]

const importType = ref<ImportType>('backbone-stock-positions')
const selectedType = ref<ImportType>('backbone-stock-positions')
const fileInput = ref<HTMLInputElement | null>(null)
const file = ref<File | null>(null)
const legacyResult = ref<ImportDryRunResult | null>(null)
const backboneResult = ref<BackboneImportResult | null>(null)
const templatesOpen = ref(false)

const ingestionEntity = ref<'demand' | 'product_master' | 'forecast_output' | 'sales_out' | 'stock_on_hand'>('demand')
const ingestionFileInput = ref<HTMLInputElement | null>(null)
const ingestionFile = ref<File | null>(null)
const ingestionUploadResult = ref<IngestionUploadResult | null>(null)
const ingestionRuns = ref<IngestionRunRow[]>([])
const drawerRunId = ref<string | null>(null)
const drawerRun = ref<IngestionRunDetail | null>(null)

const salesOutFileInput = ref<HTMLInputElement | null>(null)
const salesOutFile = ref<File | null>(null)
const salesOutUploadResult = ref<IngestionUploadResult | null>(null)
const salesOutBuildResult = ref<{ rows_staged: number; weeks_written: number; rows_rejected: number } | null>(null)

const sohFileInput = ref<HTMLInputElement | null>(null)
const sohFile = ref<File | null>(null)
const sohUploadResult = ref<IngestionUploadResult | null>(null)

const selectedCard = computed(() => importCards.find((c) => c.type === selectedType.value))

const isBackboneImport = computed(() =>
  selectedType.value === 'backbone-stock-positions' ||
  selectedType.value === 'backbone-inbound-orders' ||
  selectedType.value === 'backbone-demand-weekly'
)

const backboneEndpoint = computed(() => {
  if (selectedType.value === 'backbone-stock-positions') return '/backbone/import/stock-positions'
  if (selectedType.value === 'backbone-inbound-orders') return '/backbone/import/inbound-orders'
  if (selectedType.value === 'backbone-demand-weekly') return '/backbone/import/demand-weekly'
  return ''
})

const ingestionRunsForTable = computed(() =>
  ingestionRuns.value.map((r) => ({
    ...r,
    file_name: r.file_name || '—',
    started_at: r.started_at ? formatDate(r.started_at) : '—',
    actions: '',
  }))
)

function selectTypeAndUpload(type: ImportType) {
  importType.value = type
  selectedType.value = type
  legacyResult.value = null
  backboneResult.value = null
  fileInput.value?.click()
}

function onFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  file.value = target.files?.[0] ?? null
  legacyResult.value = null
  backboneResult.value = null
}

function clearFile() {
  file.value = null
  if (fileInput.value) fileInput.value.value = ''
}

async function uploadBackbone() {
  if (!file.value || !backboneEndpoint.value) return
  const form = new FormData()
  form.append('file', file.value)
  const { data } = await api.post<BackboneImportResult>(backboneEndpoint.value, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  backboneResult.value = data
  file.value = null
  if (fileInput.value) fileInput.value.value = ''
}

async function dryRun() {
  if (!file.value) return
  const form = new FormData()
  form.append('file', file.value)
  const legacyType = selectedType.value as 'inventory-snapshots' | 'receipts' | 'demand-actuals' | 'samples-withdrawals' | 'products'
  const { data } = await api.post<ImportDryRunResult>(`/import/${legacyType}?dry_run=true`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  legacyResult.value = data
}

async function confirmImport() {
  if (!file.value) return
  const form = new FormData()
  form.append('file', file.value)
  const legacyType = selectedType.value as 'inventory-snapshots' | 'receipts' | 'demand-actuals' | 'samples-withdrawals' | 'products'
  const { data } = await api.post<ImportDryRunResult>(`/import/${legacyType}?dry_run=false`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  legacyResult.value = data
  file.value = null
  if (fileInput.value) fileInput.value.value = ''
}

function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function getRunRow(row: Record<string, unknown>): { id: string; status: string } {
  return { id: String(row.id), status: String(row.status ?? '') }
}

function runEntity(row: Record<string, unknown>): string {
  return String(row.entity ?? '')
}

function executePendingRun(row: Record<string, unknown>) {
  const id = String(row.id)
  const entity = runEntity(row)
  if (entity === 'stock_on_hand') executeSohRun(id)
  else if (entity === 'sales_out') buildSalesOutWeekly(id)
  else executeIngestionRun(id)
}

function statusBadgeClass(status: string) {
  const s = String(status).toLowerCase()
  if (s === 'success') return 'badge-success'
  if (s === 'failed') return 'badge-danger'
  if (s === 'running') return 'badge-info'
  if (s === 'pending') return 'badge-warn'
  return 'badge-info'
}

function onIngestionFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  ingestionFile.value = target.files?.[0] ?? null
  ingestionUploadResult.value = null
}

async function uploadIngestion() {
  if (!ingestionFile.value) return
  const form = new FormData()
  form.append('file', ingestionFile.value)
  try {
    const { data } = await api.post<IngestionUploadResult>('/ingestion/upload', form, {
      params: { entity: ingestionEntity.value },
    })
    ingestionUploadResult.value = data
    ingestionFile.value = null
    if (ingestionFileInput.value) ingestionFileInput.value.value = ''
    await loadIngestionRuns()
  } catch (err: unknown) {
    const msg = err && typeof err === 'object' && 'response' in err
      ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      : null
    alert(msg ? `Upload failed: ${typeof msg === 'string' ? msg : JSON.stringify(msg)}` : 'Upload failed. Check the file format and try again.')
  }
}

function onSalesOutFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  salesOutFile.value = target.files?.[0] ?? null
  salesOutUploadResult.value = null
  salesOutBuildResult.value = null
}

async function uploadSalesOut() {
  if (!salesOutFile.value) return
  const form = new FormData()
  form.append('file', salesOutFile.value)
  try {
    const { data } = await api.post<IngestionUploadResult>('/ingestion/sales-out/upload', form)
    salesOutUploadResult.value = data
    salesOutFile.value = null
    if (salesOutFileInput.value) salesOutFileInput.value.value = ''
    await loadIngestionRuns()
  } catch (err: unknown) {
    const msg = err && typeof err === 'object' && 'response' in err
      ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      : null
    alert(msg ? `Upload failed: ${typeof msg === 'string' ? msg : JSON.stringify(msg)}` : 'Upload failed. Check the file format and try again.')
  }
}

async function buildSalesOutWeekly(runId: string) {
  try {
    const { data } = await api.post<{ run_id: string; status: string; rows_staged: number; weeks_written: number; rows_rejected: number }>(
      `/ingestion/sales-out/${runId}/build-weekly`
    )
    salesOutBuildResult.value = {
      rows_staged: data.rows_staged,
      weeks_written: data.weeks_written,
      rows_rejected: data.rows_rejected,
    }
    await loadIngestionRuns()
  } catch (err: unknown) {
    const msg = err && typeof err === 'object' && 'response' in err
      ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      : null
    alert(msg ? `Build failed: ${typeof msg === 'string' ? msg : JSON.stringify(msg)}` : 'Build failed.')
  }
}

function onSohFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  sohFile.value = target.files?.[0] ?? null
  sohUploadResult.value = null
}

async function uploadSoh() {
  if (!sohFile.value) return
  const form = new FormData()
  form.append('file', sohFile.value)
  try {
    const { data } = await api.post<IngestionUploadResult>('/ingestion/stock-on-hand/upload', form)
    sohUploadResult.value = data
    sohFile.value = null
    if (sohFileInput.value) sohFileInput.value.value = ''
    await loadIngestionRuns()
  } catch (err: unknown) {
    const msg = err && typeof err === 'object' && 'response' in err
      ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      : null
    alert(msg ? `Upload failed: ${typeof msg === 'string' ? msg : JSON.stringify(msg)}` : 'Upload failed. Check the file format and branch mapping.')
  }
}

async function executeSohRun(runId: string) {
  try {
    await api.post(`/ingestion/stock-on-hand/${runId}/execute`)
    await loadIngestionRuns()
    if (drawerRunId.value === runId) {
      const { data } = await api.get<IngestionRunDetail>(`/ingestion/runs/${runId}`)
      drawerRun.value = data
    }
    sohUploadResult.value = null
  } catch (err: unknown) {
    const msg = err && typeof err === 'object' && 'response' in err
      ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      : null
    alert(msg ? `Execute failed: ${typeof msg === 'string' ? msg : JSON.stringify(msg)}` : 'Execute failed.')
  }
}

async function loadIngestionRuns() {
  const { data } = await api.get<IngestionRunRow[]>('/ingestion/runs', { params: { limit: 50 } })
  ingestionRuns.value = data
}

async function executeIngestionRun(runId: string) {
  await api.post(`/ingestion/runs/${runId}/execute`)
  await loadIngestionRuns()
  if (drawerRunId.value === runId) {
    const { data } = await api.get<IngestionRunDetail>(`/ingestion/runs/${runId}`)
    drawerRun.value = data
  }
  ingestionUploadResult.value = null
}

async function openRunDrawer(row: { id: string }) {
  const id = String(row.id)
  drawerRunId.value = id
  const { data } = await api.get<IngestionRunDetail>(`/ingestion/runs/${id}`)
  drawerRun.value = data
}

function closeRunDrawer() {
  drawerRunId.value = null
  drawerRun.value = null
}

function downloadRejectionsCsv() {
  if (!drawerRun.value?.rejections_sample?.length) return
  const headers = ['row_number', 'reason', 'raw_payload']
  const rows = drawerRun.value.rejections_sample.map((r) => [
    r.row_number,
    r.reason,
    typeof r.raw_payload === 'object' ? JSON.stringify(r.raw_payload) : String(r.raw_payload),
  ])
  const csv = [headers.join(','), ...rows.map((row) => row.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(','))].join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `rejections_${drawerRunId.value?.slice(0, 8) ?? 'run'}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}

onMounted(() => {
  loadIngestionRuns()
})
</script>

<style scoped>
.section-title {
  font-size: 1rem;
  font-weight: 500;
  color: rgb(30 41 59);
}
</style>
