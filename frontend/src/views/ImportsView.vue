<template>
  <div class="page-shell space-y-6">
    <header class="page-header import-page-header">
      <div>
        <h1>Imports</h1>
        <p class="muted mt-1">Upload sales, stock, demand and master data into the forecasting platform.</p>
      </div>
      <span class="import-target-badge">{{ currentTargetBadge }}</span>
    </header>

    <!-- Platform-wide import / execute progress (upload bytes + server transform; polls run progress_meta) -->
    <div
      v-if="importUploadUi"
      class="import-upload-progress card card-body py-3 mb-2"
      role="status"
      aria-live="polite"
    >
      <div class="flex flex-wrap items-center gap-2 text-sm text-slate-700">
        <span class="import-upload-progress__spinner" aria-hidden="true" />
        <span>{{ importUploadUi.message }}</span>
        <span
          v-if="importUploadUi.phaseLabel"
          class="text-xs font-mono text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded"
          >{{ importUploadUi.phaseLabel }}</span
        >
        <span v-if="importUploadUi.percent != null" class="tabular-nums text-slate-500">{{ importUploadUi.percent }}%</span>
      </div>
      <div class="import-upload-progress__track mt-2">
        <div
          class="import-upload-progress__fill"
          :class="{
            'import-upload-progress__fill--indeterminate':
              importUploadUi.percent == null,
          }"
          :style="importUploadUi.percent != null ? { width: `${importUploadUi.percent}%` } : undefined"
        />
      </div>
      <p v-if="importUploadUi.detail" class="text-xs text-slate-600 mt-1.5">{{ importUploadUi.detail }}</p>
      <p class="text-xs text-slate-500 mt-1">{{ importUploadUi.hint }}</p>
    </div>

    <section class="card card-body import-location-banner">
      <div class="import-location-banner__copy">
        <p class="import-step-label">Data location</p>
        <h2 class="import-location-banner__title">
          Current data location: {{ warehouse || 'No location selected' }}
        </h2>
        <p class="import-location-banner__body">
          Sales Out, Stock on Hand and Demand imports will be loaded into the selected location.
          Product Master is platform-wide and does not change by location.
        </p>
        <p v-if="!hasLocation" class="import-location-banner__warning">
          Create an active location in Admin before importing Sales, SOH or Demand files.
        </p>
      </div>
      <div class="import-location-banner__selector">
        <label class="form-label">Data location</label>
        <select
          v-model="warehouse"
          class="select import-warehouse-card__select"
          :disabled="!locationOptions.length"
          @change="onWarehouseChange"
        >
          <option value="" disabled>{{ locationOptions.length ? 'Select location' : 'No locations created' }}</option>
          <option v-for="opt in locationOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <p class="text-xs text-amber-800 mt-1">
          Changing this location changes where Sales, SOH and Demand files are imported.
        </p>
      </div>
    </section>

    <section class="import-action-grid" aria-label="Choose import type">
      <article
        v-for="item in plannerImportCards"
        :key="item.key"
        class="import-action-card card card-body"
        :class="{ 'import-action-card--selected': selectedDataType === item.card.dataType }"
        role="button"
        tabindex="0"
        @click="selectImportCard(item.card)"
        @keydown.enter.prevent="selectImportCard(item.card)"
      >
        <div class="flex items-start justify-between gap-3">
          <div>
            <h2 class="import-action-card__title">{{ item.title }}</h2>
            <p class="import-action-card__description">{{ item.description }}</p>
          </div>
          <span class="import-action-card__target">{{ item.targetLabel }}</span>
        </div>
        <p class="import-action-card__columns">Required: {{ item.card.requiredColumns.slice(0, 4).join(', ') || 'None' }}{{ item.card.requiredColumns.length > 4 ? '…' : '' }}</p>
        <button
          v-if="item.card.dataType === 'stock_on_hand'"
          type="button"
          class="btn-secondary mt-3"
          :disabled="sohTemplateDownloading"
          @click.stop="downloadSohTemplate"
        >
          {{ sohTemplateDownloading ? 'Downloading…' : 'Download template' }}
        </button>
        <a
          v-else-if="item.card.templateHref"
          class="btn-secondary mt-3 inline-flex"
          :href="item.card.templateHref"
          download
          @click.stop
        >
          Download template
        </a>
        <router-link
          v-if="item.key === 'product-master' && catalogSetupCard?.linkHref"
          :to="catalogSetupCard.linkHref"
          class="btn-secondary mt-3 ml-2 inline-flex"
          @click.stop
        >
          Open location product codes
        </router-link>
      </article>
    </section>

    <section v-if="selectedCard && !selectedCard.linkHref" class="card card-body import-focus-panel">
      <div class="import-focus-panel__header">
        <div>
          <p class="import-step-label">Selected import</p>
          <h2 class="section-title">{{ selectedCard.title }}</h2>
          <p class="text-sm text-slate-600 m-0">{{ selectedImportDescription }}</p>
        </div>
        <span class="import-target-badge import-target-badge--small">{{ importTargetDisplay }}</span>
      </div>

      <dl class="import-summary-list">
        <div>
          <dt>Target</dt>
          <dd>{{ importTargetDisplay }}</dd>
        </div>
        <div>
          <dt>Required columns</dt>
          <dd>{{ selectedCard.requiredColumns.join(', ') || '—' }}</dd>
        </div>
        <div>
          <dt>Selected file</dt>
          <dd>{{ selectedFileName || 'No file selected' }}</dd>
        </div>
      </dl>

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

      <OperationStatusPanel :operation="importOperation.operation" class="mt-3" />
      <OperationStatusPanel :operation="executeOperation.operation" class="mt-3" />

      <input v-if="selectedCard.dataType === 'sales_out'" type="file" ref="salesOutFileInput" accept=".csv,.xlsx,.xls" class="hidden" @change="onSalesOutFileSelect" />
      <input v-if="selectedCard.dataType === 'stock_on_hand'" type="file" ref="sohFileInput" accept=".csv,.xlsx,.xls" class="hidden" @change="onSohFileSelect" />
      <input v-if="selectedCard.dataType === 'demand_pipeline' || selectedCard.dataType === 'sales_direct' || selectedCard.dataType === 'samples'" type="file" ref="demandFileInput" accept=".csv" class="hidden" @change="onDemandFileSelect" />
      <input v-if="selectedCard.dataType === 'product_master'" type="file" ref="productMasterFileInput" accept=".csv" class="hidden" @change="onProductMasterFileSelect" />

      <div class="flex flex-wrap items-center gap-2 mt-4">
        <button type="button" class="btn-primary" :disabled="selectedUploadBusy || (!isCatalogImportSelected && !hasLocation)" @click="chooseSelectedFile">
          {{ selectedUploadBusy ? 'Working…' : 'Choose file' }}
        </button>
        <a v-if="selectedCard.templateHref && selectedCard.dataType !== 'stock_on_hand'" :href="selectedCard.templateHref" download class="btn-secondary">Download template</a>
        <button v-if="selectedCard.dataType === 'stock_on_hand'" type="button" class="btn-secondary" :disabled="sohTemplateDownloading" @click="downloadSohTemplate">
          {{ sohTemplateDownloading ? 'Downloading…' : 'Download template' }}
        </button>
        <OperationStatusPanel v-if="selectedCard.dataType === 'stock_on_hand'" :operation="templateDownloadOperation.operation" class="basis-full mt-2" />
      </div>

      <details v-if="selectedCard?.entity" class="import-advanced mt-4">
        <summary>Advanced options</summary>
        <label class="mt-3 flex max-w-3xl items-start gap-2 rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2 text-sm text-amber-950">
          <input v-model="forceReimport" type="checkbox" class="mt-0.5 rounded border-amber-300" />
          <span>
            <strong>Re-import same file if it was imported before.</strong>
            Use this after clearing data when you need the exact same file to stage again.
          </span>
        </label>
      </details>

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
        <p class="text-xs text-slate-500 m-0 max-w-2xl leading-snug">
          <strong>Upload historical</strong> only keeps rows whose <code class="text-xs bg-slate-100 px-1 rounded">Business_Processed_Date</code> falls between date from and date to (inclusive). Rows before that window are rejected as
          <code class="text-xs bg-slate-100 px-1 rounded">date_out_of_range</code>. For a full file without filtering, use <strong>Upload (weekly)</strong> or clear the date fields and use historical with no range.
        </p>
        <div class="flex gap-2">
          <button type="button" class="btn-primary" :disabled="salesOutUploading" @click="uploadSalesOutWithMode('weekly')">Upload (weekly)</button>
          <button type="button" class="btn-secondary border-amber-300" :disabled="salesOutUploading" @click="uploadSalesOutWithMode('historical')">Upload historical</button>
        </div>
      </div>

      <!-- SOH: file + location + snapshot date + execute -->
      <div v-if="selectedCard?.dataType === 'stock_on_hand' && sohFile" class="mt-4 space-y-3">
        <p class="text-xs text-slate-500">Selected: {{ sohFile.name }}</p>
        <div class="flex flex-wrap gap-3">
          <div>
            <label class="form-label text-xs">Location</label>
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
        <span v-if="!currentUploadResult.duplicate_noop">
          Staged {{ currentUploadResult.staged_count }}, rejected {{ currentUploadResult.rejected_count }}
        </span>
        <p
          v-if="currentUploadResult.duplicate_noop"
          class="w-full basis-full text-sm text-amber-900 bg-amber-50 border border-amber-200 rounded px-2 py-1.5"
        >
          {{
            currentUploadResult.message ||
              'This exact file was already imported successfully. Nothing new was staged. Tick the re-import option above if the data was cleared and you need to load it again.'
          }}
        </p>
        <span v-if="currentUploadResult.mode" class="badge" :class="currentUploadResult.mode === 'historical' ? 'badge-warn' : 'badge-info'">{{ currentUploadResult.mode }}</span>
        <button v-if="currentUploadResult.requires_confirm" type="button" class="btn-secondary text-sm border-amber-300" @click="showConfirmModal(currentUploadResult)">Confirm backfill</button>
        <button
          v-if="needsExecute"
          type="button"
          class="btn-primary text-sm"
          :disabled="(currentUploadResult.requires_confirm && !currentUploadResult.confirmed) || executeTransformBusy"
          @click="executeCurrentRun"
        >
          {{ executeTransformBusy ? 'Executing…' : executeButtonLabel }}
        </button>
      </div>
      <div
        v-if="sohUploadResult && (sohUploadResult.rejected_count ?? 0) > 0 && sohRejectionDetail"
        class="mt-3 rounded-lg text-sm border"
        :class="sohUploadResult.staged_count === 0 ? 'border-amber-300 bg-amber-50 text-amber-900' : 'border-slate-200 bg-slate-50'"
      >
        <div class="px-3 py-2 flex items-center justify-between gap-2">
          <p class="font-semibold">
            {{ sohUploadResult.staged_count === 0
              ? `All ${sohUploadResult.rejected_count ?? 0} rows rejected.`
              : `${sohUploadResult.rejected_count ?? 0} rows rejected.` }}
          </p>
          <span v-if="sohRejectionDetail.rejections_sample.length < (sohUploadResult.rejected_count ?? 0)" class="text-xs opacity-70">
            Showing first {{ sohRejectionDetail.rejections_sample.length }} of {{ sohUploadResult.rejected_count ?? 0 }}
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

    <section class="card import-history-card">
      <div class="card-header flex items-center justify-between">
        <h3 class="section-title mb-0">Recent import history</h3>
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
            <button
              v-if="getRunRow(row).status === 'pending' && row.needsConfirmBeforeExecute"
              type="button"
              class="btn-secondary text-xs py-1 px-2 ml-1 border-amber-400 text-amber-900 hover:bg-amber-50"
              @click="confirmPendingRunFromTable(String(row.id))"
            >
              Confirm
            </button>
            <button
              v-if="getRunRow(row).status === 'pending'"
              type="button"
              class="btn-primary text-xs py-1 px-2 ml-1"
              :disabled="Boolean(row.needsConfirmBeforeExecute) || executeTransformBusy"
              :title="row.needsConfirmBeforeExecute ? 'Confirm this run first (amber button)' : undefined"
              @click="executePendingRun(row)"
            >
              Execute
            </button>
          </template>
          <template #empty>
            <p class="text-slate-500">No imports have been run yet. Choose an import type above and upload a file.</p>
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
          <p v-if="(drawerRun.rejected_count ?? 0) > 0" class="text-sm">
            <router-link
              :to="{ name: 'ImportRejections', query: { run: drawerRunId ?? undefined } }"
              class="font-medium text-indigo-600 hover:text-indigo-800"
            >
              Work through rejections
            </router-link>
            <span class="text-slate-500"> — missing SKUs, reasons, full CSV</span>
          </p>
          <p
            v-if="drawerProgressLine"
            class="text-slate-700 border border-slate-200 rounded-md px-2 py-1.5 bg-slate-50"
          >
            <strong class="block text-xs text-slate-500 mb-0.5">Last progress</strong>
            {{ drawerProgressLine.message }}
            <span v-if="drawerProgressLine.detail" class="block text-xs mt-1 opacity-90">
              {{ drawerProgressLine.detail }}
            </span>
          </p>
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
          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              class="btn-secondary"
              :disabled="!drawerRun.rejections_sample?.length"
              @click="downloadRejectionsCsv"
            >
              Download sample CSV
            </button>
            <button
              v-if="(drawerRun.rejected_count ?? 0) > 0"
              type="button"
              class="btn-secondary"
              :disabled="fullRejectionsBusy"
              @click="downloadFullRejectionsCsv"
            >
              Download all rejections (CSV)
            </button>
            <OperationStatusPanel :operation="rejectionsDownloadOperation.operation" class="basis-full mt-2" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api, { INGESTION_UPLOAD_TIMEOUT_MS } from '@/api/client'
import {
  IMPORT_PROGRESS_HINT_EXECUTE,
  IMPORT_PROGRESS_HINT_UPLOAD,
  importProgressMetaToDisplay,
  startImportProgressPoll,
} from '@/config/importProgressSpec'
import { useAdminStore } from '@/stores/admin'
import { useBannerStore } from '@/stores/banner'
import DataTable from '@/components/console/DataTable.vue'
import type { DataTableColumn } from '@/components/console/DataTable.vue'
import OperationStatusPanel from '@/components/common/OperationStatusPanel.vue'
import { useOperation } from '@/composables/useOperation'
import {
  getImportCardsForLocation,
  getStoredWarehouse,
  setStoredWarehouse,
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
  requires_confirm?: boolean
  confirmed_at?: string | null
}
interface IngestionRunDetail extends IngestionRunRow {
  rejections_sample: { row_number: number; reason: string; raw_payload: unknown }[]
  error_summary: string | null
  progress_meta?: Record<string, unknown> | null
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
  /** Server skipped work: same file bytes already ingested successfully for this entity */
  duplicate_noop?: boolean
  message?: string | null
}
interface LatestRun {
  id: string
  entity: string
  status: string
  inserted_count: number
  rejected_count: number
  finished_at: string | null
}

/** Visible upload + post-upload server work (staging) + execute transform (polled progress_meta). */
interface ImportUploadUi {
  message: string
  percent: number | null
  hint: string
  detail?: string | null
  phaseLabel?: string | null
}

interface PlannerImportCard {
  key: string
  title: string
  description: string
  targetLabel: string
  card: ImportCardDef
}

const route = useRoute()
const router = useRouter()
const adminStore = useAdminStore()
const bannerStore = useBannerStore()
const activeWarehouses = computed(() => adminStore.warehouses.filter((w) => w.active))

const warehouse = ref(getStoredWarehouse())
const selectedDataType = ref<string>('')
const lastRun = ref<LatestRun | null>(null)
const lastRunLoaded = ref(false)
const forceReimport = ref(false)

// Declared here (before its watch) to avoid temporal dead zone
const sohWarehouseCode = ref('')

const visibleCards = computed(() => getImportCardsForLocation(warehouse.value))
const selectedCard = computed(() => visibleCards.value.find((c) => c.dataType === selectedDataType.value) || visibleCards.value[0])
const locationOptions = computed(() =>
  activeWarehouses.value
    .map((w) => ({ value: String(w.code || '').trim().toUpperCase(), label: w.name ? `${w.code} - ${w.name}` : w.code }))
    .filter((w) => w.value),
)
const hasLocation = computed(() => Boolean(warehouse.value))

function findImportCard(...dataTypes: string[]): ImportCardDef | undefined {
  return visibleCards.value.find((c) => dataTypes.includes(c.dataType))
}

const plannerImportCards = computed<PlannerImportCard[]>(() => {
  const productMaster = findImportCard('product_master')
  const sales = findImportCard('sales_out', 'sales_direct')
  const soh = findImportCard('stock_on_hand')
  const demand = findImportCard('demand_pipeline', 'samples')
  return [
    productMaster && {
      key: 'product-master',
      title: 'Product Master',
      description: 'Load the shared product list and descriptions used across forecasts.',
      targetLabel: 'Platform-wide',
      card: productMaster,
    },
    sales && {
      key: 'sales-out',
      title: 'Sales Out',
      description: 'Upload recent sales activity so the forecast has demand history to learn from.',
      targetLabel: `Location ${warehouse.value}`,
      card: sales,
    },
    soh && {
      key: 'stock-on-hand',
      title: 'Stock on Hand (SOH)',
      description: 'Upload current stock balances before planning replenishment.',
      targetLabel: `Location ${warehouse.value}`,
      card: soh,
    },
    demand && {
      key: 'demand-pipeline',
      title: 'Demand Pipeline',
      description: 'Upload known demand, sales adjustments or sample withdrawals for planning.',
      targetLabel: `Location ${warehouse.value}`,
      card: demand,
    },
  ].filter(Boolean) as PlannerImportCard[]
})

const catalogSetupCard = computed(() => findImportCard('warehouse_product_codes'))

const isCatalogImportSelected = computed(
  () =>
    selectedDataType.value === 'product_master' ||
    selectedDataType.value === 'warehouse_product_codes',
)

/** Shown next to Format in the detail panel — bold emphasis in template. */
const importTargetDisplay = computed(() =>
  isCatalogImportSelected.value ? 'Platform-wide' : `Location ${warehouse.value}`,
)

const currentTargetBadge = computed(() =>
  isCatalogImportSelected.value ? 'Platform-wide' : `Location ${warehouse.value}`,
)

const selectedImportDescription = computed(() => {
  if (selectedDataType.value === 'product_master') {
    return 'Use this to update the shared product catalogue for the whole platform.'
  }
  if (selectedDataType.value === 'sales_out' || selectedDataType.value === 'sales_direct') {
    return hasLocation.value ? `Use this to load sales history for ${warehouse.value}.` : 'Create a location before loading sales history.'
  }
  if (selectedDataType.value === 'stock_on_hand') {
    return hasLocation.value ? `Use this to load stock balances for ${warehouse.value}.` : 'Create a location before loading stock balances.'
  }
  return hasLocation.value ? `Use this to load demand pipeline data for ${warehouse.value}.` : 'Create a location before loading demand data.'
})

const selectedFileName = computed(() => {
  if (selectedDataType.value === 'sales_out') return salesOutFile.value?.name
  if (selectedDataType.value === 'stock_on_hand') return sohFile.value?.name
  if (['demand_pipeline', 'sales_direct', 'samples'].includes(selectedDataType.value)) return demandFile.value?.name
  if (selectedDataType.value === 'product_master') return productMasterFile.value?.name
  return ''
})

function selectImportCard(c: ImportCardDef) {
  selectedDataType.value = c.dataType
  forceReimport.value = false
}

const isBlpSohHistoricalDisabled = computed(
  () => false
)

watch(visibleCards, (cards) => {
  if (!cards.length) return
  const stillValid = cards.some((c) => c.dataType === selectedDataType.value)
  if (!stillValid) {
    const ops = cards.filter(
      (c) => c.dataType !== 'product_master' && c.dataType !== 'warehouse_product_codes',
    )
    const preferred =
      ops.find((c) => c.dataType === 'sales_out') ||
      ops.find((c) => c.dataType === 'sales_direct') ||
      ops[0] ||
      cards[0]
    selectedDataType.value = preferred.dataType
  }
}, { immediate: true })

watch(warehouse, (wh) => {
  sohWarehouseCode.value = wh
}, { immediate: true })

watch(locationOptions, (options) => {
  const routeWarehouse = typeof route.query.warehouse === 'string' ? route.query.warehouse.trim().toUpperCase() : ''
  const storedWarehouse = getStoredWarehouse()
  const preferred = [routeWarehouse, warehouse.value, storedWarehouse].find((code) =>
    options.some((option) => option.value === code),
  )

  if (preferred && preferred !== warehouse.value) {
    warehouse.value = preferred
    setStoredWarehouse(preferred)
    router.replace({ query: { ...route.query, warehouse: preferred } })
    return
  }

  if (!preferred && options.length) {
    const first = options[0].value
    warehouse.value = first
    setStoredWarehouse(first)
    router.replace({ query: { ...route.query, warehouse: first } })
    return
  }

  if (!options.length && warehouse.value) {
    warehouse.value = ''
    setStoredWarehouse('')
    const query = { ...route.query }
    delete query.warehouse
    router.replace({ query })
  }
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
      const params = card.targetWarehouse ? { entity, warehouse_code: card.targetWarehouse } : { entity }
      const { data } = await api.get<LatestRun | null>('/ingestion/runs/latest', { params })
      lastRun.value = data
    } catch {
      lastRun.value = null
    } finally {
      lastRunLoaded.value = true
    }
  }
}, { immediate: true })

function onWarehouseChange() {
  const selected = warehouse.value.trim().toUpperCase()
  warehouse.value = selected
  setStoredWarehouse(selected)
  if (selected) router.replace({ query: { ...route.query, warehouse: selected } })
}

onMounted(async () => {
  await adminStore.fetchWarehouses()
  loadIngestionRuns()
})

const runColumns: DataTableColumn[] = [
  { key: 'id', label: 'Run', format: 'text' },
  { key: 'entity', label: 'Import type' },
  { key: 'file_name', label: 'File' },
  { key: 'status', label: 'Status' },
  { key: 'row_count', label: 'Rows', align: 'right' },
  { key: 'inserted_count', label: 'Imported', align: 'right' },
  { key: 'rejected_count', label: 'Rejected', align: 'right' },
  { key: 'started_at', label: 'Started' },
  { key: 'actions', label: '' },
]

const importUploadUi = ref<ImportUploadUi | null>(null)
const importUploadError = ref<string | null>(null)
const importOperation = useOperation('Import data')
const executeOperation = useOperation('Import transform')
const templateDownloadOperation = useOperation('Download SOH template')
const rejectionsDownloadOperation = useOperation('Download rejections CSV')
const executeTransformBusy = executeOperation.isRunning

const salesOutFileInput = ref<HTMLInputElement | null>(null)
const salesOutFile = ref<File | null>(null)
const salesOutUploading = importOperation.isRunning
const salesOutDateFrom = ref('')
const salesOutDateTo = ref('')
const salesOutUploadResult = ref<IngestionUploadResult | null>(null)

const sohFileInput = ref<HTMLInputElement | null>(null)
const sohFile = ref<File | null>(null)
const sohSnapshotDate = ref(new Date().toISOString().slice(0, 10))
const sohUploadResult = ref<IngestionUploadResult | null>(null)
const sohRejectionDetail = ref<{ error_summary: string | null; rejections_sample: { row_number: number; reason: string }[] } | null>(null)
const sohUploading = importOperation.isRunning
const sohError = ref<string | null>(null)
const sohExecuting = ref(false)
const sohTemplateDownloading = templateDownloadOperation.isRunning

const demandFileInput = ref<HTMLInputElement | null>(null)
const demandFile = ref<File | null>(null)
const demandUploading = importOperation.isRunning
const demandUploadResult = ref<IngestionUploadResult | null>(null)

const productMasterFileInput = ref<HTMLInputElement | null>(null)
const productMasterFile = ref<File | null>(null)
const productMasterUploading = importOperation.isRunning
const productMasterUploadResult = ref<IngestionUploadResult | null>(null)

const selectedUploadBusy = computed(() => importOperation.isRunning.value)

function chooseSelectedFile() {
  if (selectedDataType.value === 'sales_out') {
    salesOutFileInput.value?.click()
    return
  }
  if (selectedDataType.value === 'stock_on_hand') {
    sohFileInput.value?.click()
    return
  }
  if (['demand_pipeline', 'sales_direct', 'samples'].includes(selectedDataType.value)) {
    demandFileInput.value?.click()
    return
  }
  if (selectedDataType.value === 'product_master') {
    productMasterFileInput.value?.click()
  }
}

const ingestionRuns = ref<IngestionRunRow[]>([])
const drawerRunId = ref<string | null>(null)
const drawerRun = ref<IngestionRunDetail | null>(null)
const fullRejectionsBusy = rejectionsDownloadOperation.isRunning

const drawerProgressLine = computed(() => {
  const m = drawerRun.value?.progress_meta
  if (!m || typeof m !== 'object' || !Object.keys(m).length) return null
  return importProgressMetaToDisplay(m)
})
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
  if (r.duplicate_noop) return false
  if (selectedDataType.value === 'sales_out' || selectedDataType.value === 'stock_on_hand') return true
  if (['demand_pipeline', 'sales_direct', 'samples', 'product_master'].includes(selectedDataType.value)) return true
  return false
})

const executeButtonLabel = computed(() => {
  if (selectedDataType.value === 'sales_out') return 'Execute build-weekly'
  if (selectedDataType.value === 'stock_on_hand') return 'Execute (daily → weekly)'
  return 'Execute transform'
})

function ingestionRunNeedsConfirmation(row: Record<string, unknown>): boolean {
  if (String(row.status ?? '') !== 'pending') return false
  const req = row.requires_confirm === true || row.requires_confirm === 1
  if (!req) return false
  const conf = row.confirmed_at
  return conf == null || conf === ''
}

const ingestionRunsForTable = computed(() =>
  ingestionRuns.value.map((r) => {
    const base = { ...r } as Record<string, unknown>
    return {
      ...r,
      file_name: r.file_name || '—',
      started_at: r.started_at ? formatDate(r.started_at) : '—',
      actions: '',
      needsConfirmBeforeExecute: ingestionRunNeedsConfirmation(base),
    }
  })
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

function applyPollToImportUploadUi(d: ReturnType<typeof importProgressMetaToDisplay>) {
  if (!importUploadUi.value) return
  importUploadUi.value = {
    ...importUploadUi.value,
    message: d.message,
    percent: d.percent,
    detail: d.detail ?? undefined,
    phaseLabel: d.phaseLabel ?? undefined,
    hint: IMPORT_PROGRESS_HINT_EXECUTE,
  }
}

function formatApiDetail(err: unknown): string {
  const msg =
    err && typeof err === 'object' && 'response' in err
      ? (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      : null
  if (msg == null) return 'Request failed.'
  return typeof msg === 'string' ? msg : JSON.stringify(msg)
}

/** Backend returns 409 with detail.code confirmation_required for large/historical runs. */
function humanizeIngestion409(err: unknown): string | null {
  const res =
    err && typeof err === 'object' && 'response' in err
      ? (err as { response?: { status?: number; data?: { detail?: unknown } } }).response
      : undefined
  if (res?.status !== 409) return null
  const d = res.data?.detail
  if (
    d &&
    typeof d === 'object' &&
    'code' in d &&
    (d as { code: string }).code === 'confirmation_required'
  ) {
    return (
      'Confirmation required: click «Confirm backfill» for this run on the Imports page, then run Execute again. ' +
      'Or confirm with POST /api/ingestion/runs/{run_id}/confirm?confirmed_by=you — then build/execute. ' +
      'Until then, rows stay in staging only (inserted_count stays 0).'
    )
  }
  return null
}

function beginImportUploadDisplay(fileName?: string) {
  importUploadError.value = null
  importUploadUi.value = {
    message: fileName ? `Sending «${fileName}»…` : 'Sending file…',
    percent: 0,
    detail: null,
    phaseLabel: 'upload',
    hint: IMPORT_PROGRESS_HINT_UPLOAD,
  }
}

function onImportMultipartProgress(e: { loaded: number; total?: number }) {
  if (!importUploadUi.value) return
  const total = e.total
  if (total && total > 0) {
    const uploadComplete = e.loaded >= total
    importUploadUi.value = {
      ...importUploadUi.value,
      percent: uploadComplete ? 99 : Math.min(98, Math.round((100 * e.loaded) / total)),
      message: uploadComplete
        ? 'File sent — server is staging rows (often much slower than this bar; do not refresh — can take many minutes)…'
        : 'Sending file to server…',
      phaseLabel: uploadComplete ? 'staging' : 'upload',
    }
  } else {
    importUploadUi.value = {
      ...importUploadUi.value,
      percent: null,
      message: 'Sending file to server…',
      phaseLabel: 'upload',
    }
  }
}

function endImportUploadDisplay() {
  importUploadUi.value = null
}

function getRunRow(row: Record<string, unknown>): { id: string; status: string } {
  return { id: String(row.id), status: String(row.status ?? '') }
}

async function confirmPendingRunFromTable(runId: string): Promise<void> {
  try {
    await api.post(`/ingestion/runs/${runId}/confirm`, null, {
      params: { confirmed_by: 'imports_table' },
    })
    await loadIngestionRuns()
    bannerStore.add({
      type: 'success',
      title: 'Run confirmed',
      message: 'Click Execute to write staged rows into planning tables.',
    })
  } catch (err: unknown) {
    bannerStore.add({
      type: 'error',
      title: 'Confirm failed',
      message: formatApiDetail(err),
    })
  }
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
    const params = selectedCard.value.targetWarehouse
      ? { entity, warehouse_code: selectedCard.value.targetWarehouse }
      : { entity }
    const { data: latest } = await api.get<LatestRun | null>('/ingestion/runs/latest', { params })
    lastRun.value = latest || null
  }
}

function onSalesOutFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  salesOutFile.value = target.files?.[0] ?? null
  salesOutUploadResult.value = null
  importUploadError.value = null
}

function setSalesOutLast24Months() {
  const today = new Date()
  const from = new Date(today)
  from.setMonth(from.getMonth() - 24)
  salesOutDateFrom.value = from.toISOString().slice(0, 10)
  salesOutDateTo.value = today.toISOString().slice(0, 10)
}

function withForceReimport(params: Record<string, string>): Record<string, string> {
  if (!forceReimport.value) return params
  return { ...params, force_reimport: 'true' }
}

async function uploadSalesOutWithMode(mode: 'weekly' | 'historical') {
  if (!salesOutFile.value) return
  salesOutUploadResult.value = null
  beginImportUploadDisplay(salesOutFile.value.name)
  const form = new FormData()
  form.append('file', salesOutFile.value)
  let params: Record<string, string> = { mode, warehouse_code: warehouse.value }
  if (mode === 'historical') {
    if (salesOutDateFrom.value.trim()) params.date_from = salesOutDateFrom.value.trim()
    if (salesOutDateTo.value.trim()) params.date_to = salesOutDateTo.value.trim()
  }
  params = withForceReimport(params)
  const data = await importOperation.runWithOperation(
    'Import data',
    async () => {
      try {
        const response = await api.post<IngestionUploadResult>('/ingestion/sales-out/upload', form, {
          params,
          timeout: INGESTION_UPLOAD_TIMEOUT_MS,
          onUploadProgress: (e) => onImportMultipartProgress(e),
        })
        return response.data
      } catch (err: unknown) {
        throw new Error(formatApiDetail(err))
      }
    },
    {
      timeoutMs: INGESTION_UPLOAD_TIMEOUT_MS,
      runningMessage: `Uploading ${salesOutFile.value.name}...`,
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh imports before retrying.',
      nextActions: ['Refresh imports before retrying.', 'Check the runs table before uploading again.'],
    },
  )
  endImportUploadDisplay()
  if (!data) return
  salesOutUploadResult.value = { ...data, confirmed: data.requires_confirm ? false : true }
  importOperation.completeOperation({
    message: data.duplicate_noop ? 'Same file as a completed import.' : 'Sales Out upload staged.',
    detail: data.message || `Staged ${data.staged_count}, rejected ${data.rejected_count}.`,
    technicalDetails: data,
  })
    if (data.duplicate_noop) {
      bannerStore.add({
        type: 'info',
        title: 'Same file as a completed import',
        message: data.message || 'The server did not stage again because this file was already imported successfully.',
      })
    }
    salesOutFile.value = null
    if (salesOutFileInput.value) salesOutFileInput.value.value = ''
    try {
      await loadIngestionRuns()
    } catch {
      /* upload succeeded; table refresh is best-effort */
    }
}

function onSohFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  sohFile.value = target.files?.[0] ?? null
  sohUploadResult.value = null
  sohError.value = null
  importUploadError.value = null
}

async function downloadSohTemplate() {
  sohError.value = null
  const result = await templateDownloadOperation.runWithOperation(
    'Download SOH template',
    async () => {
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
        return { filename }
      } catch (err: unknown) {
        sohError.value = 'Template download failed.'
        throw new Error(formatApiDetail(err))
      }
    },
    {
      runningMessage: 'Downloading SOH template...',
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh imports before retrying.',
      nextActions: ['Refresh imports before retrying.', 'Try the template download again after checking API status.'],
    },
  )
  if (!result) return
  templateDownloadOperation.completeOperation({
    message: `Template downloaded: ${result.filename}`,
    technicalDetails: result,
  })
}

async function uploadSohWithMode(mode: 'weekly' | 'historical') {
  if (!sohFile.value) return
  sohError.value = null
  sohRejectionDetail.value = null
  beginImportUploadDisplay(sohFile.value.name)
  const form = new FormData()
  form.append('file', sohFile.value)
  let params: Record<string, string> = { mode }
  if (sohWarehouseCode.value.trim()) params.warehouse_code = sohWarehouseCode.value.trim()
  else if (warehouse.value) params.warehouse_code = warehouse.value
  if (sohSnapshotDate.value) params.snapshot_date = sohSnapshotDate.value
  params = withForceReimport(params)
  const data = await importOperation.runWithOperation(
    'Import data',
    async () => {
      try {
        const response = await api.post<IngestionUploadResult>('/ingestion/stock-on-hand/upload', form, {
          params,
          timeout: INGESTION_UPLOAD_TIMEOUT_MS,
          onUploadProgress: (e) => onImportMultipartProgress(e),
        })
        return response.data
      } catch (err: unknown) {
        const detail = formatApiDetail(err)
        sohError.value = detail
        throw new Error(detail)
      }
    },
    {
      timeoutMs: INGESTION_UPLOAD_TIMEOUT_MS,
      runningMessage: `Uploading ${sohFile.value.name}...`,
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh imports before retrying.',
      nextActions: ['Refresh imports before retrying.', 'Check the runs table before uploading again.'],
    },
  )
  endImportUploadDisplay()
  if (!data) return
  sohUploadResult.value = { ...data, confirmed: data.requires_confirm ? false : true }
  importOperation.completeOperation({
    message: data.duplicate_noop ? 'Same file as a completed import.' : 'SOH upload staged.',
    detail: data.message || `Staged ${data.staged_count}, rejected ${data.rejected_count}.`,
    technicalDetails: data,
  })
    if (data.duplicate_noop) {
      bannerStore.add({
        type: 'info',
        title: 'Same file as a completed import',
        message: data.message || 'The server did not stage again because this file was already imported successfully.',
      })
    }
    sohFile.value = null
    if (sohFileInput.value) sohFileInput.value.value = ''
    try {
      await loadIngestionRuns()
    } catch {
      /* upload succeeded */
    }
    if (data.rejected_count > 0) {
      const { data: runDetail } = await api.get<IngestionRunDetail>(`/ingestion/runs/${data.run_id}`, { params: { rejections_limit: 20 } })
      sohRejectionDetail.value = {
        error_summary: runDetail.error_summary,
        rejections_sample: runDetail.rejections_sample.map((r) => ({ row_number: r.row_number, reason: r.reason })),
      }
    }
}

function onDemandFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  demandFile.value = target.files?.[0] ?? null
  demandUploadResult.value = null
  importUploadError.value = null
}

async function uploadDemandWithMode(mode: 'weekly' | 'historical') {
  if (!demandFile.value) return
  demandUploadResult.value = null
  beginImportUploadDisplay(demandFile.value.name)
  const form = new FormData()
  form.append('file', demandFile.value)
  const data = await importOperation.runWithOperation(
    'Import data',
    async () => {
      try {
        const response = await api.post<IngestionUploadResult>('/ingestion/upload', form, {
          params: withForceReimport({ entity: 'demand', mode, warehouse_code: warehouse.value }),
          timeout: INGESTION_UPLOAD_TIMEOUT_MS,
          onUploadProgress: (e) => onImportMultipartProgress(e),
        })
        return response.data
      } catch (err: unknown) {
        throw new Error(formatApiDetail(err))
      }
    },
    {
      timeoutMs: INGESTION_UPLOAD_TIMEOUT_MS,
      runningMessage: `Uploading ${demandFile.value.name}...`,
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh imports before retrying.',
      nextActions: ['Refresh imports before retrying.', 'Check the runs table before uploading again.'],
    },
  )
  endImportUploadDisplay()
  if (!data) return
  demandUploadResult.value = { ...data, confirmed: data.requires_confirm ? false : true }
  importOperation.completeOperation({
    message: data.duplicate_noop ? 'Same file as a completed import.' : 'Demand upload staged.',
    detail: data.message || `Staged ${data.staged_count}, rejected ${data.rejected_count}.`,
    technicalDetails: data,
  })
    if (data.duplicate_noop) {
      bannerStore.add({
        type: 'info',
        title: 'Same file as a completed import',
        message: data.message || 'The server did not stage again because this file was already imported successfully.',
      })
    }
    demandFile.value = null
    if (demandFileInput.value) demandFileInput.value.value = ''
    try {
      await loadIngestionRuns()
    } catch {
      /* upload succeeded */
    }
}

function onProductMasterFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  productMasterFile.value = target.files?.[0] ?? null
  productMasterUploadResult.value = null
  importUploadError.value = null
}

async function uploadProductMaster() {
  if (!productMasterFile.value) return
  productMasterUploadResult.value = null
  beginImportUploadDisplay(productMasterFile.value.name)
  const form = new FormData()
  form.append('file', productMasterFile.value)
  const data = await importOperation.runWithOperation(
    'Import data',
    async () => {
      try {
        const response = await api.post<IngestionUploadResult>('/ingestion/upload', form, {
          params: withForceReimport({ entity: 'product_master', mode: 'weekly' }),
          timeout: INGESTION_UPLOAD_TIMEOUT_MS,
          onUploadProgress: (e) => onImportMultipartProgress(e),
        })
        return response.data
      } catch (err: unknown) {
        throw new Error(formatApiDetail(err))
      }
    },
    {
      timeoutMs: INGESTION_UPLOAD_TIMEOUT_MS,
      runningMessage: `Uploading ${productMasterFile.value.name}...`,
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh imports before retrying.',
      nextActions: ['Refresh imports before retrying.', 'Check the runs table before uploading again.'],
    },
  )
  endImportUploadDisplay()
  if (!data) return
  productMasterUploadResult.value = { ...data, confirmed: true }
  importOperation.completeOperation({
    message: data.duplicate_noop ? 'Same file as a completed import.' : 'Product master upload staged.',
    detail: data.message || `Staged ${data.staged_count}, rejected ${data.rejected_count}.`,
    technicalDetails: data,
  })
    if (data.duplicate_noop) {
      bannerStore.add({
        type: 'info',
        title: 'Same file as a completed import',
        message: data.message || 'The server did not stage again because this file was already imported successfully.',
      })
    }
    productMasterFile.value = null
    if (productMasterFileInput.value) productMasterFileInput.value.value = ''
    try {
      await loadIngestionRuns()
    } catch {
      /* upload succeeded */
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
  importUploadError.value = null
  importUploadUi.value = {
    message: 'Starting transform on server…',
    percent: null,
    detail: null,
    phaseLabel: 'execute',
    hint: IMPORT_PROGRESS_HINT_EXECUTE,
  }
  const stopPoll = startImportProgressPoll(r.run_id, applyPollToImportUploadUi)
  const result = await executeOperation.runWithOperation(
    'Import transform',
    async () => {
      if (selectedDataType.value === 'sales_out') {
        try {
          await api.post(`/ingestion/sales-out/${r.run_id}/build-weekly`, null, {
            timeout: INGESTION_UPLOAD_TIMEOUT_MS,
          })
          await loadIngestionRuns()
          return { title: 'Sales Out build-weekly completed', message: 'demand_actuals written.' }
        } catch (err: unknown) {
          const detail = humanizeIngestion409(err) ?? formatApiDetail(err)
          importUploadError.value = detail
          throw new Error(detail)
        }
      }
      if (selectedDataType.value === 'stock_on_hand') {
        try {
          await api.post(`/ingestion/stock-on-hand/${r.run_id}/execute`, null, {
            timeout: INGESTION_UPLOAD_TIMEOUT_MS,
          })
          await loadIngestionRuns()
          return { title: 'SOH import executed', message: 'inventory_snapshots_weekly updated.' }
        } catch (err: unknown) {
          const res = err && typeof err === 'object' && 'response' in err ? (err as { response?: { data?: { detail?: unknown } } }).response : null
          const detail =
            res?.data?.detail != null
              ? typeof res.data.detail === 'string'
                ? res.data.detail
                : JSON.stringify(res.data.detail)
              : 'Execute failed.'
          sohError.value = detail
          importUploadError.value = detail
          throw new Error(detail)
        }
      }
      if (['demand_pipeline', 'sales_direct', 'samples', 'product_master'].includes(selectedDataType.value)) {
        try {
          await api.post(`/ingestion/runs/${r.run_id}/execute`, null, {
            timeout: INGESTION_UPLOAD_TIMEOUT_MS,
          })
          await loadIngestionRuns()
          return { title: 'Import executed', message: 'Transform completed.' }
        } catch (err: unknown) {
          const detail = humanizeIngestion409(err) ?? formatApiDetail(err)
          importUploadError.value = detail
          throw new Error(detail)
        }
      }
      return { title: 'Import executed', message: 'Transform completed.' }
    },
    {
      timeoutMs: INGESTION_UPLOAD_TIMEOUT_MS,
      runningMessage: 'Executing staged import on server...',
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh imports before retrying.',
      nextActions: ['Refresh imports before retrying.', 'Check the runs table before executing again.'],
    },
  )
  stopPoll()
  endImportUploadDisplay()
  if (!result) return
  executeOperation.completeOperation({ message: result.title, detail: result.message, technicalDetails: result })
  bannerStore.add({ type: 'success', title: result.title, message: result.message })
  if (selectedDataType.value === 'sales_out') {
    salesOutUploadResult.value = null
  } else if (selectedDataType.value === 'stock_on_hand') {
    sohUploadResult.value = null
    sohRejectionDetail.value = null
  } else if (['demand_pipeline', 'sales_direct', 'samples', 'product_master'].includes(selectedDataType.value)) {
    demandUploadResult.value = null
    productMasterUploadResult.value = null
  }
}

async function executePendingRun(row: Record<string, unknown>) {
  const id = String(row.id)
  const entity = String(row.entity ?? '')
  if (ingestionRunNeedsConfirmation(row)) {
    bannerStore.add({
      type: 'error',
      title: 'Confirm this run first',
      message: 'Use the amber «Confirm» button in this row, then «Execute».',
    })
    return
  }
  importUploadError.value = null
  importUploadUi.value = {
    message: 'Starting transform on server…',
    percent: null,
    detail: null,
    phaseLabel: 'execute',
    hint: IMPORT_PROGRESS_HINT_EXECUTE,
  }
  const stopPoll = startImportProgressPoll(id, applyPollToImportUploadUi)
  const result = await executeOperation.runWithOperation(
    'Import transform',
    async () => {
      if (entity === 'stock_on_hand') {
        sohExecuting.value = true
        await api.post(`/ingestion/stock-on-hand/${id}/execute`, null, { timeout: INGESTION_UPLOAD_TIMEOUT_MS })
        await loadIngestionRuns()
        return { title: 'SOH executed', message: 'Transform completed.' }
      }
      if (entity === 'sales_out') {
        try {
          await api.post(`/ingestion/sales-out/${id}/build-weekly`, null, { timeout: INGESTION_UPLOAD_TIMEOUT_MS })
          await loadIngestionRuns()
          return { title: 'Sales Out build-weekly completed', message: 'Transform completed.' }
        } catch (err: unknown) {
          throw new Error(humanizeIngestion409(err) ?? formatApiDetail(err))
        }
      }
      try {
        await api.post(`/ingestion/runs/${id}/execute`, null, { timeout: INGESTION_UPLOAD_TIMEOUT_MS })
        await loadIngestionRuns()
        return { title: 'Import executed', message: 'Transform completed.' }
      } catch (err: unknown) {
        throw new Error(humanizeIngestion409(err) ?? formatApiDetail(err))
      }
    },
    {
      timeoutMs: INGESTION_UPLOAD_TIMEOUT_MS,
      runningMessage: 'Executing staged import on server...',
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh imports before retrying.',
      nextActions: ['Refresh imports before retrying.', 'Check the runs table before executing again.'],
    },
  )
  stopPoll()
  sohExecuting.value = false
  endImportUploadDisplay()
  if (!result) return
  executeOperation.completeOperation({ message: result.title, detail: result.message, technicalDetails: result })
  bannerStore.add({ type: 'success', title: result.title, message: result.message })
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
  a.download = `rejections_sample_${drawerRunId.value?.slice(0, 8) ?? 'run'}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}

async function downloadFullRejectionsCsv() {
  const id = drawerRunId.value
  if (!id) return
  const result = await rejectionsDownloadOperation.runWithOperation(
    'Download rejections CSV',
    async () => {
      try {
        const res = await api.get(`/ingestion/runs/${id}/rejections/export`, { responseType: 'blob' })
        const cd = res.headers['content-disposition'] as string | undefined
        let filename = `rejections_${id.slice(0, 8)}.csv`
        if (cd) {
          const m = /filename="?([^";]+)"?/i.exec(cd)
          if (m?.[1]) filename = m[1]
        }
        const url = URL.createObjectURL(res.data)
        const a = document.createElement('a')
        a.href = url
        a.download = filename
        a.click()
        URL.revokeObjectURL(url)
        return { filename }
      } catch (err: unknown) {
        throw new Error(formatApiDetail(err))
      }
    },
    {
      runningMessage: 'Downloading full rejection CSV...',
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh imports before retrying.',
      nextActions: ['Refresh imports before retrying.', 'Check the run details before downloading again.'],
    },
  )
  if (!result) return
  rejectionsDownloadOperation.completeOperation({
    message: `Rejections CSV downloaded: ${result.filename}`,
    technicalDetails: result,
  })
}
</script>

<style scoped>
.section-title {
  font-size: 1rem;
  font-weight: 500;
  color: rgb(30 41 59);
}
.import-section-title {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgb(100 116 139);
}
.import-section-title--catalog {
  color: rgb(30 64 175);
}
.import-section-title--feeds {
  color: rgb(21 128 61);
}
.import-section-warehouse {
  font-size: inherit;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: rgb(15 23 42);
}
.import-context-summary {
  border: 1px solid rgb(226 232 240);
  background: linear-gradient(to bottom, rgb(248 250 252), rgb(255 255 255));
}
.import-context-summary__grid {
  display: grid;
  gap: 1rem;
}
@media (min-width: 768px) {
  .import-context-summary__grid {
    grid-template-columns: 1fr 1fr;
    gap: 1.5rem;
  }
}
.import-context-summary__block {
  padding: 0.25rem 0;
}
@media (min-width: 768px) {
  .import-context-summary__block--feeds {
    border-left: 1px solid rgb(226 232 240);
    padding-left: 1.5rem;
  }
}
.import-context-summary__heading {
  font-size: 0.6875rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgb(71 85 105);
  margin: 0 0 0.5rem;
}
.import-context-summary__target {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.5rem 0.75rem;
  margin: 0 0 0.5rem;
}
.import-context-summary__target-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: rgb(100 116 139);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.import-context-summary__warehouse {
  font-size: 1.5rem;
  font-weight: 800;
  line-height: 1.1;
  color: var(--accent, #214a7d);
  letter-spacing: 0.03em;
}
.import-context-summary__text {
  font-size: 0.8125rem;
  line-height: 1.45;
  color: rgb(51 65 85);
  margin: 0;
}
.import-scope-block--catalog {
  padding-top: 0.25rem;
  border-top: 3px solid rgb(199 210 254);
  margin-top: 0.25rem;
}
.import-scope-block--feeds {
  padding-top: 0.25rem;
  border-top: 3px solid rgb(167 243 208);
  margin-top: 0.25rem;
}
.import-warehouse-card__select {
  font-weight: 600;
}
.import-detail-target {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.25rem 0.5rem;
}
.import-detail-target__sep {
  color: rgb(148 163 184);
  user-select: none;
}
.import-detail-target__target-line {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.35rem;
}
.import-detail-target__emphasis {
  font-size: 1.0625rem;
  font-weight: 800;
  letter-spacing: 0.02em;
}
.import-detail-target__emphasis--catalog {
  color: rgb(67 56 202);
}
.import-detail-target__emphasis--warehouse {
  color: rgb(22 101 52);
}
.import-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
  gap: 0.75rem;
}
.import-type-card {
  display: block;
  width: 100%;
  text-align: left;
  padding: 1rem;
  border-radius: 0.5rem;
  border: 1px solid rgb(226 232 240);
  background: white;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.import-type-card:hover {
  border-color: rgb(147 197 253);
  box-shadow: 0 1px 3px rgb(0 0 0 / 0.06);
}
.import-type-card--active {
  border-color: rgb(37 99 235);
  box-shadow: 0 0 0 1px rgb(37 99 235);
  background: rgb(239 246 255);
}
.import-type-card__badge {
  display: inline-block;
  font-size: 0.625rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: rgb(29 78 216);
  background: rgb(219 234 254);
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
  margin-bottom: 0.5rem;
}
.import-type-card__badge--ops {
  color: rgb(21 128 61);
  background: rgb(220 252 231);
}
.import-type-card__title {
  font-size: 1rem;
  font-weight: 600;
  color: rgb(30 41 59);
  margin: 0 0 0.25rem;
}
.import-type-card__meta {
  font-size: 0.8125rem;
  color: rgb(71 85 105);
  margin: 0 0 0.35rem;
}
.import-type-card__cols {
  font-size: 0.6875rem;
  color: rgb(100 116 139);
  margin: 0 0 0.5rem;
  line-height: 1.35;
}
.import-type-card__link {
  font-size: 0.75rem;
  font-weight: 500;
  color: rgb(37 99 235);
  text-decoration: underline;
}

.import-page-header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}
.import-target-badge {
  display: inline-flex;
  align-items: center;
  border-radius: 9999px;
  border: 1px solid rgb(191 219 254);
  background: rgb(239 246 255);
  color: rgb(30 64 175);
  font-size: 0.8125rem;
  font-weight: 700;
  padding: 0.35rem 0.75rem;
  white-space: nowrap;
}
.import-target-badge--small {
  font-size: 0.75rem;
  padding: 0.3rem 0.65rem;
}
.import-location-banner {
  display: grid;
  gap: 1rem;
  border: 1px solid rgb(191 219 254);
  background: linear-gradient(135deg, rgb(239 246 255), rgb(255 255 255));
}
@media (min-width: 768px) {
  .import-location-banner {
    grid-template-columns: minmax(0, 1fr) minmax(16rem, 22rem);
    align-items: center;
  }
}
.import-location-banner__title {
  margin: 0;
  color: rgb(15 23 42);
  font-size: 1.25rem;
  font-weight: 800;
}
.import-location-banner__body {
  margin: 0.4rem 0 0;
  max-width: 48rem;
  color: rgb(51 65 85);
  font-size: 0.9375rem;
  line-height: 1.5;
}
.import-location-banner__selector {
  border-radius: 0.75rem;
  border: 1px solid rgb(226 232 240);
  background: rgb(255 255 255 / 0.82);
  padding: 0.85rem;
}
.import-action-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
  gap: 1rem;
}
.import-action-card {
  cursor: pointer;
  border: 1px solid rgb(226 232 240);
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
}
.import-action-card:hover,
.import-action-card:focus {
  border-color: rgb(147 197 253);
  box-shadow: 0 8px 20px rgb(15 23 42 / 0.08);
  outline: none;
  transform: translateY(-1px);
}
.import-action-card--selected {
  border-color: rgb(37 99 235);
  box-shadow: 0 0 0 1px rgb(37 99 235), 0 8px 20px rgb(37 99 235 / 0.12);
  background: rgb(239 246 255);
}
.import-action-card__title {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
  color: rgb(15 23 42);
}
.import-action-card__description {
  margin: 0.35rem 0 0;
  font-size: 0.875rem;
  line-height: 1.45;
  color: rgb(71 85 105);
}
.import-action-card__target {
  flex-shrink: 0;
  border-radius: 9999px;
  background: rgb(241 245 249);
  color: rgb(51 65 85);
  font-size: 0.6875rem;
  font-weight: 700;
  padding: 0.25rem 0.5rem;
}
.import-action-card__columns {
  margin: 0.85rem 0 0;
  color: rgb(100 116 139);
  font-size: 0.75rem;
  line-height: 1.35;
}
.import-focus-panel {
  border: 1px solid rgb(219 234 254);
}
.import-focus-panel__header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}
.import-step-label {
  margin: 0 0 0.25rem;
  font-size: 0.6875rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgb(100 116 139);
}
.import-summary-list {
  display: grid;
  gap: 0.75rem;
  margin: 1rem 0 0;
  padding: 0.85rem;
  border-radius: 0.75rem;
  background: rgb(248 250 252);
}
@media (min-width: 768px) {
  .import-summary-list {
    grid-template-columns: 0.8fr 1.6fr 1fr;
  }
}
.import-summary-list dt {
  font-size: 0.6875rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgb(100 116 139);
}
.import-summary-list dd {
  margin: 0.25rem 0 0;
  color: rgb(15 23 42);
  font-size: 0.875rem;
  font-weight: 600;
}
.import-advanced summary {
  cursor: pointer;
  color: rgb(71 85 105);
  font-size: 0.875rem;
  font-weight: 600;
}
.import-history-card {
  opacity: 0.96;
}

.import-upload-progress {
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
  border: 1px solid rgb(226 232 240);
  background: rgb(248 250 252);
}
.import-upload-progress__track {
  height: 6px;
  border-radius: 9999px;
  background: rgb(226 232 240);
  overflow: hidden;
  margin-top: 0.5rem;
}
.import-upload-progress__fill {
  height: 100%;
  border-radius: 9999px;
  background: rgb(37 99 235);
  transition: width 0.2s ease-out;
  min-width: 0;
}
.import-upload-progress__fill--indeterminate {
  width: 42%;
  animation: import-upload-indeterminate 1.2s ease-in-out infinite;
}
@keyframes import-upload-indeterminate {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(340%);
  }
}
.import-upload-progress__spinner {
  width: 1rem;
  height: 1rem;
  border: 2px solid rgb(226 232 240);
  border-top-color: rgb(37 99 235);
  border-radius: 50%;
  animation: import-upload-spin 0.65s linear infinite;
  flex-shrink: 0;
}
@keyframes import-upload-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
