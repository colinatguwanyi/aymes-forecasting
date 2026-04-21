<template>
  <div class="space-y-4">
    <PageHeader title="Warehouses" :breadcrumbs="[{ label: 'Admin', path: '/admin/warehouses' }]" />
    <FilterBar v-model="search" search-placeholder="Search by code or name…" :has-active-filters="filterActive !== 'all'" @clear="filterActive = 'all'; search = ''">
      <template #leading>
        <button type="button" class="btn-primary px-4" @click="openDrawer('add')">Add warehouse</button>
        <button type="button" class="btn-secondary px-4" @click="exportCsv">Export CSV</button>
      </template>
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
        <div>
          <label class="block text-sm font-medium text-neutral-700 mb-1">Timezone</label>
          <input v-model="drawerForm.timezone" type="text" class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm" placeholder="Europe/London" />
        </div>
        <div class="flex items-center gap-2">
          <input id="wh-active" v-model="drawerForm.active" type="checkbox" class="rounded border-neutral-300" />
          <label for="wh-active" class="text-sm text-neutral-700 cursor-pointer">Active</label>
        </div>
        <div class="border-t border-neutral-200 pt-3 mt-2">
          <p class="text-xs font-medium text-neutral-500 uppercase tracking-wide mb-2">Site details</p>
          <div class="flex items-center gap-2 mb-3">
            <input id="wh-own" v-model="drawerForm.is_own_site" type="checkbox" class="rounded border-neutral-300" />
            <label for="wh-own" class="text-sm text-neutral-700 cursor-pointer">AYMES / our site (uncheck if 3PL or another company&apos;s warehouse)</label>
          </div>
          <div class="mb-3">
            <label class="block text-sm font-medium text-neutral-700 mb-1">Operator / 3PL name</label>
            <input
              v-model="drawerForm.operator_name"
              type="text"
              class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
              placeholder="e.g. partner logistics company (when not our site)"
            />
          </div>
          <div class="mb-3">
            <label class="block text-sm font-medium text-neutral-700 mb-1">Address</label>
            <textarea v-model="drawerForm.address" rows="3" class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm" placeholder="Street, city, postcode…" />
          </div>
          <div>
            <label class="block text-sm font-medium text-neutral-700 mb-1">Site type</label>
            <select v-model="drawerForm.site_type" class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white">
              <option value="soh_warehouse">SOH at our warehouse</option>
              <option value="factory">Our factory</option>
              <option value="third_party_3pl">Third-party / 3PL</option>
            </select>
          </div>
        </div>
      </form>
      <template #footer>
        <button type="button" class="btn-secondary px-4" @click="drawerOpen = false">Cancel</button>
        <button type="button" class="btn-primary px-4" @click="submitDrawer">{{ drawerMode === 'add' ? 'Add warehouse' : 'Save' }}</button>
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
import axios from 'axios'

const router = useRouter()
const store = useAdminStore()
const search = ref('')
const filterActive = ref<'all' | 'yes' | 'no'>('all')
const debouncedSearch = useDebounce(search, 300)
const loading = ref(false)
const columns: DataTableColumn[] = [
  { key: 'code', label: 'Code', sortable: true },
  { key: 'name', label: 'Name', sortable: true },
  { key: 'site_type_label', label: 'Type', sortable: true },
  { key: 'active', label: 'Active', sortable: true, format: 'boolean' },
  { key: 'has_stock', label: 'Has stock', sortable: true, format: 'boolean' },
]
const sortField = ref<string>('code')
const sortDir = ref<'asc' | 'desc'>('asc')

const SITE_LABELS: Record<string, string> = {
  soh_warehouse: 'SOH warehouse',
  factory: 'Factory',
  third_party_3pl: '3PL',
}

const filteredRows = computed(() => {
  let list = store.warehouses as unknown as Record<string, unknown>[]
  const q = debouncedSearch.value.toLowerCase()
  if (q) list = list.filter((r) => String(r.code ?? '').toLowerCase().includes(q) || String(r.name ?? '').toLowerCase().includes(q))
  if (filterActive.value === 'yes') list = list.filter((r) => r.active === true)
  if (filterActive.value === 'no') list = list.filter((r) => r.active === false)
  list = list.map((r) => ({
    ...r,
    site_type_label: SITE_LABELS[String(r.site_type)] ?? String(r.site_type ?? '—'),
  }))
  const field = sortField.value
  list = [...list].sort((a, b) => {
    const va = a[field],
      vb = b[field]
    if (va == null && vb == null) return 0
    if (va == null) return sortDir.value === 'asc' ? 1 : -1
    if (vb == null) return sortDir.value === 'asc' ? -1 : 1
    const cmp = String(va).localeCompare(String(vb), undefined, { numeric: true })
    return sortDir.value === 'asc' ? cmp : -cmp
  })
  return list
})

const pagination = ref({ page: 1, pageSize: 25, total: 0 })
watch(filteredRows, (rows) => {
  pagination.value.total = rows.length
}, { immediate: true })
const paginatedRows = computed(() => {
  const { page, pageSize } = pagination.value
  return filteredRows.value.slice((page - 1) * pageSize, page * pageSize)
})

function apiErr(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const d = e.response?.data
    if (d && typeof d === 'object' && 'detail' in d) {
      const det = (d as { detail: unknown }).detail
      return typeof det === 'string' ? det : JSON.stringify(det)
    }
  }
  return e instanceof Error ? e.message : 'Request failed'
}

async function confirmDelete(wh: Warehouse) {
  if (wh.active) {
    window.alert('Set the warehouse to inactive first, then you can delete it.')
    return
  }
  if (wh.has_stock) {
    window.alert(
      'This warehouse still has quantity in stock-on-hand snapshots or stock positions. Clear or reassign that data before deleting.',
    )
    return
  }
  if (!window.confirm(`Delete warehouse "${wh.code}"? This cannot be undone. Remove lanes and warehouse–product links first if the server rejects the delete.`)) return
  try {
    await store.deleteWarehouse(wh.id)
  } catch (e) {
    window.alert(apiErr(e))
  }
}

const rowActions: RowAction[] = [
  { id: 'view', label: 'View', handler: (row) => router.push({ name: 'AdminWarehouseDetail', params: { id: String(row.id) } }) },
  { id: 'edit', label: 'Edit', handler: (row) => openDrawer('edit', row as unknown as Warehouse) },
  { id: 'delete', label: 'Delete', handler: (row) => void confirmDelete(row as unknown as Warehouse) },
]

function onSort(field: string) {
  if (sortField.value === field) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else sortField.value = field
}

const drawerOpen = ref(false)
const drawerMode = ref<'add' | 'edit'>('add')
const editingId = ref<number | null>(null)

type SiteType = 'soh_warehouse' | 'factory' | 'third_party_3pl'

const defaultForm = () => ({
  code: '',
  name: '',
  timezone: 'Europe/London',
  active: true,
  is_own_site: true,
  operator_name: '',
  address: '',
  site_type: 'soh_warehouse' as SiteType,
})

const drawerForm = ref(defaultForm())

function openDrawer(mode: 'add' | 'edit', wh?: Warehouse) {
  drawerMode.value = mode
  editingId.value = wh?.id ?? null
  if (mode === 'add') {
    drawerForm.value = defaultForm()
  } else if (wh) {
    drawerForm.value = {
      code: wh.code,
      name: wh.name ?? '',
      timezone: wh.timezone ?? 'Europe/London',
      active: wh.active,
      is_own_site: wh.is_own_site ?? true,
      operator_name: wh.operator_name ?? '',
      address: wh.address ?? '',
      site_type: (['soh_warehouse', 'factory', 'third_party_3pl'].includes(wh.site_type) ? wh.site_type : 'soh_warehouse') as SiteType,
    }
  }
  drawerOpen.value = true
}

async function submitDrawer() {
  const body = {
    code: drawerForm.value.code.trim(),
    name: drawerForm.value.name.trim() || null,
    timezone: drawerForm.value.timezone.trim() || 'Europe/London',
    active: drawerForm.value.active,
    is_own_site: drawerForm.value.is_own_site,
    operator_name: drawerForm.value.operator_name.trim() || null,
    address: drawerForm.value.address.trim() || null,
    site_type: drawerForm.value.site_type,
  }
  try {
    if (drawerMode.value === 'add') await store.createWarehouse(body)
    else if (editingId.value != null) await store.updateWarehouse(editingId.value, body)
    drawerOpen.value = false
  } catch (e) {
    window.alert(apiErr(e))
  }
}

function exportCsv() {
  const headers = ['Code', 'Name', 'Type', 'Active', 'Has stock', 'Our site', 'Operator', 'Address']
  const rows = filteredRows.value.map((r) => {
    const addr = typeof r.address === 'string' ? r.address.replace(/\r?\n/g, ' ') : ''
    return [
      r.code,
      r.name ?? '',
      r.site_type_label,
      r.active ? 'Yes' : 'No',
      r.has_stock ? 'Yes' : 'No',
      r.is_own_site ? 'Yes' : 'No',
      r.operator_name ?? '',
      addr,
    ]
  })
  const csv = [headers.join(','), ...rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(','))].join('\n')
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }))
  a.download = 'warehouses.csv'
  a.click()
  URL.revokeObjectURL(a.href)
}

onMounted(async () => {
  loading.value = true
  await store.fetchWarehouses()
  loading.value = false
})
</script>
