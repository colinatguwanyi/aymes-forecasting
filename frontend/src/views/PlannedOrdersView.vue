<template>
  <div class="space-y-4">
    <PageHeader title="Planned Orders" :breadcrumbs="[{ label: 'Planning', path: '/' }]">
      <template #actions>
        <a v-if="selectedRunId" :href="exportUrl" class="px-4 py-2 text-sm font-medium text-neutral-700 bg-white border border-neutral-300 rounded-lg hover:bg-neutral-50" download>Export CSV</a>
      </template>
    </PageHeader>

    <FilterBar v-model="search" search-placeholder="Search SKU or warehouse…" :has-active-filters="!!selectedRunId || !!skuFilter || !!whFilter" @clear="selectedRunId = null; skuFilter = ''; whFilter = ''; search = ''">
      <template #filters>
        <select v-model="selectedRunId" class="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white min-w-48">
          <option :value="null">Plan run</option>
          <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }}</option>
        </select>
        <select v-model="skuFilter" class="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white min-w-40">
          <option value="">All SKUs</option>
          <option v-for="p in products" :key="p.id" :value="p.sku">{{ p.sku }}</option>
        </select>
        <select v-model="whFilter" class="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white min-w-40">
          <option value="">All warehouses</option>
          <option v-for="w in warehouses" :key="w.id" :value="w.code">{{ w.code }}</option>
        </select>
      </template>
    </FilterBar>

    <div class="border border-neutral-200 rounded-lg bg-white overflow-hidden">
      <div v-if="displayOrders.length" class="overflow-x-auto max-h-[60vh] overflow-y-auto">
        <table class="w-full text-sm border-collapse">
          <thead class="sticky top-0 bg-neutral-50 border-b border-neutral-200">
            <tr>
              <th class="px-3 py-2 text-left font-medium text-neutral-600">Week start</th>
              <th class="px-3 py-2 text-left font-medium text-neutral-600">SKU</th>
              <th class="px-3 py-2 text-left font-medium text-neutral-600">Warehouse</th>
              <th class="px-3 py-2 text-left font-medium text-neutral-600">Order qty</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="o in displayOrders" :key="o.id" class="border-b border-neutral-100 hover:bg-neutral-50">
              <td class="px-3 py-2">{{ o.week_start }}</td>
              <td class="px-3 py-2">{{ o.sku }}</td>
              <td class="px-3 py-2">{{ o.warehouse_code }}</td>
              <td class="px-3 py-2">{{ o.order_qty }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="px-4 py-8 text-sm text-neutral-500">No planned orders. Select a scenario or run a plan.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { usePlanningStore } from '@/stores/planning'
import { useAdminStore } from '@/stores/admin'
import type { PlannedOrder } from '@/api/client'
import PageHeader from '@/components/console/PageHeader.vue'
import FilterBar from '@/components/console/FilterBar.vue'

const store = usePlanningStore()
const adminStore = useAdminStore()
const selectedRunId = ref<number | null>(null)
const orders = ref<PlannedOrder[]>([])
const search = ref('')
const skuFilter = ref('')
const whFilter = ref('')

const planRuns = computed(() => store.planRuns)
const products = computed(() => adminStore.products)
const warehouses = computed(() => adminStore.warehouses)

const displayOrders = computed(() => {
  let list = orders.value
  if (skuFilter.value) list = list.filter((o) => o.sku === skuFilter.value)
  if (whFilter.value) list = list.filter((o) => o.warehouse_code === whFilter.value)
  const q = search.value.toLowerCase()
  if (q) list = list.filter((o) => o.sku.toLowerCase().includes(q) || o.warehouse_code.toLowerCase().includes(q))
  return list
})

const exportUrl = computed(() =>
  selectedRunId.value ? `/api/exports/planned-orders?plan_run_id=${selectedRunId.value}` : '#'
)

watch(selectedRunId, async (id) => {
  if (id) {
    orders.value = await store.fetchPlannedOrders(id)
  } else {
    orders.value = []
  }
}, { immediate: true })

onMounted(() => {
  store.fetchPlanRuns()
  adminStore.fetchProducts()
  adminStore.fetchWarehouses()
})
</script>
