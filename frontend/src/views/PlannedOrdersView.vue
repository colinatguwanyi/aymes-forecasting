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
      <NoDataWithReason
        v-else
        :title="noDataTitle"
        :reasons="noDataReasons"
        :actions="noDataActions"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { usePlanningStore } from '@/stores/planning'
import { useAdminStore } from '@/stores/admin'
import type { PlannedOrder } from '@/api/client'
import { fetchPlanningReadiness } from '@/api/client'
import PageHeader from '@/components/console/PageHeader.vue'
import FilterBar from '@/components/console/FilterBar.vue'
import NoDataWithReason from '@/components/console/NoDataWithReason.vue'

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

const diagnosticsData = ref<Awaited<ReturnType<typeof fetchPlanningReadiness>> | null>(null)
const noDataTitle = computed(() => {
  if (!selectedRunId.value && store.planRuns.length) return 'No plan run selected'
  if (!selectedRunId.value) return 'No plan runs yet'
  return 'No planned orders for this plan run'
})
const noDataReasons = computed(() => {
  const d = diagnosticsData.value
  if (!d) return ['Loading diagnostics…']
  return d.blockers.map((b) => b.message)
})
const noDataActions = computed(() => {
  const d = diagnosticsData.value
  if (!d) return []
  const seen = new Set<string>()
  return d.blockers
    .filter((b) => !seen.has(b.action_href) && seen.add(b.action_href))
    .map((b) => ({ label: b.action_label, href: b.action_href }))
})

watch(selectedRunId, async (id) => {
  if (id) {
    orders.value = await store.fetchPlannedOrders(id)
  } else {
    orders.value = []
  }
}, { immediate: true })

watch(
  () => ({ ordersLen: displayOrders.value.length, runId: selectedRunId.value }),
  async ({ ordersLen, runId }) => {
    if (ordersLen === 0) {
      diagnosticsData.value = await fetchPlanningReadiness(runId ?? undefined)
    } else {
      diagnosticsData.value = null
    }
  },
  { immediate: true }
)

onMounted(async () => {
  await Promise.all([store.fetchPlanRuns(), adminStore.fetchProducts(), adminStore.fetchWarehouses()])
  if (store.planRuns.length && !selectedRunId.value) selectedRunId.value = store.planRuns[0].id
})
</script>
