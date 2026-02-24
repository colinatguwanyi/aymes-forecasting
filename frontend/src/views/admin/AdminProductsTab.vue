<template>
  <div class="space-y-4">
    <PageHeader
      title="Products"
      :breadcrumbs="[{ label: 'Admin', path: '/admin/products' }]"
    >
      <template #actions>
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium text-white bg-neutral-700 rounded-lg hover:bg-neutral-800"
          @click="openDrawer('add')"
        >
          Add product
        </button>
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium text-neutral-700 bg-white border border-neutral-300 rounded-lg hover:bg-neutral-50"
          @click="exportCsv"
        >
          Export CSV
        </button>
      </template>
    </PageHeader>

    <FilterBar
      v-model="search"
      search-placeholder="Search by SKU or name…"
      :has-active-filters="filterActive !== 'all'"
      @clear="filterActive = 'all'; search = ''"
    >
      <template #filters>
        <select
          v-model="filterActive"
          class="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white min-w-[120px]"
        >
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
      :on-row-click="(row) => $router.push({ name: 'AdminProductDetail', params: { id: String(row.id) } })"
      @update:page="pagination.page = $event"
      @update:pageSize="pagination.pageSize = $event; pagination.page = 1"
    >
      <template #empty>
        No products. Add one to get started.
      </template>
    </DataTable>

    <DrawerForm
      v-model="drawerOpen"
      :title="drawerMode === 'add' ? 'Add product' : 'Edit product'"
    >
      <form class="space-y-4" @submit.prevent="submitDrawer">
        <div>
          <label class="block text-sm font-medium text-neutral-700 mb-1">SKU <span class="text-red-600">*</span></label>
          <input
            v-model="drawerForm.sku"
            type="text"
            required
            class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
            placeholder="Unique SKU"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-neutral-700 mb-1">Name</label>
          <input
            v-model="drawerForm.name"
            type="text"
            class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
            placeholder="Product name"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-neutral-700 mb-1">Description</label>
          <input
            v-model="drawerForm.description"
            type="text"
            class="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm"
            placeholder="Description"
          />
        </div>
        <div class="flex items-center gap-2">
          <input v-model="drawerForm.active" type="checkbox" id="prod-active" class="rounded border-neutral-300" />
          <label for="prod-active" class="text-sm text-neutral-700">Active</label>
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
          {{ drawerMode === 'add' ? 'Add product' : 'Save' }}
        </button>
      </template>
    </DrawerForm>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAdminStore } from '@/stores/admin'
import type { Product } from '@/api/client'
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
  { key: 'sku', label: 'SKU', sortable: true },
  { key: 'name', label: 'Name', sortable: true },
  { key: 'description', label: 'Description' },
  { key: 'active', label: 'Active', sortable: true, format: 'boolean' },
]

const sortField = ref<string>('sku')
const sortDir = ref<'asc' | 'desc'>('asc')

const filteredRows = computed(() => {
  let list = store.products as unknown as Record<string, unknown>[]
  const q = debouncedSearch.value.toLowerCase()
  if (q) {
    list = list.filter(
      (r) =>
        String(r.sku ?? '').toLowerCase().includes(q) ||
        String(r.name ?? '').toLowerCase().includes(q)
    )
  }
  if (filterActive.value === 'yes') list = list.filter((r) => r.active === true)
  if (filterActive.value === 'no') list = list.filter((r) => r.active === false)
  const field = sortField.value
  list = [...list].sort((a, b) => {
    const va = a[field]
    const vb = b[field]
    if (va == null && vb == null) return 0
    if (va == null) return sortDir.value === 'asc' ? 1 : -1
    if (vb == null) return sortDir.value === 'asc' ? -1 : 1
    const cmp = String(va).localeCompare(String(vb), undefined, { numeric: true })
    return sortDir.value === 'asc' ? cmp : -cmp
  })
  return list
})

const pagination = ref({ page: 1, pageSize: 25, total: 0 })
watch(
  filteredRows,
  (rows) => {
    pagination.value.total = rows.length
  },
  { immediate: true }
)
const paginatedRows = computed(() => {
  const { page, pageSize } = pagination.value
  const start = (page - 1) * pageSize
  return filteredRows.value.slice(start, start + pageSize)
})

const rowActions: RowAction[] = [
  {
    id: 'view',
    label: 'View',
    handler: (row) => router.push({ name: 'AdminProductDetail', params: { id: String(row.id) } }),
  },
  {
    id: 'edit',
    label: 'Edit',
    handler: (row) => openDrawer('edit', row as unknown as Product),
  },
  {
    id: 'delete',
    label: 'Delete',
    handler: () => {},
  },
]

function onSort(field: string) {
  if (sortField.value === field) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else sortField.value = field
}

const drawerOpen = ref(false)
const drawerMode = ref<'add' | 'edit'>('add')
const editingId = ref<number | null>(null)
const drawerForm = ref({ sku: '', name: '', description: '', active: true })

function openDrawer(mode: 'add' | 'edit', product?: Product) {
  drawerMode.value = mode
  editingId.value = product?.id ?? null
  if (mode === 'add') {
    drawerForm.value = { sku: '', name: '', description: '', active: true }
  } else if (product) {
    drawerForm.value = {
      sku: product.sku,
      name: product.name ?? '',
      description: product.description ?? '',
      active: product.active,
    }
  }
  drawerOpen.value = true
}

async function submitDrawer() {
  if (drawerMode.value === 'add') {
    await store.createProduct({
      sku: drawerForm.value.sku,
      name: drawerForm.value.name || undefined,
      description: drawerForm.value.description || undefined,
      active: drawerForm.value.active,
    })
  } else if (editingId.value != null) {
    await store.updateProduct(editingId.value, drawerForm.value)
  }
  drawerOpen.value = false
}

function exportCsv() {
  const headers = ['SKU', 'Name', 'Description', 'Active']
  const rows = filteredRows.value.map((r) => [
    r.sku,
    r.name ?? '',
    r.description ?? '',
    r.active ? 'Yes' : 'No',
  ])
  const csv = [headers.join(','), ...rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(','))].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'products.csv'
  a.click()
  URL.revokeObjectURL(a.href)
}

onMounted(async () => {
  loading.value = true
  await store.fetchProducts()
  loading.value = false
})
</script>
