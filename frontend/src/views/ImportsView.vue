<template>
  <div class="page-shell space-y-6">
    <header class="page-header">
      <h1>Imports</h1>
      <p class="muted mt-1">Warehouse-first imports. Select warehouse and data type to upload.</p>
    </header>

    <!-- Top-level selectors -->
    <section class="card card-body">
      <div class="flex flex-wrap items-end gap-4">
        <div>
          <label class="form-label">Warehouse</label>
          <select v-model="warehouse" class="select" @change="onWarehouseChange">
            <option v-for="opt in WAREHOUSE_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </div>
        <div>
          <label class="form-label">Data type</label>
          <select v-model="selectedDataType" class="select">
            <option v-for="c in visibleCards" :key="c.id" :value="c.dataType">{{ c.title }}</option>
          </select>
        </div>
      </div>
    </section>

    <!-- Single card for selected data type -->
    <section v-if="selectedCard && !selectedCard.linkHref" class="card card-body">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <h3 class="text-lg font-medium text-slate-800">{{ selectedCard.title }}</h3>
          <p class="text-sm text-slate-600 mt-0.5">
            <strong>Format:</strong> {{ selectedCard.formatName }} · <strong>Target:</strong> {{ selectedCard.targetWarehouse }}
          </p>
          <p class="text-xs text-slate-500 mt-1">Required columns: {{ selectedCard.requiredColumns.join(', ') || '—' }}</p>
        </div>
      </div>

      <!-- Last run summary -->
      <div v-if="lastRun" class="mt-3 p-3 rounded-lg bg-slate-50 text-sm">
        <strong>Last run:</strong>
        <span :class="lastRun.status === 'success' ? 'text-green-700' : lastRun.status === 'failed' ? 'text-red-700' : 'text-slate-600'">
          {{ lastRun.status }}
        </span>
        · inserted {{ lastRun.inserted_count }}, rejected {{ lastRun.rejected_count }}
        <span v-if="lastRun.finished_at" class="text-slate-500">· {{ formatDateShort(lastRun.finished_at) }}</span>
      </div>
      <p v-else-if="lastRunLoaded && !lastRun" class="mt-3 text-sm text-slate-500">No runs yet for this entity.</p>

      <div class="flex flex-wrap items-center gap-2 mt-4">
        <a v-if="selectedCard.templateHref" :href="selectedCard.templateHref" download class="btn-secondary">Template</a>
        <template v-if="selectedCard.dataType === 'sales_out'">
          <input type="file" ref="salesOutFileInput" accept=".csv,.xlsx,.xls" class="hidden" @change="onSalesOutFileSelect" />
          <button type="button" class="btn-primary" :disabled="salesOutUploading" @click="salesOutFileInput?.click()">
            {{ salesOutUploading ? 'Uploading…' : 'Upload (weekly)' }}
          </button>
          <button
            v-if="selectedCard.supportsHistorical"
            type="button"
            class="btn-secondary border-amber-300 text-amber-800 hover:bg-amber-50"
            :disabled="salesOutUploading"
            @click="salesOutFileInput?.click()"
          >
            Upload historical backfill
          </button>
        </template>
        <template v-else-if="selectedCard.dataType === 'stock_on_hand'">
          <button type="button" class="btn-secondary" :disabled="sohTemplateDownloading" @click="downloadSohTemplate">
            {{ sohTemplateDownloading ? 'Downloading…' : 'Download template' }}
          </button>
          <input type="file" ref="sohFileInput" accept=".csv,.xlsx,.xls" class="hidden" @change="onSohFileSelect" />
          <button type="button" class="btn-primary" :disabled="sohUploading" @click="sohFileInput?.click()">
            {{ sohUploading ? 'Uploading…' : 'Upload (weekly)' }}
          </button>
          <button
            v-if="selectedCard.supportsHistorical && !isBlpSohHistoricalDisabled"
            type="button"
            class="btn-secondary border-amber-300 text-amber-800 hover:bg-amber-50"
            :disabled="sohUploading"
            @click="sohFileInput?.click()"
          >
            Upload historical backfill
          </button>
          <p v-else-if="selectedCard.supportsHistorical && selectedCard.historicalDisabledMessage" class="text-sm text-amber-700">
            {{ selectedCard.historicalDisabledMessage }}
          </p>
        </template>
        <template v-else-if="selectedCard.dataType === 'demand_pipeline' || selectedCard.dataType === 'sales_direct' || selectedCard.dataType === 'samples'">
          <input type="file" ref="demandFileInput" accept=".csv" class="hidden" @change="onDemandFileSelect" />
          <button type="button" class="btn-primary" :disabled="demandUploading" @click="demandFileInput?.click()">
            {{ demandUploading ? 'Uploading…' : 'Upload (weekly)' }}
          </button>
          <button
            v-if="selectedCard.supportsHistorical"
            type="button"
            class="btn-secondary border-amber-300 text-amber-800 hover:bg-amber-50"
            :disabled="demandUploading"
            @click="demandFileInput?.click()"
          >
            Upload historical backfill
          </button>
        </template>
        <template v-else-if="selectedCard.dataType === 'product_master'">
          <input type="file" ref="productMasterFileInput" accept=".csv" class="hidden" @change="onProductMasterFileSelect" />
          <button type="button" class="btn-primary" :disabled="productMasterUploading" @click="productMasterFileInput?.click()">
            {{ productMasterUploading ? 'Uploading…' : 'Upload' }}
          </button>
        </template>
      </div>

      <!-- Sales Out: file + date range + execute -->
      <div v-if="selectedCard?.dataType === 'sales_out' && salesOutFile" class="mt-4 space-y-3">
        <p class="text-xs text-slate-500">Selected: {{ salesOutFile.name }}</p>
        <div class="flex flex-wrap gap-3">
          <div>
            <label class="form-label text-xs">Date from (historical)</label>
            <input v-model="salesOutDateFrom" type="date" class="input w-full max-w-[160px]" />
          </div>
          <div>
            <label class="form-label text-xs">Date to (historical)</label>
            <input v-model="salesOutDateTo" type="date" class="input w-full max-w-[160px]" />
          </div>
          <button type="button" class="btn-secondary text-xs self-end" @click="setSalesOutLast24Months">Set last 24 months</button>
        </div>
        <div class="flex gap-2">
          <button type="button" class="btn-primary" :disabled="salesOutUploading" @click="uploadSalesOutWithMode('weekly')">Upload (weekly)</button>
          <button type="button" class="btn-secondary border-amber-300" :disabled="salesOutUploading" @click="uploadSalesOutWithMode('historical')">Upload historical</button>
        </div>
      </div>

      <!-- SOH: file + warehouse + snapshot date + execute -->
      <div v-if="selectedCard?.dataType === 'stock_on_hand' && sohFile" class="mt-4 space-y-3">
        <p class="text-xs text-slate-500">Selected: {{ sohFile.name }}</p>
        <div class="flex flex-wrap gap-3">
          <div>
            <label class="form-label text-xs">Warehouse</label>
            <select v-model="sohWarehouseCode" class="select">
              <option value="">—</option>
              <option v-for="w in activeWarehouses" :key="w.id" :value="w.code">{{ w.code }} – {{ w.name || '—' }}</option>
            </select>
          </div>
          <div>
            <label class="form-label text-xs">Snapshot date</label>
            <input v-model="sohSnapshotDate" type="date" class="input w-full max-w-[160px]" />
          </div>
        </div>
        <div class="flex gap-2">
          <button type="button" class="btn-primary" :disabled="sohUploading" @click="uploadSohWithMode('weekly')">Upload (weekly)</button>
          <button
            v-if="selectedCard.supportsHistorical && !isBlpSohHistoricalDisabled"
            type="button"
            class="btn-secondary border-amber-300"
            :disabled="sohUploading"
            @click="uploadSohWithMode('historical')"
          >
            Upload historical
          </button>
        </div>
      </div>

      <!-- Demand: upload then execute -->
      <div v-if="(selectedCard?.dataType === 'demand_pipeline' || selectedCard?.dataType === 'sales_direct' || selectedCard?.dataType === 'samples') && demandFile" class="mt-4">
        <p class="text-xs text-slate-500">Selected: {{ demandFile.name }}</p>
        <div class="flex gap-2 mt-2">
          <button type="button" class="btn-primary" :disabled="demandUploading" @click="uploadDemandWithMode('weekly')">Upload (weekly)</button>
          <button v-if="selectedCard.supportsHistorical" type="button" class="btn-secondary border-amber-300" :disabled="demandUploading" @click="uploadDemandWithMode('historical')">Upload historical</button>
        </div>
      </div>

      <!-- Product master: upload then execute -->
      <div v-if="selectedCard?.dataType === 'product_master' && productMasterFile" class="mt-4">
        <p class="text-xs text-slate-500">Selected: {{ productMasterFile.name }}</p>
        <button type="button" class="btn-primary mt-2" :disabled="productMasterUploading" @click="uploadProductMaster">Upload</button>
      </div>

      <!-- Upload result + execute -->
      <div v-if="currentUploadResult" class="mt-4 p-3 rounded-lg bg-slate-50 text-sm flex flex-wrap items-center gap-2">
        <span>Run ID: <code class="text-xs bg-slate-200 px-1.5 py-0.5 rounded">{{ currentUploadResult.run_id.slice(0, 8) }}</code></span>
        <span>Staged {{ currentUploadResult.staged_count }}, rejected {{ currentUploadResult.rejected_count }}</span>
        <span v-if="currentUploadResult.mode" class="badge" :class="currentUploadResult.mode === 'historical' ? 'badge-warn' : 'badge-info'">{{ currentUploadResult.mode }}</span>
        <button v-if="currentUploadResult.requires_confirm" type="button" class="btn-secondary text-sm border-amber-300" @click="showConfirmModal(currentUploadResult)">Confirm backfill</button>
        <button
          v-if="needsExecute"
          type="button"
          class="btn-primary text-sm"
          :disabled="(currentUploadResult.requires_confirm && !currentUploadResult.confirmed) || executing"
          @click="executeCurrentRun"
        >
          {{ executing ? 'Executing…' : executeButtonLabel }}
        </button>
      </div>
      <div v-if="sohUploadResult?.rejected_count > 0 && sohRejectionDetail" class="mt-3 rounded-lg text-sm border" :class="sohUploadResult.staged_count === 0 ? 'border-amber-300 bg-amber-50 text-amber-900' : 'border-slate-200 bg-slate-50'">
        <div class="px-3 py-2 flex items-center justify-between gap-2">
          <p class="font-semibold">
            {{ sohUploadResult.staged_count === 0
              ? `All ${sohUploadResult.rejected_count} rows rejected.`
              : `${sohUploadResult.rejected_count} rows rejected.` }}
          </p>
          <span v-if="sohRejectionDetail.rejections_sample.length < sohUploadResult.rejected_count" class="text-xs opacity-70">
            Showing first {{ sohRejectionDetail.rejections_sample.length }} of {{ sohUploadResult.rejected_count }}
          </span>
        </div>
        <p v-if="sohRejectionDetail.error_summary" class="px-3 pb-2 text-xs opacity-80">{{ sohRejectionDetail.error_summary }}</p>
        <table v-if="sohRejectionDetail.rejections_sample.length" class="w-full text-xs border-t border-current border-opacity-20">
          <thead>
            <tr class="opacity-60">
              <th class="text-left px-3 py-1.5 font-medium w-16">Row</th>
              <th class="text-left px-3 py-1.5 font-medium">Reason</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(rej, i) in sohRejectionDetail.rejections_sample" :key="i" class="border-t border-current border-opacity-10">
              <td class="px-3 py-1.5 font-mono">{{ rej.row_number }}</td>
              <td class="px-3 py-1.5">{{ rej.reason }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Link-only card (Warehouse Product Codes) -->
    <section v-else-if="selectedCard?.linkHref" class="card card-body">
      <h3 class="text-lg font-medium text-slate-800">{{ selectedCard.title }}</h3>
      <p class="text-sm text-slate-600 mt-1">Map BLP external codes to canonical SKUs before importing BLP SOH.</p>
      <router-link :to="selectedCard.linkHref" class="btn-primary mt-3 inline-block">{{ selectedCard.linkLabel || 'Open' }}</router-link>
    </section>

    <!-- Ingestion runs table -->
    <section class="card">
      <div class="card-header flex items-center justify-between">
        <h3 class="section-title mb-0">Ingestion runs</h3>
        <button type="button" class="btn-secondary text-sm" @click="loadIngestionRuns">Refresh</button>
      </div>
      <div class="overflow-x-auto">
        <DataTable :columns="runColumns" :rows="ingestionRunsForTable" row-key="id" density="compact">
          <template #cell-id="{ value }">
            <code class="text-xs bg-slate-100 px-1.5 py-0.5 rounded">{{ String(value).slice(0, 8) }}</code>
          </template>
          <template #cell-status="{ value }">
            <span :class="statusBadgeClass(String(value ?? ''))">{{ value }}</span>
          </template>
          <template #cell-actions="{ row }">
            <button type="button" class="btn-secondary text-xs py-1 px-2" @click="openRunDrawer(getRunRow(row))">Details</button>
            <button v-if="getRunRow(row).status === 'pending'" type="button" class="btn-primary text-xs py-1 px-2 ml-1" @click="executePendingRun(row)">Execute</button>
          </template>
          <template #empty>
            <p class="text-slate-500">No runs yet. Upload a file above.</p>
          </template>
        </DataTable>
      </div>
    </section>

    <!-- Confirmation modal -->
    <div v-if="confirmModalRun" class="fixed inset-0 bg-black/30 z-200 flex items-center justify-center" @click.self="closeConfirmModal">
      <div class="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 p-5">
        <h3 class="text-lg font-medium text-slate-800 mb-2">Confirm historical backfill</h3>
        <p class="text-sm text-slate-600 mb-3">This looks like a historical backfill. Please review before proceeding.</p>
        <dl class="space-y-1 text-sm mb-4">
          <div class="flex justify-between"><dt class="text-slate-500">Rows:</dt><dd class="font-medium">{{ confirmModalRun.row_count?.toLocaleString() }}</dd></div>
          <div class="flex justify-between"><dt class="text-slate-500">Date span:</dt><dd class="font-medium">{{ confirmModalRun.date_min }} – {{ confirmModalRun.date_max }}</dd></div>
        </dl>
        <div class="flex justify-end gap-2">
          <button type="button" class="btn-secondary" @click="closeConfirmModal">Cancel</button>
          <button type="button" class="btn-primary bg-amber-600 hover:bg-amber-700" @click="confirmBackfill">Confirm backfill</button>
        </div>
      </div>
    </div>

    <!-- Run detail drawer -->
    <div v-if="drawerRunId" class="fixed inset-0 bg-black/30 z-100 flex justify-end" @click.self="closeRunDrawer">
      <div class="w-full max-w-md bg-white shadow-xl overflow-auto">
        <div class="flex justify-between items-center px-5 py-3 border-b border-slate-200">
          <h3 class="text-lg font-medium">Run {{ drawerRunId?.slice(0, 8) }}</h3>
          <button type="button" class="text-slate-500 hover:text-slate-700 text-2xl leading-none" @click="closeRunDrawer">×</button>
        </div>
        <div v-if="drawerRun" class="p-5 space-y-3 text-sm">
          <p><strong>Status:</strong> {{ drawerRun.status }}</p>
          <p><strong>Entity:</strong> {{ drawerRun.entity }}</p>
          <p><strong>File:</strong> {{ drawerRun.file_name || '—' }}</p>
          <p><strong>Rows:</strong> {{ drawerRun.row_count }} — Inserted: {{ drawerRun.inserted_count }}, Rejected: {{ drawerRun.rejected_count }}</p>
          <p v-if="drawerRun.error_summary" class="text-red-600">{{ drawerRun.error_summary }}</p>
          <h4 class="font-medium text-slate-800 mt-4">Rejections sample</h4>
          <div class="overflow-x-auto">
            <table class="app-table">
              <thead><tr><th>Row</th><th>Reason</th></tr></thead>
              <tbody>
                <tr v-for="(rej, i) in drawerRun.rejections_sample" :key="i">
                  <td>{{ rej.row_number }}</td>
                  <td>{{ rej.reason }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <button type="button" class="btn-secondary" @click="downloadRejectionsCsv">Download rejections CSV</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api/client'
import { useAdminStore } from '@/stores/admin'
import { useBannerStore } from '@/stores/banner'
import DataTable from '@/components/console/DataTable.vue'
import type { DataTableColumn } from '@/components/console/DataTable.vue'
import {
  IMPORT_CARDS_BY_WAREHOUSE,
  WAREHOUSE_OPTIONS,
  getStoredWarehouse,
  setStoredWarehouse,
  type WarehouseCode,
  type ImportCardDef,
} from '@/config/importCards'

interface IngestionRunRow {
  id: string
  entity: string
  file_name: string | null
  status: string
  row_count: number
  inserted_count: number
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
  mode?: string
  requires_confirm?: boolean
  confirmed?: boolean
  date_min?: string
  date_max?: string
  import_summary?: { distinct_skus: number; total_qty: number; row_count: number; parsing_errors: number }
}
interface LatestRun {
  id: string
  entity: string
  status: string
  inserted_count: number
  rejected_count: number
  finished_at: string | null
}

const route = useRoute()
const router = useRouter()
const adminStore = useAdminStore()
const bannerStore = useBannerStore()
const activeWarehouses = computed(() => adminStore.warehouses.filter((w) => w.active))

const warehouse = ref<WarehouseCode>(getStoredWarehouse())
const selectedDataType = ref<string>('')
const lastRun = ref<LatestRun | null>(null)
const lastRunLoaded = ref(false)

// Declared here (before its watch) to avoid temporal dead zone
const sohWarehouseCode = ref('')

const visibleCards = computed(() => IMPORT_CARDS_BY_WAREHOUSE[warehouse.value] || [])
const selectedCard = computed(() => visibleCards.value.find((c) => c.dataType === selectedDataType.value) || visibleCards.value[0])

const isBlpSohHistoricalDisabled = computed(
  () => warehouse.value === 'BLP' && selectedDataType.value === 'stock_on_hand'
)

watch(visibleCards, (cards) => {
  if (cards.length && !cards.some((c) => c.dataType === selectedDataType.value)) {
    selectedDataType.value = cards[0].dataType
  }
}, { immediate: true })

watch(warehouse, (wh) => {
  sohWarehouseCode.value = wh
}, { immediate: true })

watch(selectedCard, async (card) => {
  if (card?.entity) {
    lastRunLoaded.value = false
    lastRun.value = null
    try {
      const entityMap: Record<string, string> = {
        sales_out: 'sales_out',
        stock_on_hand: 'stock_on_hand',
        demand_pipeline: 'demand',
        sales_direct: 'demand',
        samples: 'demand',
        product_master: 'product_master',
      }
      const entity = entityMap[card.dataType] || card.entity
      const { data } = await api.get<LatestRun | null>('/ingestion/runs/latest', {
        params: { entity, warehouse_code: card.targetWarehouse },
      })
      lastRun.value = data
    } catch {
      lastRun.value = null
    } finally {
      lastRunLoaded.value = true
    }
  }
}, { immediate: true })

function onWarehouseChange() {
  setStoredWarehouse(warehouse.value)
  router.replace({ query: { ...route.query, warehouse: warehouse.value } })
}

onMounted(() => {
  const q = route.query.warehouse
  if (q === 'AAH' || q === 'BLP') {
    warehouse.value = q
    setStoredWarehouse(q)
  } else {
    router.replace({ query: { ...route.query, warehouse: warehouse.value } })
  }
  adminStore.fetchWarehouses()
  loadIngestionRuns()
})

const runColumns: DataTableColumn[] = [
  { key: 'id', label: 'Run ID', format: 'text' },
  { key: 'entity', label: 'Entity' },
  { key: 'file_name', label: 'File' },
  { key: 'status', label: 'Status' },
  { key: 'row_count', label: 'Rows', align: 'right' },
  { key: 'inserted_count', label: 'Inserted', align: 'right' },
  { key: 'rejected_count', label: 'Rejected', align: 'right' },
  { key: 'started_at', label: 'Started' },
  { key: 'actions', label: '' },
]

const salesOutFileInput = ref<HTMLInputElement | null>(null)
const salesOutFile = ref<File | null>(null)
const salesOutUploading = ref(false)
const salesOutDateFrom = ref('')
const salesOutDateTo = ref('')
const salesOutUploadResult = ref<IngestionUploadResult | null>(null)

const sohFileInput = ref<HTMLInputElement | null>(null)
const sohFile = ref<File | null>(null)
const sohSnapshotDate = ref(new Date().toISOString().slice(0, 10))
const sohUploadResult = ref<IngestionUploadResult | null>(null)
const sohRejectionDetail = ref<{ error_summary: string | null; rejections_sample: { row_number: number; reason: string }[] } | null>(null)
const sohUploading = ref(false)
const sohError = ref<string | null>(null)
const sohExecuting = ref(false)
const sohTemplateDownloading = ref(false)

const demandFileInput = ref<HTMLInputElement | null>(null)
const demandFile = ref<File | null>(null)
const demandUploading = ref(false)
const demandUploadResult = ref<IngestionUploadResult | null>(null)

const productMasterFileInput = ref<HTMLInputElement | null>(null)
const productMasterFile = ref<File | null>(null)
const productMasterUploading = ref(false)
const productMasterUploadResult = ref<IngestionUploadResult | null>(null)

const ingestionRuns = ref<IngestionRunRow[]>([])
const drawerRunId = ref<string | null>(null)
const drawerRun = ref<IngestionRunDetail | null>(null)
const confirmModalRun = ref<IngestionUploadResult | null>(null)

const currentUploadResult = computed(() => {
  if (selectedDataType.value === 'sales_out') return salesOutUploadResult.value
  if (selectedDataType.value === 'stock_on_hand') return sohUploadResult.value
  if (['demand_pipeline', 'sales_direct', 'samples'].includes(selectedDataType.value)) return demandUploadResult.value
  if (selectedDataType.value === 'product_master') return productMasterUploadResult.value
  return null
})

const needsExecute = computed(() => {
  const r = currentUploadResult.value
  if (!r) return false
  if (selectedDataType.value === 'sales_out' || selectedDataType.value === 'stock_on_hand') return true
  if (['demand_pipeline', 'sales_direct', 'samples', 'product_master'].includes(selectedDataType.value)) return true
  return false
})

const executeButtonLabel = computed(() => {
  if (selectedDataType.value === 'sales_out') return 'Execute build-weekly'
  if (selectedDataType.value === 'stock_on_hand') return 'Execute (daily → weekly)'
  return 'Execute transform'
})

const executing = computed(() => sohExecuting.value)

const ingestionRunsForTable = computed(() =>
  ingestionRuns.value.map((r) => ({
    ...r,
    file_name: r.file_name || '—',
    started_at: r.started_at ? formatDate(r.started_at) : '—',
    actions: '',
  }))
)

function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function formatDateShort(iso: string) {
  try {
    return new Date(iso).toLocaleDateString()
  } catch {
    return iso
  }
}

function getRunRow(row: Record<string, unknown>): { id: string; status: string } {
  return { id: String(row.id), status: String(row.status ?? '') }
}

function statusBadgeClass(status: string) {
  const s = String(status).toLowerCase()
  if (s === 'success') return 'badge-success'
  if (s === 'failed') return 'badge-danger'
  if (s === 'running') return 'badge-info'
  if (s === 'pending') return 'badge-warn'
  return 'badge-info'
}

async function loadIngestionRuns() {
  const { data } = await api.get<IngestionRunRow[]>('/ingestion/runs', { params: { limit: 50 } })
  ingestionRuns.value = data
  if (lastRun.value && selectedCard.value?.entity) {
    const entityMap: Record<string, string> = {
      sales_out: 'sales_out',
      stock_on_hand: 'stock_on_hand',
      demand_pipeline: 'demand',
      sales_direct: 'demand',
      samples: 'demand',
      product_master: 'product_master',
    }
    const entity = entityMap[selectedCard.value.dataType] || selectedCard.value.entity
    const { data: latest } = await api.get<LatestRun | null>('/ingestion/runs/latest', {
      params: { entity, warehouse_code: selectedCard.value.targetWarehouse },
    })
    lastRun.value = latest || null
  }
}

function onSalesOutFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  salesOutFile.value = target.files?.[0] ?? null
  salesOutUploadResult.value = null
}

function setSalesOutLast24Months() {
  const today = new Date()
  const from = new Date(today)
  from.setMonth(from.getMonth() - 24)
  salesOutDateFrom.value = from.toISOString().slice(0, 10)
  salesOutDateTo.value = today.toISOString().slice(0, 10)
}

async function uploadSalesOutWithMode(mode: 'weekly' | 'historical') {
  if (!salesOutFile.value) return
  salesOutUploading.value = true
  salesOutUploadResult.value = null
  const form = new FormData()
  form.append('file', salesOutFile.value)
  const params: Record<string, string> = { mode }
  if (mode === 'historical') {
    if (salesOutDateFrom.value.trim()) params.date_from = salesOutDateFrom.value.trim()
    if (salesOutDateTo.value.trim()) params.date_to = salesOutDateTo.value.trim()
  }
  try {
    const { data } = await api.post<IngestionUploadResult>('/ingestion/sales-out/upload', form, {
      params,
      onUploadProgress: (e) => {
        if (e.total) salesOutUploading.value = true
      },
    })
    salesOutUploadResult.value = { ...data, confirmed: data.requires_confirm ? false : true }
    salesOutFile.value = null
    if (salesOutFileInput.value) salesOutFileInput.value.value = ''
    await loadIngestionRuns()
  } catch (err: unknown) {
    const msg = err && typeof err === 'object' && 'response' in err
      ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      : null
    alert(msg ? `Upload failed: ${typeof msg === 'string' ? msg : JSON.stringify(msg)}` : 'Upload failed.')
  } finally {
    salesOutUploading.value = false
  }
}

function onSohFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  sohFile.value = target.files?.[0] ?? null
  sohUploadResult.value = null
  sohError.value = null
}

async function downloadSohTemplate() {
  sohTemplateDownloading.value = true
  sohError.value = null
  try {
    const { data, headers } = await api.get<Blob>('/templates/stock-on-hand', { responseType: 'blob' })
    const disposition = headers['content-disposition']
    const match = disposition?.match(/filename="?([^";]+)"?/)
    const filename = match?.[1] ?? 'template_stock_on_hand.csv'
    const url = URL.createObjectURL(data)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  } catch (err: unknown) {
    sohError.value = 'Template download failed.'
  } finally {
    sohTemplateDownloading.value = false
  }
}

async function uploadSohWithMode(mode: 'weekly' | 'historical') {
  if (!sohFile.value) return
  sohError.value = null
  sohRejectionDetail.value = null
  sohUploading.value = true
  const form = new FormData()
  form.append('file', sohFile.value)
  const params: Record<string, string> = { mode }
  if (sohWarehouseCode.value.trim()) params.warehouse_code = sohWarehouseCode.value.trim()
  else if (warehouse.value) params.warehouse_code = warehouse.value
  if (sohSnapshotDate.value) params.snapshot_date = sohSnapshotDate.value
  try {
    const { data } = await api.post<IngestionUploadResult>('/ingestion/stock-on-hand/upload', form, {
      params,
      onUploadProgress: (e) => {
        if (e.total) sohUploading.value = true
      },
    })
    sohUploadResult.value = { ...data, confirmed: data.requires_confirm ? false : true }
    sohFile.value = null
    if (sohFileInput.value) sohFileInput.value.value = ''
    await loadIngestionRuns()
    if (data.rejected_count > 0) {
      const { data: runDetail } = await api.get<IngestionRunDetail>(`/ingestion/runs/${data.run_id}`, { params: { rejections_limit: 20 } })
      sohRejectionDetail.value = {
        error_summary: runDetail.error_summary,
        rejections_sample: runDetail.rejections_sample.map((r) => ({ row_number: r.row_number, reason: r.reason })),
      }
    }
  } catch (err: unknown) {
    const res = err && typeof err === 'object' && 'response' in err ? (err as { response?: { data?: { detail?: unknown } } }).response : null
    sohError.value = res?.data?.detail != null ? (typeof res.data.detail === 'string' ? res.data.detail : JSON.stringify(res.data.detail)) : 'Upload failed.'
  } finally {
    sohUploading.value = false
  }
}

function onDemandFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  demandFile.value = target.files?.[0] ?? null
  demandUploadResult.value = null
}

async function uploadDemandWithMode(mode: 'weekly' | 'historical') {
  if (!demandFile.value) return
  demandUploading.value = true
  demandUploadResult.value = null
  const form = new FormData()
  form.append('file', demandFile.value)
  try {
    const { data } = await api.post<IngestionUploadResult>('/ingestion/upload', form, {
      params: { entity: 'demand', mode },
    })
    demandUploadResult.value = { ...data, confirmed: data.requires_confirm ? false : true }
    demandFile.value = null
    if (demandFileInput.value) demandFileInput.value.value = ''
    await loadIngestionRuns()
  } catch (err: unknown) {
    const msg = err && typeof err === 'object' && 'response' in err
      ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      : null
    alert(msg ? `Upload failed: ${typeof msg === 'string' ? msg : JSON.stringify(msg)}` : 'Upload failed.')
  } finally {
    demandUploading.value = false
  }
}

function onProductMasterFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  productMasterFile.value = target.files?.[0] ?? null
  productMasterUploadResult.value = null
}

async function uploadProductMaster() {
  if (!productMasterFile.value) return
  productMasterUploading.value = true
  productMasterUploadResult.value = null
  const form = new FormData()
  form.append('file', productMasterFile.value)
  try {
    const { data } = await api.post<IngestionUploadResult>('/ingestion/upload', form, {
      params: { entity: 'product_master', mode: 'weekly' },
    })
    productMasterUploadResult.value = { ...data, confirmed: true }
    productMasterFile.value = null
    if (productMasterFileInput.value) productMasterFileInput.value.value = ''
    await loadIngestionRuns()
  } catch (err: unknown) {
    const msg = err && typeof err === 'object' && 'response' in err
      ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      : null
    alert(msg ? `Upload failed: ${typeof msg === 'string' ? msg : JSON.stringify(msg)}` : 'Upload failed.')
  } finally {
    productMasterUploading.value = false
  }
}

function showConfirmModal(result: IngestionUploadResult) {
  confirmModalRun.value = result
}

function closeConfirmModal() {
  confirmModalRun.value = null
}

async function confirmBackfill() {
  if (!confirmModalRun.value) return
  try {
    await api.post(`/ingestion/runs/${confirmModalRun.value.run_id}/confirm`, null, {
      params: { confirmed_by: 'user' },
    })
    if (salesOutUploadResult.value?.run_id === confirmModalRun.value.run_id) {
      salesOutUploadResult.value = { ...salesOutUploadResult.value, confirmed: true }
    }
    if (sohUploadResult.value?.run_id === confirmModalRun.value.run_id) {
      sohUploadResult.value = { ...sohUploadResult.value, confirmed: true }
    }
    if (demandUploadResult.value?.run_id === confirmModalRun.value.run_id) {
      demandUploadResult.value = { ...demandUploadResult.value, confirmed: true }
    }
    closeConfirmModal()
  } catch (err: unknown) {
    const msg = err && typeof err === 'object' && 'response' in err
      ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      : null
    alert(msg ? `Confirm failed: ${typeof msg === 'string' ? msg : JSON.stringify(msg)}` : 'Confirm failed.')
  }
}

async function executeCurrentRun() {
  const r = currentUploadResult.value
  if (!r || (r.requires_confirm && !r.confirmed)) return
  if (selectedDataType.value === 'sales_out') {
    try {
      await api.post(`/ingestion/sales-out/${r.run_id}/build-weekly`)
      await loadIngestionRuns()
      bannerStore.add({ type: 'success', title: 'Sales Out build-weekly completed', message: 'demand_actuals written.' })
    } catch (err: unknown) {
      const msg = err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : null
      alert(msg ? `Build failed: ${typeof msg === 'string' ? msg : JSON.stringify(msg)}` : 'Build failed.')
    }
    salesOutUploadResult.value = null
  } else if (selectedDataType.value === 'stock_on_hand') {
    sohExecuting.value = true
    try {
      await api.post(`/ingestion/stock-on-hand/${r.run_id}/execute`)
      await loadIngestionRuns()
      bannerStore.add({ type: 'success', title: 'SOH import executed', message: 'inventory_snapshots_weekly updated.' })
    } catch (err: unknown) {
      const res = err && typeof err === 'object' && 'response' in err ? (err as { response?: { data?: { detail?: unknown } } }).response : null
      sohError.value = res?.data?.detail != null ? (typeof res.data.detail === 'string' ? res.data.detail : JSON.stringify(res.data.detail)) : 'Execute failed.'
    } finally {
      sohExecuting.value = false
    }
    sohUploadResult.value = null
    sohRejectionDetail.value = null
  } else if (['demand_pipeline', 'sales_direct', 'samples', 'product_master'].includes(selectedDataType.value)) {
    try {
      await api.post(`/ingestion/runs/${r.run_id}/execute`)
      await loadIngestionRuns()
      bannerStore.add({ type: 'success', title: 'Import executed', message: 'Transform completed.' })
    } catch (err: unknown) {
      const msg = err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : null
      alert(msg ? `Execute failed: ${typeof msg === 'string' ? msg : JSON.stringify(msg)}` : 'Execute failed.')
    }
    demandUploadResult.value = null
    productMasterUploadResult.value = null
  }
}

function executePendingRun(row: Record<string, unknown>) {
  const id = String(row.id)
  const entity = String(row.entity ?? '')
  if (entity === 'stock_on_hand') {
    sohExecuting.value = true
    api.post(`/ingestion/stock-on-hand/${id}/execute`).then(() => {
      loadIngestionRuns()
      bannerStore.add({ type: 'success', title: 'SOH executed', message: '' })
    }).catch(() => {
      sohError.value = 'Execute failed.'
    }).finally(() => {
      sohExecuting.value = false
    })
  } else if (entity === 'sales_out') {
    api.post(`/ingestion/sales-out/${id}/build-weekly`).then(() => {
      loadIngestionRuns()
      bannerStore.add({ type: 'success', title: 'Sales Out build-weekly completed', message: '' })
    }).catch((err) => {
      const msg = err?.response?.data?.detail
      alert(msg ? `Build failed: ${typeof msg === 'string' ? msg : JSON.stringify(msg)}` : 'Build failed.')
    })
  } else {
    api.post(`/ingestion/runs/${id}/execute`).then(() => {
      loadIngestionRuns()
      bannerStore.add({ type: 'success', title: 'Import executed', message: '' })
    }).catch((err) => {
      const msg = err?.response?.data?.detail
      alert(msg ? `Execute failed: ${typeof msg === 'string' ? msg : JSON.stringify(msg)}` : 'Execute failed.')
    })
  }
}

async function openRunDrawer(row: { id: string }) {
  drawerRunId.value = row.id
  const { data } = await api.get<IngestionRunDetail>(`/ingestion/runs/${row.id}`)
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
</script>

<style scoped>
.section-title {
  font-size: 1rem;
  font-weight: 500;
  color: rgb(30 41 59);
}
</style>
