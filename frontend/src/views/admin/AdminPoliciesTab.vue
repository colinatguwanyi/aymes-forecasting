<template>
  <div class="space-y-4">
    <PageHeader title="Planning Policies (SKU × Warehouse)" :breadcrumbs="[{ label: 'Admin', path: '/admin/policies' }]">
      <template #actions>
        <button type="button" class="px-4 py-2 text-sm font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg hover:bg-emerald-100" :disabled="generateLoading" @click="generateDefaults">Generate Default Policies for AAH</button>
        <button type="button" class="px-4 py-2 text-sm font-medium text-white bg-neutral-700 rounded-lg hover:bg-neutral-800" @click="openDrawer('add')">Add policy</button>
        <button type="button" class="px-4 py-2 text-sm font-medium text-neutral-700 bg-white border border-neutral-300 rounded-lg hover:bg-neutral-50" @click="exportCsv">Export CSV</button>
      </template>
    </PageHeader>
    <FilterBar v-model="search" search-placeholder="Search by SKU or warehouse…" :has-active-filters="false" @clear="search = ''" />
    <DataTable
      :columns="columns"
      :rows="paginatedRows"
      row-key="id"
      :loading="loading"
      :pagination="pagination"
      :row-actions="rowActions"
      :sort-field="sortField"
      :sort-dir="sortDir"
      @sort="onSort"
      @update:page="pagination.page = $event"
      @update:pageSize="pagination.pageSize = $event; pagination.page = 1"
      :on-row-click="(row) => $router.push({ name: 'AdminPolicyDetail', params: { id: String(row.id) } })"
    >
      <template #empty>No planning policies. Add one to define SKU × warehouse settings.</template>
    </DataTable>
    <DrawerForm v-model="drawerOpen" :title="drawerMode === 'add' ? 'Add policy' : 'Edit policy'">
      <form class="space-y-4" @submit.prevent="submitDrawer">
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-neutral-700 mb-1">SKU <span class="text-red-600">*</span></label>
            <select v-model="drawerForm.sku" required class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white">
              <option value="">Select SKU</option>
              <option v-for="p in store.products" :key="p.id" :value="p.sku">{{ p.sku }} – {{ p.name ?? '' }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-neutral-700 mb-1">Warehouse <span class="text-red-600">*</span></label>
            <select v-model="drawerForm.warehouse_code" required class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white">
              <option value="">Select warehouse</option>
              <option v-for="w in store.warehouses" :key="w.id" :value="w.code">{{ w.code }} – {{ w.name ?? '' }}</option>
            </select>
          </div>
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-neutral-700 mb-1">Mode</label>
            <select v-model="drawerForm.mode" class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white">
              <option value="WOS_TARGET">WOS_TARGET</option>
              <option value="ROP">ROP</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-neutral-700 mb-1">Target weeks</label>
            <input v-model="drawerForm.target_weeks" type="text" class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm" />
          </div>
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-neutral-700 mb-1">Safety method</label>
            <select v-model="drawerForm.safety_stock_method" class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white">
              <option value="WEEKS">WEEKS</option>
              <option value="SERVICE_LEVEL">SERVICE_LEVEL</option>
            </select>
          </div>
          <div v-if="drawerForm.safety_stock_method === 'WEEKS'">
            <label class="block text-sm font-medium text-neutral-700 mb-1">Safety weeks</label>
            <input v-model="drawerForm.safety_stock_weeks" type="text" class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm" />
          </div>
          <div v-else>
            <label class="block text-sm font-medium text-neutral-700 mb-1">Service level</label>
            <input v-model="drawerForm.service_level" type="text" class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm" />
          </div>
        </div>
        <div class="flex items-center justify-between">
          <div>
            <label class="block text-sm font-medium text-neutral-700 mb-1">Forecast window (weeks)</label>
            <input v-model.number="drawerForm.forecast_window_weeks" type="number" min="1" class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm max-w-[8rem]" />
          </div>
          <label class="flex items-center gap-2">
            <input v-model="drawerForm.include_samples" type="checkbox" class="rounded border-neutral-300" />
            <span class="text-sm text-neutral-700">Include samples</span>
          </label>
        </div>
      </form>
      <template #footer>
        <button type="button" class="px-4 py-2 text-sm font-medium text-neutral-600 bg-white border border-neutral-300 rounded-lg hover:bg-neutral-50" @click="drawerOpen = false">Cancel</button>
        <button type="button" class="px-4 py-2 text-sm font-medium text-white bg-neutral-700 rounded-lg hover:bg-neutral-800" @click="submitDrawer">{{ drawerMode === 'add' ? 'Add policy' : 'Save' }}</button>
      </template>
    </DrawerForm>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAdminStore } from '@/stores/admin'
import api from '@/api/client'
import type { PlanningPolicy } from '@/api/client'
import PageHeader from '@/components/console/PageHeader.vue'
import FilterBar from '@/components/console/FilterBar.vue'
import DataTable from '@/components/console/DataTable.vue'
import type { DataTableColumn, RowAction } from '@/components/console/DataTable.vue'
import DrawerForm from '@/components/console/DrawerForm.vue'
import { useDebounce } from '@/composables/useDebounce'

const router = useRouter()
const store = useAdminStore()
const search = ref('')
const generateLoading = ref(false)
const debouncedSearch = useDebounce(search, 300)
const loading = ref(false)

function defaultPolicy(): Partial<PlanningPolicy> & { sku: string; warehouse_code: string } {
  return {
    sku: '',
    warehouse_code: '',
    mode: 'WOS_TARGET',
    target_weeks: '4',
    safety_stock_method: 'WEEKS',
    safety_stock_weeks: '1',
    service_level: '0.95',
    forecast_window_weeks: 8,
    include_samples: true,
    lead_time_production_weeks: '2',
    lead_time_slot_wait_weeks: '0',
    lead_time_haulage_weeks: '1',
    lead_time_putaway_weeks: '0',
    lead_time_padding_weeks: '0',
  }
}

const tableRows = computed(() =>
  store.planningPolicies.map((p) => ({
    ...p,
    safety_display: p.safety_stock_method === 'WEEKS' ? p.safety_stock_weeks : p.service_level,
  }))
)

const columns: DataTableColumn[] = [
  { key: 'sku', label: 'SKU', sortable: true },
  { key: 'warehouse_code', label: 'Warehouse', sortable: true },
  { key: 'mode', label: 'Mode', sortable: true },
  { key: 'target_weeks', label: 'Target weeks' },
  { key: 'safety_display', label: 'Safety (weeks / service)' },
  { key: 'forecast_window_weeks', label: 'Forecast window' },
  { key: 'include_samples', label: 'Include samples', format: 'boolean' },
]

const sortField = ref<string>('sku')
const sortDir = ref<'asc' | 'desc'>('asc')

const filteredRows = computed(() => {
  let list = tableRows.value as unknown as Record<string, unknown>[]
  const q = debouncedSearch.value.toLowerCase()
  if (q) list = list.filter((r) => String(r.sku ?? '').toLowerCase().includes(q) || String(r.warehouse_code ?? '').toLowerCase().includes(q))
  const field = sortField.value
  list = [...list].sort((a, b) => {
    const va = a[field], vb = b[field]
    if (va == null && vb == null) return 0
    if (va == null) return sortDir.value === 'asc' ? 1 : -1
    if (vb == null) return sortDir.value === 'asc' ? -1 : 1
    const cmp = String(va).localeCompare(String(vb), undefined, { numeric: true })
    return sortDir.value === 'asc' ? cmp : -cmp
  })
  return list
})

const pagination = ref({ page: 1, pageSize: 25, total: 0 })
watch(filteredRows, (rows) => { pagination.value.total = rows.length }, { immediate: true })
const paginatedRows = computed(() => {
  const { page, pageSize } = pagination.value
  return filteredRows.value.slice((page - 1) * pageSize, page * pageSize)
})

const rowActions: RowAction[] = [
  { id: 'view', label: 'View', handler: (row) => router.push({ name: 'AdminPolicyDetail', params: { id: String(row.id) } }) },
  { id: 'edit', label: 'Edit', handler: (row) => openDrawer('edit', row as unknown as PlanningPolicy & { safety_display?: string }) },
  { id: 'delete', label: 'Remove', handler: (row) => store.deletePlanningPolicy(Number(row.id)) },
]

function onSort(field: string) {
  if (sortField.value === field) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else sortField.value = field
}

const drawerOpen = ref(false)
const drawerMode = ref<'add' | 'edit'>('add')
const editingId = ref<number | null>(null)
const drawerForm = reactive(defaultPolicy())

function openDrawer(mode: 'add' | 'edit', pol?: PlanningPolicy) {
  drawerMode.value = mode
  editingId.value = pol?.id ?? null
  Object.assign(drawerForm, defaultPolicy())
  if (pol) {
    drawerForm.sku = pol.sku
    drawerForm.warehouse_code = pol.warehouse_code
    drawerForm.mode = pol.mode
    drawerForm.target_weeks = pol.target_weeks
    drawerForm.safety_stock_method = pol.safety_stock_method
    drawerForm.safety_stock_weeks = pol.safety_stock_weeks
    drawerForm.service_level = pol.service_level
    drawerForm.forecast_window_weeks = pol.forecast_window_weeks
    drawerForm.include_samples = pol.include_samples
    drawerForm.lead_time_production_weeks = pol.lead_time_production_weeks
    drawerForm.lead_time_slot_wait_weeks = pol.lead_time_slot_wait_weeks
    drawerForm.lead_time_haulage_weeks = pol.lead_time_haulage_weeks
    drawerForm.lead_time_putaway_weeks = pol.lead_time_putaway_weeks
    drawerForm.lead_time_padding_weeks = pol.lead_time_padding_weeks
  }
  drawerOpen.value = true
}

async function submitDrawer() {
  const payload = {
    sku: drawerForm.sku,
    warehouse_code: drawerForm.warehouse_code,
    mode: drawerForm.mode,
    target_weeks: drawerForm.target_weeks,
    safety_stock_method: drawerForm.safety_stock_method,
    safety_stock_weeks: drawerForm.safety_stock_weeks,
    service_level: drawerForm.service_level,
    forecast_window_weeks: drawerForm.forecast_window_weeks,
    include_samples: drawerForm.include_samples,
    lead_time_production_weeks: drawerForm.lead_time_production_weeks,
    lead_time_slot_wait_weeks: drawerForm.lead_time_slot_wait_weeks,
    lead_time_haulage_weeks: drawerForm.lead_time_haulage_weeks,
    lead_time_putaway_weeks: drawerForm.lead_time_putaway_weeks,
    lead_time_padding_weeks: drawerForm.lead_time_padding_weeks,
  }
  if (drawerMode.value === 'add') await store.createPlanningPolicy(payload)
  else if (editingId.value != null) await store.updatePlanningPolicy(editingId.value, payload)
  drawerOpen.value = false
}

async function generateDefaults() {
  generateLoading.value = true
  try {
    const { data } = await api.post<{ created: number }>('/planning-policies/generate-defaults', null, {
      params: { warehouse_code: 'AAH', default_target_weeks: 4, default_safety_stock_weeks: 1, default_lead_time_weeks: 2 },
    })
    await store.fetchPlanningPolicies()
    alert(`Created ${data.created} default policies for AAH.`)
  } catch (e: unknown) {
    const msg = e && typeof e === 'object' && 'response' in e && (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
    alert(msg || 'Failed to generate policies.')
  } finally {
    generateLoading.value = false
  }
}

function exportCsv() {
  const headers = ['SKU', 'Warehouse', 'Mode', 'Target weeks', 'Safety', 'Forecast window', 'Include samples']
  const rows = filteredRows.value.map((r) => [r.sku, r.warehouse_code, r.mode, r.target_weeks, r.safety_display, r.forecast_window_weeks, r.include_samples ? 'Yes' : 'No'])
  const csv = [headers.join(','), ...rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(','))].join('\n')
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }))
  a.download = 'planning_policies.csv'
  a.click()
  URL.revokeObjectURL(a.href)
}

onMounted(async () => {
  loading.value = true
  await Promise.all([store.fetchPlanningPolicies(), store.fetchProducts(), store.fetchWarehouses()])
  loading.value = false
})
</script>
