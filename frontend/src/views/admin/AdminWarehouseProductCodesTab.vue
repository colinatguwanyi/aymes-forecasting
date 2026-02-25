<template>
  <div class="space-y-6">
    <PageHeader
      title="Warehouse Product Codes"
      :breadcrumbs="[{ label: 'Admin', path: '/admin/warehouse-product-codes' }]"
    >
      <template #actions>
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium text-white bg-neutral-700 rounded-lg hover:bg-neutral-800"
          @click="openDrawer('add')"
        >
          Add mapping
        </button>
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium text-neutral-700 bg-white border border-neutral-300 rounded-lg hover:bg-neutral-50"
          @click="showBulkUpload = true"
        >
          Bulk upload CSV
        </button>
      </template>
    </PageHeader>

    <FilterBar
      v-model="search"
      search-placeholder="Search by external code or SKU…"
      :has-active-filters="filterWarehouse !== '' || filterActiveOnly"
      @clear="filterWarehouse = ''; filterActiveOnly = true; search = ''"
    >
      <template #filters>
        <select
          v-model="filterWarehouse"
          class="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white min-w-[140px]"
        >
          <option value="">All warehouses</option>
          <option v-for="w in warehouseOptions" :key="w" :value="w">{{ w }}</option>
        </select>
        <label class="flex items-center gap-2 text-sm">
          <input v-model="filterActiveOnly" type="checkbox" class="rounded border-neutral-300" />
          Active only
        </label>
      </template>
    </FilterBar>

    <DataTable
      :columns="columns"
      :rows="paginatedRows"
      row-key="id"
      :loading="loading"
      :pagination="pagination"
      :row-actions="rowActions"
      @update:page="pagination.page = $event"
      @update:pageSize="pagination.pageSize = $event; pagination.page = 1"
    >
      <template #cell-active="{ value }">
        <span :class="value ? 'text-green-600' : 'text-slate-400'">{{ value ? 'Yes' : 'No' }}</span>
      </template>
      <template #empty>
        No mappings. Add one or bulk upload CSV.
      </template>
    </DataTable>

    <DrawerForm
      v-model="drawerOpen"
      :title="drawerMode === 'add' ? 'Add mapping' : 'Edit mapping'"
    >
      <form class="space-y-4" @submit.prevent="submitDrawer">
        <div v-if="drawerMode === 'add'">
          <label class="block text-sm font-medium text-neutral-700 mb-1">Warehouse code <span class="text-red-600">*</span></label>
          <select
            v-model="drawerForm.warehouse_code"
            required
            class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
          >
            <option value="">Select warehouse</option>
            <option v-for="w in warehouseOptions" :key="w" :value="w">{{ w }}</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium text-neutral-700 mb-1">External code <span class="text-red-600">*</span></label>
          <input
            v-model="drawerForm.external_code"
            type="text"
            required
            :readonly="drawerMode === 'edit'"
            class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
            placeholder="e.g. BLP Code"
          />
          <p v-if="drawerMode === 'edit'" class="text-xs text-slate-500 mt-1">External code cannot be changed.</p>
        </div>
        <div>
          <label class="block text-sm font-medium text-neutral-700 mb-1">SKU <span class="text-red-600">*</span></label>
          <input
            v-model="drawerForm.sku"
            type="text"
            required
            class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
            placeholder="Canonical product SKU"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-neutral-700 mb-1">External name (optional)</label>
          <input
            v-model="drawerForm.external_name"
            type="text"
            class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
            placeholder="Raw description for reference"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-neutral-700 mb-1">HS code (optional)</label>
          <input
            v-model="drawerForm.hs_code"
            type="text"
            class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
          />
        </div>
        <div class="flex items-center gap-2">
          <input v-model="drawerForm.active" type="checkbox" id="wpc-active" class="rounded border-neutral-300" />
          <label for="wpc-active" class="text-sm text-neutral-700">Active</label>
        </div>
      </form>
      <template #footer>
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium text-neutral-600 bg-white border border-neutral-300 rounded-lg hover:bg-neutral-50"
          @click="drawerOpen = false"
        >
          Cancel
        </button>
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium text-white bg-neutral-700 rounded-lg hover:bg-neutral-800"
          @click="submitDrawer"
        >
          {{ drawerMode === 'add' ? 'Add' : 'Save' }}
        </button>
      </template>
    </DrawerForm>

    <!-- Bulk upload modal -->
    <div
      v-if="showBulkUpload"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      @click.self="showBulkUpload = false"
    >
      <div class="bg-white rounded-lg shadow-xl max-w-lg w-full mx-4 p-6">
        <h3 class="text-lg font-semibold text-slate-800 mb-2">Bulk upload mappings</h3>
        <p class="text-sm text-slate-600 mb-4">
          CSV columns: external_code, sku, external_name (optional), hs_code (optional). Set warehouse below.
        </p>
        <div class="mb-4">
          <label class="block text-sm font-medium text-neutral-700 mb-1">Warehouse code <span class="text-red-600">*</span></label>
          <select
            v-model="bulkWarehouse"
            class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
          >
            <option value="">Select warehouse</option>
            <option v-for="w in warehouseOptions" :key="w" :value="w">{{ w }}</option>
          </select>
        </div>
        <input
          ref="bulkFileInput"
          type="file"
          accept=".csv"
          class="hidden"
          @change="onBulkFileSelect"
        />
        <div class="flex gap-2 mb-4">
          <button
            type="button"
            class="px-4 py-2 text-sm font-medium text-neutral-700 bg-slate-100 rounded-lg hover:bg-slate-200"
            @click="bulkFileInput?.click()"
          >
            Choose CSV file
          </button>
          <span v-if="bulkFileName" class="text-sm text-slate-600 self-center">{{ bulkFileName }}</span>
        </div>
        <p v-if="bulkError" class="text-sm text-red-600 mb-2">{{ bulkError }}</p>
        <p v-if="bulkResult" class="text-sm text-green-600 mb-2">{{ bulkResult }}</p>
        <div class="flex justify-end gap-2">
          <button
            type="button"
            class="px-4 py-2 text-sm font-medium text-neutral-600 bg-white border border-neutral-300 rounded-lg hover:bg-neutral-50"
            @click="showBulkUpload = false; bulkError = ''; bulkResult = ''"
          >
            Close
          </button>
          <button
            type="button"
            class="px-4 py-2 text-sm font-medium text-white bg-neutral-700 rounded-lg hover:bg-neutral-800"
            :disabled="!bulkFile || !bulkWarehouse"
            @click="submitBulkUpload"
          >
            Upload
          </button>
        </div>
      </div>
    </div>

    <!-- Unmapped codes panel -->
    <section class="card">
      <h3 class="section-title px-5 py-3 border-b border-slate-200">Unmapped codes (from latest SOH import)</h3>
      <div class="p-5 space-y-4">
        <div class="flex flex-wrap gap-4 items-center">
          <select
            v-model="unmappedWarehouse"
            class="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
            @change="fetchUnmapped"
          >
            <option value="">Select warehouse</option>
            <option v-for="w in warehouseOptions" :key="w" :value="w">{{ w }}</option>
          </select>
          <button
            type="button"
            class="px-3 py-2 text-sm font-medium text-neutral-700 bg-slate-100 rounded-lg hover:bg-slate-200"
            :disabled="!unmappedWarehouse"
            @click="fetchUnmapped"
          >
            Refresh
          </button>
          <button
            v-if="unmappedData?.unmapped?.length"
            type="button"
            class="px-3 py-2 text-sm font-medium text-neutral-700 bg-slate-100 rounded-lg hover:bg-slate-200"
            @click="downloadUnmappedCsv"
          >
            Download CSV
          </button>
        </div>
        <p v-if="!unmappedWarehouse" class="text-sm text-slate-500">Select a warehouse to see unmapped codes from the latest SOH import.</p>
        <p v-else-if="unmappedLoading" class="text-sm text-slate-500">Loading…</p>
        <p v-else-if="!unmappedData?.unmapped?.length" class="text-sm text-slate-500">No unmapped codes for this warehouse.</p>
        <div v-else class="overflow-x-auto max-h-64 overflow-y-auto">
          <table class="app-table text-sm">
            <thead>
              <tr>
                <th class="text-left">External code</th>
                <th class="text-left">Description</th>
                <th class="text-left">HS code guess</th>
                <th class="text-right">Qty sum</th>
                <th class="text-right">Rows</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in unmappedData.unmapped" :key="u.external_code">
                <td class="font-mono">{{ u.external_code }}</td>
                <td class="max-w-[200px] truncate" :title="u.description">{{ u.description || '—' }}</td>
                <td>{{ u.hs_code_guess || '—' }}</td>
                <td class="text-right">{{ u.qty_sum }}</td>
                <td class="text-right">{{ u.sample_rows }}</td>
                <td>
                  <button
                    type="button"
                    class="text-xs text-blue-600 hover:underline"
                    @click="openDrawerFromUnmapped(u)"
                  >
                    Create mapping
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import api from '@/api/client'
import { useAdminStore } from '@/stores/admin'
import PageHeader from '@/components/console/PageHeader.vue'
import FilterBar from '@/components/console/FilterBar.vue'
import DataTable from '@/components/console/DataTable.vue'
import type { DataTableColumn, RowAction } from '@/components/console/DataTable.vue'
import DrawerForm from '@/components/console/DrawerForm.vue'

interface WarehouseProductCode {
  id: number
  warehouse_code: string
  external_code: string
  sku: string
  external_name: string | null
  hs_code: string | null
  active: boolean
  match_method: string | null
  match_confidence: number | null
  created_at: string
  updated_at: string
}

interface UnmappedCode {
  external_code: string
  description: string | null
  hs_code_guess: string | null
  qty_sum: number
  sample_rows: number
}

const adminStore = useAdminStore()
const loading = ref(false)
const search = ref('')
const filterWarehouse = ref('')
const filterActiveOnly = ref(true)
const rows = ref<WarehouseProductCode[]>([])
const pagination = ref({ page: 1, pageSize: 25, total: 0 })

const columns: DataTableColumn[] = [
  { key: 'warehouse_code', label: 'Warehouse' },
  { key: 'external_code', label: 'External code' },
  { key: 'sku', label: 'SKU' },
  { key: 'external_name', label: 'External name' },
  { key: 'hs_code', label: 'HS code' },
  { key: 'active', label: 'Active' },
  { key: 'match_method', label: 'Match method' },
  { key: 'match_confidence', label: 'Confidence' },
  { key: 'updated_at', label: 'Updated', format: 'datetime' },
]

const warehouseOptions = computed(() => {
  const codes = new Set<string>(['AAH', 'BLP'])
  adminStore.warehouses.forEach((w) => codes.add(w.code))
  return Array.from(codes).sort()
})

async function fetchRows() {
  loading.value = true
  try {
    const params: Record<string, string | number | boolean> = {
      limit: 500,
      offset: 0,
      active_only: filterActiveOnly.value,
    }
    if (filterWarehouse.value) params.warehouse_code = filterWarehouse.value
    if (search.value.trim()) params.q = search.value.trim()
    const { data } = await api.get<WarehouseProductCode[]>('/admin/warehouse-product-codes', { params })
    rows.value = data
    pagination.value.total = data.length
  } finally {
    loading.value = false
  }
}

watch([filterWarehouse, filterActiveOnly, search], () => {
  pagination.value.page = 1
  fetchRows()
})

const rowActions: RowAction[] = [
  {
    id: 'edit',
    label: 'Edit',
    handler: (row) => openDrawer('edit', row as unknown as WarehouseProductCode),
  },
  {
    id: 'deactivate',
    label: 'Deactivate',
    handler: async (row) => {
      const r = row as unknown as WarehouseProductCode
      await api.put(`/admin/warehouse-product-codes/${r.id}`, { active: false })
      fetchRows()
    },
  },
  {
    id: 'delete',
    label: 'Delete',
    handler: async (row) => {
      if (!confirm('Permanently delete this mapping?')) return
      const r = row as unknown as WarehouseProductCode
      await api.delete(`/admin/warehouse-product-codes/${r.id}`)
      fetchRows()
    },
  },
]

const drawerOpen = ref(false)
const drawerMode = ref<'add' | 'edit'>('add')
const editingId = ref<number | null>(null)
const drawerForm = ref({
  warehouse_code: '',
  external_code: '',
  sku: '',
  external_name: '',
  hs_code: '',
  active: true,
})

function openDrawer(mode: 'add' | 'edit', row?: WarehouseProductCode) {
  drawerMode.value = mode
  editingId.value = row?.id ?? null
  if (mode === 'add') {
    drawerForm.value = {
      warehouse_code: filterWarehouse.value || '',
      external_code: '',
      sku: '',
      external_name: '',
      hs_code: '',
      active: true,
    }
  } else if (row) {
    drawerForm.value = {
      warehouse_code: row.warehouse_code,
      external_code: row.external_code,
      sku: row.sku,
      external_name: row.external_name || '',
      hs_code: row.hs_code || '',
      active: row.active,
    }
  }
  drawerOpen.value = true
}

function openDrawerFromUnmapped(u: UnmappedCode) {
  drawerMode.value = 'add'
  editingId.value = null
  drawerForm.value = {
    warehouse_code: unmappedWarehouse.value || '',
    external_code: u.external_code,
    sku: '',
    external_name: u.description || '',
    hs_code: u.hs_code_guess || '',
    active: true,
  }
  drawerOpen.value = true
  showBulkUpload.value = false
}

async function submitDrawer() {
  if (drawerMode.value === 'add') {
    await api.post('/admin/warehouse-product-codes', {
      warehouse_code: drawerForm.value.warehouse_code,
      external_code: drawerForm.value.external_code,
      sku: drawerForm.value.sku,
      external_name: drawerForm.value.external_name || null,
      hs_code: drawerForm.value.hs_code || null,
      active: drawerForm.value.active,
    })
  } else if (editingId.value != null) {
    await api.put(`/admin/warehouse-product-codes/${editingId.value}`, {
      sku: drawerForm.value.sku,
      external_name: drawerForm.value.external_name || null,
      hs_code: drawerForm.value.hs_code || null,
      active: drawerForm.value.active,
    })
  }
  drawerOpen.value = false
  fetchRows()
  if (unmappedWarehouse.value) fetchUnmapped()
}

const showBulkUpload = ref(false)
const bulkWarehouse = ref('')
const bulkFile = ref<File | null>(null)
const bulkFileName = ref('')
const bulkFileInput = ref<HTMLInputElement | null>(null)
const bulkError = ref('')
const bulkResult = ref('')

function onBulkFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) {
    bulkFile.value = file
    bulkFileName.value = file.name
  } else {
    bulkFile.value = null
    bulkFileName.value = ''
  }
  bulkError.value = ''
  bulkResult.value = ''
}

async function submitBulkUpload() {
  if (!bulkFile.value || !bulkWarehouse.value) return
  bulkError.value = ''
  bulkResult.value = ''
  try {
    const form = new FormData()
    form.append('file', bulkFile.value)
    const { data } = await api.post<{ created: number; updated: number; errors: number }>(
      `/admin/warehouse-product-codes/bulk?warehouse_code=${encodeURIComponent(bulkWarehouse.value)}`,
      form
    )
    bulkResult.value = `Created: ${data.created}, updated: ${data.updated}${data.errors ? `, errors: ${data.errors}` : ''}`
    fetchRows()
    bulkFile.value = null
    bulkFileName.value = ''
    bulkFileInput.value?.value && (bulkFileInput.value.value = '')
  } catch (err: unknown) {
    bulkError.value = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Upload failed'
  }
}

const unmappedWarehouse = ref('')
const unmappedLoading = ref(false)
const unmappedData = ref<{ unmapped: UnmappedCode[]; import_run_id: string | null; warehouse_code: string } | null>(null)

async function downloadUnmappedCsv() {
  if (!unmappedWarehouse.value) return
  try {
    const { data } = await api.get<string>('/admin/warehouse-product-codes/unmapped/csv', {
      params: { warehouse_code: unmappedWarehouse.value },
      responseType: 'blob',
    })
    const blob = new Blob([data], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'unmapped-codes.csv'
    a.click()
    URL.revokeObjectURL(a.href)
  } catch {
    // ignore
  }
}

async function fetchUnmapped() {
  if (!unmappedWarehouse.value) {
    unmappedData.value = null
    return
  }
  unmappedLoading.value = true
  try {
    const { data } = await api.get<{ unmapped: UnmappedCode[]; import_run_id: string | null; warehouse_code: string }>(
      '/admin/warehouse-product-codes/unmapped',
      { params: { warehouse_code: unmappedWarehouse.value } }
    )
    unmappedData.value = data
  } finally {
    unmappedLoading.value = false
  }
}

const paginatedRows = computed(() => {
  const { page, pageSize } = pagination.value
  const start = (page - 1) * pageSize
  return rows.value.slice(start, start + pageSize)
})

onMounted(async () => {
  await adminStore.fetchWarehouses()
  fetchRows()
})
</script>
