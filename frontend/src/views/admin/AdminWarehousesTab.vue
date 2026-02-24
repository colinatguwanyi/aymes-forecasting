<template>
  <div class="space-y-4">
    <PageHeader title="Warehouses" :breadcrumbs="[{ label: 'Admin', path: '/admin/warehouses' }]">
      <template #actions>
        <button type="button" class="px-4 py-2 text-sm font-medium text-white bg-neutral-700 rounded-lg hover:bg-neutral-800" @click="openDrawer('add')">Add warehouse</button>
        <button type="button" class="px-4 py-2 text-sm font-medium text-neutral-700 bg-white border border-neutral-300 rounded-lg hover:bg-neutral-50" @click="exportCsv">Export CSV</button>
      </template>
    </PageHeader>
    <FilterBar v-model="search" search-placeholder="Search by code or name…" :has-active-filters="filterActive !== 'all'" @clear="filterActive = 'all'; search = ''">
      <template #filters>
        <select v-model="filterActive" class="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white min-w-[120px]">
          <option value="all">All status</option>
          <option value="yes">Active only</option>
          <option value="no">Inactive only</option>
        </select>
      </template>
    </FilterBar>
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
      :on-row-click="(row) => $router.push({ name: 'AdminWarehouseDetail', params: { id: String(row.id) } })"
    >
      <template #empty>No warehouses. Add one to get started.</template>
    </DataTable>
    <DrawerForm v-model="drawerOpen" :title="drawerMode === 'add' ? 'Add warehouse' : 'Edit warehouse'">
      <form class="space-y-4" @submit.prevent="submitDrawer">
        <div>
          <label class="block text-sm font-medium text-neutral-700 mb-1">Code <span class="text-red-600">*</span></label>
          <input v-model="drawerForm.code" type="text" required class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm" placeholder="Unique code" />
        </div>
        <div>
          <label class="block text-sm font-medium text-neutral-700 mb-1">Name</label>
          <input v-model="drawerForm.name" type="text" class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm" placeholder="Warehouse name" />
        </div>
      </form>
      <template #footer>
        <button type="button" class="px-4 py-2 text-sm font-medium text-neutral-600 bg-white border border-neutral-300 rounded-lg hover:bg-neutral-50" @click="drawerOpen = false">Cancel</button>
        <button type="button" class="px-4 py-2 text-sm font-medium text-white bg-neutral-700 rounded-lg hover:bg-neutral-800" @click="submitDrawer">{{ drawerMode === 'add' ? 'Add warehouse' : 'Save' }}</button>
      </template>
    </DrawerForm>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAdminStore } from '@/stores/admin'
import type { Warehouse } from '@/api/client'
import PageHeader from '@/components/console/PageHeader.vue'
import FilterBar from '@/components/console/FilterBar.vue'
import DataTable from '@/components/console/DataTable.vue'
import type { DataTableColumn, RowAction } from '@/components/console/DataTable.vue'
import DrawerForm from '@/components/console/DrawerForm.vue'
import { useDebounce } from '@/composables/useDebounce'

const router = useRouter()
const store = useAdminStore()
const search = ref('')
const filterActive = ref<'all' | 'yes' | 'no'>('all')
const debouncedSearch = useDebounce(search, 300)
const loading = ref(false)
const columns: DataTableColumn[] = [
  { key: 'code', label: 'Code', sortable: true },
  { key: 'name', label: 'Name', sortable: true },
  { key: 'active', label: 'Active', sortable: true, format: 'boolean' },
]
const sortField = ref<string>('code')
const sortDir = ref<'asc' | 'desc'>('asc')

const filteredRows = computed(() => {
  let list = store.warehouses as unknown as Record<string, unknown>[]
  const q = debouncedSearch.value.toLowerCase()
  if (q) list = list.filter((r) => String(r.code ?? '').toLowerCase().includes(q) || String(r.name ?? '').toLowerCase().includes(q))
  if (filterActive.value === 'yes') list = list.filter((r) => r.active === true)
  if (filterActive.value === 'no') list = list.filter((r) => r.active === false)
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
  { id: 'view', label: 'View', handler: (row) => router.push({ name: 'AdminWarehouseDetail', params: { id: String(row.id) } }) },
  { id: 'edit', label: 'Edit', handler: (row) => openDrawer('edit', row as unknown as Warehouse) },
  { id: 'delete', label: 'Delete', handler: () => {} },
]

function onSort(field: string) {
  if (sortField.value === field) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else sortField.value = field
}

const drawerOpen = ref(false)
const drawerMode = ref<'add' | 'edit'>('add')
const editingId = ref<number | null>(null)
const drawerForm = ref({ code: '', name: '', timezone: 'Europe/London', active: true })

function openDrawer(mode: 'add' | 'edit', wh?: Warehouse) {
  drawerMode.value = mode
  editingId.value = wh?.id ?? null
  if (mode === 'add') drawerForm.value = { code: '', name: '', timezone: 'Europe/London', active: true }
  else if (wh) drawerForm.value = { code: wh.code, name: wh.name ?? '', timezone: wh.timezone, active: wh.active }
  drawerOpen.value = true
}

async function submitDrawer() {
  if (drawerMode.value === 'add') await store.createWarehouse({ code: drawerForm.value.code, name: drawerForm.value.name || undefined })
  else if (editingId.value != null) await store.updateWarehouse(editingId.value, drawerForm.value)
  drawerOpen.value = false
}

function exportCsv() {
  const headers = ['Code', 'Name', 'Active']
  const rows = filteredRows.value.map((r) => [r.code, r.name ?? '', r.active ? 'Yes' : 'No'])
  const csv = [headers.join(','), ...rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(','))].join('\n')
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }))
  a.download = 'warehouses.csv'
  a.click()
  URL.revokeObjectURL(a.href)
}

onMounted(async () => { loading.value = true; await store.fetchWarehouses(); loading.value = false })
</script>
