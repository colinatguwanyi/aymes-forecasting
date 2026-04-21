<template>
  <div class="space-y-4">
    <PageHeader title="Lanes (Supplier → Warehouse)" :breadcrumbs="[{ label: 'Admin', path: '/admin/lanes' }]">
      <template #actions>
        <button type="button" class="btn-primary px-4" @click="openDrawer">Add lane</button>
        <button type="button" class="px-4 py-2 text-sm font-medium text-neutral-700 bg-white border border-neutral-300 rounded-lg hover:bg-neutral-50" @click="exportCsv">Export CSV</button>
      </template>
    </PageHeader>
    <FilterBar v-model="search" search-placeholder="Search by supplier or warehouse…" :has-active-filters="false" @clear="search = ''" />
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
      :on-row-click="(row) => $router.push({ name: 'AdminLaneDetail', params: { id: String(row.id) } })"
    >
      <template #empty>No lanes. Add one to connect a supplier to a warehouse.</template>
    </DataTable>
    <DrawerForm v-model="drawerOpen" title="Add lane">
      <form class="space-y-4" @submit.prevent="submitLane">
        <div>
          <label class="block text-sm font-medium text-neutral-700 mb-1">Supplier <span class="text-red-600">*</span></label>
          <select v-model.number="form.supplier_id" required class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white">
            <option :value="0">Select supplier</option>
            <option v-for="s in store.suppliers" :key="s.id" :value="s.id">{{ s.code }} – {{ s.name ?? '' }}</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium text-neutral-700 mb-1">Warehouse <span class="text-red-600">*</span></label>
          <select v-model.number="form.warehouse_id" required class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white">
            <option :value="0">Select warehouse</option>
            <option v-for="w in store.warehouses" :key="w.id" :value="w.id">{{ w.code }} – {{ w.name ?? '' }}</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium text-neutral-700 mb-1">Lane code</label>
          <input v-model="form.code" type="text" class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm" placeholder="Optional" />
        </div>
      </form>
      <template #footer>
        <button type="button" class="px-4 py-2 text-sm font-medium text-neutral-600 bg-white border border-neutral-300 rounded-lg hover:bg-neutral-50" @click="drawerOpen = false">Cancel</button>
        <button type="button" class="btn-primary px-4" @click="submitLane">Add lane</button>
      </template>
    </DrawerForm>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAdminStore } from '@/stores/admin'
import PageHeader from '@/components/console/PageHeader.vue'
import FilterBar from '@/components/console/FilterBar.vue'
import DataTable from '@/components/console/DataTable.vue'
import type { DataTableColumn, RowAction } from '@/components/console/DataTable.vue'
import DrawerForm from '@/components/console/DrawerForm.vue'
import { useDebounce } from '@/composables/useDebounce'

const router = useRouter()
const store = useAdminStore()
const search = ref('')
const debouncedSearch = useDebounce(search, 300)
const loading = ref(false)

function supplierName(id: number) {
  const s = store.suppliers.find((x) => x.id === id)
  return s ? `${s.code} – ${s.name ?? ''}`.trim() : String(id)
}
function warehouseName(id: number) {
  const w = store.warehouses.find((x) => x.id === id)
  return w ? `${w.code} – ${w.name ?? ''}`.trim() : String(id)
}

const tableRows = computed(() =>
  store.lanes.map((l) => ({
    id: l.id,
    supplier_id: l.supplier_id,
    warehouse_id: l.warehouse_id,
    supplier_name: supplierName(l.supplier_id),
    warehouse_name: warehouseName(l.warehouse_id),
    code: l.code ?? '',
  }))
)

const columns: DataTableColumn[] = [
  { key: 'supplier_name', label: 'Supplier', sortable: true },
  { key: 'warehouse_name', label: 'Warehouse', sortable: true },
  { key: 'code', label: 'Lane code', sortable: true },
]

const sortField = ref<string>('supplier_name')
const sortDir = ref<'asc' | 'desc'>('asc')

const filteredRows = computed(() => {
  let list = tableRows.value as unknown as Record<string, unknown>[]
  const q = debouncedSearch.value.toLowerCase()
  if (q) list = list.filter((r) => String(r.supplier_name ?? '').toLowerCase().includes(q) || String(r.warehouse_name ?? '').toLowerCase().includes(q))
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
  { id: 'view', label: 'View', handler: (row) => router.push({ name: 'AdminLaneDetail', params: { id: String(row.id) } }) },
  { id: 'delete', label: 'Remove', handler: (row) => store.deleteLane(Number(row.id)) },
]

function onSort(field: string) {
  if (sortField.value === field) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else sortField.value = field
}

const drawerOpen = ref(false)
const form = ref({ supplier_id: 0, warehouse_id: 0, code: '' })

function openDrawer() {
  form.value = { supplier_id: 0, warehouse_id: 0, code: '' }
  drawerOpen.value = true
}

async function submitLane() {
  if (!form.value.supplier_id || !form.value.warehouse_id) return
  await store.createLane({ supplier_id: form.value.supplier_id, warehouse_id: form.value.warehouse_id, code: form.value.code || undefined })
  drawerOpen.value = false
}

function exportCsv() {
  const headers = ['Supplier', 'Warehouse', 'Lane code']
  const rows = filteredRows.value.map((r) => [r.supplier_name, r.warehouse_name, r.code])
  const csv = [headers.join(','), ...rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(','))].join('\n')
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }))
  a.download = 'lanes.csv'
  a.click()
  URL.revokeObjectURL(a.href)
}

onMounted(async () => {
  loading.value = true
  await Promise.all([store.fetchLanes(), store.fetchSuppliers(), store.fetchWarehouses()])
  loading.value = false
})
</script>
