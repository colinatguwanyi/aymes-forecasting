<template>
  <div class="space-y-4">
    <PageHeader title="Stock Position Breakdown" :breadcrumbs="[{ label: 'Planning', path: '/' }]" />

    <FilterBar
      v-model="search"
      search-placeholder="Search SKU or warehouse…"
      :has-active-filters="hasActiveFilters"
      @clear="clearFilters"
    >
      <template #filters>
        <select v-model="planRunId" class="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white min-w-48">
          <option :value="null">Plan run</option>
          <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }}</option>
        </select>
        <select v-model="warehouseFilter" class="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white min-w-40">
          <option value="">All warehouses</option>
          <option v-for="w in warehouses" :key="w.id" :value="w.code">{{ w.code }}</option>
        </select>
        <select v-model="productFamilyFilter" class="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white min-w-40">
          <option value="">All families</option>
          <option v-for="f in productFamilies" :key="f" :value="f">{{ f }}</option>
        </select>
        <label class="flex items-center gap-2 text-sm text-neutral-700">
          <input v-model="breachOnly" type="checkbox" class="rounded border-neutral-300" />
          Breach only
        </label>
      </template>
    </FilterBar>

    <section v-if="loading" class="text-sm text-neutral-500 py-8">Loading…</section>
    <div v-else class="border border-neutral-200 rounded-lg bg-white overflow-hidden">
      <p class="px-4 py-1 text-xs text-neutral-500">Click a row to open the calculation breakdown and 12-week rolling view.</p>
      <div v-if="displayRows.length" class="overflow-x-auto max-h-[60vh] overflow-y-auto">
        <table class="w-full text-sm border-collapse">
          <thead class="sticky top-0 bg-neutral-50 border-b border-neutral-200">
            <tr>
              <th class="px-3 py-2 text-left font-medium text-neutral-600">SKU</th>
              <th class="px-3 py-2 text-left font-medium text-neutral-600">Warehouse</th>
              <th class="px-3 py-2 text-right font-medium text-neutral-600">On hand</th>
              <th class="px-3 py-2 text-right font-medium text-neutral-600">Avg demand</th>
              <th class="px-3 py-2 text-right font-medium text-neutral-600">ROP</th>
              <th class="px-3 py-2 text-right font-medium text-neutral-600">Target</th>
              <th class="px-3 py-2 text-left font-medium text-neutral-600">Next breach</th>
              <th class="px-3 py-2 text-left font-medium text-neutral-600">Order week</th>
              <th class="px-3 py-2 text-right font-medium text-neutral-600">Rec. qty</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="r in displayRows"
              :key="`${r.sku}-${r.warehouse_code}`"
              :class="[r.next_breach_week_start && 'bg-amber-50', 'border-b border-neutral-100 hover:bg-neutral-50 cursor-pointer']"
              @click="openDetail(r)"
            >
              <td class="px-3 py-2">{{ r.sku }}</td>
              <td class="px-3 py-2">{{ r.warehouse_code }}</td>
              <td class="px-3 py-2 text-right">{{ r.on_hand_qty }}</td>
              <td class="px-3 py-2 text-right">{{ r.avg_weekly_demand }}</td>
              <td class="px-3 py-2 text-right">{{ r.reorder_point_units }}</td>
              <td class="px-3 py-2 text-right">{{ r.target_stock_units }}</td>
              <td class="px-3 py-2">{{ r.next_breach_week_start ?? '—' }}</td>
              <td class="px-3 py-2">{{ r.recommended_order_week_start ?? '—' }}</td>
              <td class="px-3 py-2 text-right">{{ r.recommended_order_qty }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="px-4 py-8 text-sm text-neutral-500">No breakdown. Select a plan run and run a plan if needed.</p>
    </div>

    <Teleport to="#right-panel-body">
      <div v-if="detailRow" class="stock-position-detail">
        <template v-if="detailLoading">Loading…</template>
        <template v-else>
          <h3 class="text-sm font-semibold text-neutral-800 mb-2">{{ detailRow.sku }} × {{ detailRow.warehouse_code }}</h3>

          <section class="mb-4">
            <h4 class="text-xs font-medium text-neutral-600 uppercase tracking-wide mb-1">Inputs</h4>
            <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
              <dt class="text-neutral-500">On hand</dt><dd>{{ detailRow.on_hand_qty }} (week {{ detailRow.on_hand_snapshot_week ?? '—' }})</dd>
              <dt class="text-neutral-500">Avg weekly demand</dt><dd>{{ detailRow.avg_weekly_demand }}</dd>
              <dt class="text-neutral-500">Forecast window</dt><dd>{{ detailRow.forecast_window_weeks }} weeks</dd>
            </dl>
          </section>

          <section class="mb-4">
            <h4 class="text-xs font-medium text-neutral-600 uppercase tracking-wide mb-1">Policy</h4>
            <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
              <dt class="text-neutral-500">Mode</dt><dd>{{ detailRow.mode }}</dd>
              <dt class="text-neutral-500">Target weeks</dt><dd>{{ detailRow.target_weeks }}</dd>
              <dt class="text-neutral-500">Safety stock</dt><dd>{{ detailRow.safety_stock_method }} {{ detailRow.safety_stock_weeks }} wk → {{ detailRow.safety_stock_units }} units</dd>
              <dt class="text-neutral-500">Effective lead time</dt><dd>{{ detailRow.effective_lead_time_weeks }} wk (supplier {{ detailRow.supplier_lead_time_weeks }} + haul {{ detailRow.haulage_buffer_weeks }} + stock {{ detailRow.stocking_buffer_weeks }})</dd>
              <dt class="text-neutral-500">MOQ / Pack</dt><dd>{{ detailRow.moq_units ?? '—' }} / {{ detailRow.pack_size_units ?? '—' }}</dd>
            </dl>
          </section>

          <section class="mb-4">
            <h4 class="text-xs font-medium text-neutral-600 uppercase tracking-wide mb-1">Derived</h4>
            <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
              <dt class="text-neutral-500">Reorder point</dt><dd>{{ detailRow.reorder_point_units }}</dd>
              <dt class="text-neutral-500">Target stock</dt><dd>{{ detailRow.target_stock_units }}</dd>
              <dt class="text-neutral-500">Next breach week</dt><dd>{{ detailRow.next_breach_week_start ?? '—' }}</dd>
              <dt class="text-neutral-500">Recommended order week</dt><dd>{{ detailRow.recommended_order_week_start ?? '—' }}</dd>
              <dt class="text-neutral-500">Recommended order qty</dt><dd>{{ detailRow.recommended_order_qty }}</dd>
              <dt class="text-neutral-500">Projected qty at arrival</dt><dd>{{ detailRow.projected_qty_at_arrival ?? '—' }}</dd>
            </dl>
          </section>

          <section>
            <h4 class="text-xs font-medium text-neutral-600 uppercase tracking-wide mb-1">Rolling 12 weeks</h4>
            <div class="overflow-x-auto max-h-[40vh] overflow-y-auto">
              <table class="w-full text-xs border-collapse">
                <thead class="bg-neutral-50 border-b border-neutral-200">
                  <tr>
                    <th class="px-2 py-1.5 text-left font-medium text-neutral-600">Week</th>
                    <th class="px-2 py-1.5 text-right font-medium text-neutral-600">Open</th>
                    <th class="px-2 py-1.5 text-right font-medium text-neutral-600">Receipts</th>
                    <th class="px-2 py-1.5 text-right font-medium text-neutral-600">Demand</th>
                    <th class="px-2 py-1.5 text-right font-medium text-neutral-600">Close</th>
                    <th class="px-2 py-1.5 text-right font-medium text-neutral-600">WOC</th>
                    <th class="px-2 py-1.5 text-right font-medium text-neutral-600">Order</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="w in rollingWeeks"
                    :key="w.week_start"
                    :class="[w.stockout && 'bg-red-50', 'border-b border-neutral-100']"
                  >
                    <td class="px-2 py-1.5">{{ w.week_start }}</td>
                    <td class="px-2 py-1.5 text-right">{{ w.opening_qty }}</td>
                    <td class="px-2 py-1.5 text-right">{{ w.receipts_qty }}</td>
                    <td class="px-2 py-1.5 text-right">{{ w.demand_qty }}</td>
                    <td class="px-2 py-1.5 text-right">{{ w.closing_qty }}</td>
                    <td class="px-2 py-1.5 text-right">{{ w.weeks_of_cover ?? '—' }}</td>
                    <td class="px-2 py-1.5 text-right">{{ w.planned_order_qty ?? '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p v-if="!rollingWeeks.length" class="text-xs text-neutral-500 py-2">No rolling data.</p>
          </section>
        </template>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { usePlanningStore } from '@/stores/planning'
import { useAdminStore } from '@/stores/admin'
import { useLayoutStore } from '@/stores/layout'
import type { StockPositionBreakdown } from '@/api/client'
import PageHeader from '@/components/console/PageHeader.vue'
import FilterBar from '@/components/console/FilterBar.vue'

const store = usePlanningStore()
const adminStore = useAdminStore()
const layout = useLayoutStore()
const planRunId = ref<number | null>(null)
const warehouseFilter = ref('')
const productFamilyFilter = ref('')
const breachOnly = ref(false)
const search = ref('')
const loading = ref(false)
const breakdown = ref<StockPositionBreakdown[]>([])
const detailRow = ref<StockPositionBreakdown | null>(null)
const detailLoading = ref(false)
const rollingWeeks = ref<{ week_start: string; opening_qty: string; receipts_qty: string; demand_qty: string; closing_qty: string; weeks_of_cover: number | null; stockout: boolean; planned_order_qty: string | null }[]>([])

const planRuns = computed(() => store.planRuns)
const warehouses = computed(() => adminStore.warehouses)
const products = computed(() => adminStore.products)

const productFamilies = computed(() => {
  const set = new Set<string>()
  for (const p of products.value) {
    const fam = p.product_family
    if (fam) set.add(fam)
  }
  return Array.from(set).sort()
})

const hasActiveFilters = computed(
  () => !!planRunId.value || !!warehouseFilter.value || !!productFamilyFilter.value || breachOnly.value
)

function clearFilters() {
  planRunId.value = null
  warehouseFilter.value = ''
  productFamilyFilter.value = ''
  breachOnly.value = false
  search.value = ''
}

const displayRows = computed(() => {
  let list = breakdown.value
  const q = search.value.toLowerCase()
  if (q) list = list.filter((r) => r.sku.toLowerCase().includes(q) || r.warehouse_code.toLowerCase().includes(q))
  return list
})

async function load() {
  if (!planRunId.value) {
    breakdown.value = []
    return
  }
  loading.value = true
  try {
    breakdown.value = await store.fetchStockPositionBreakdown(planRunId.value, {
      warehouseCode: warehouseFilter.value || undefined,
      productFamily: productFamilyFilter.value || undefined,
      breachOnly: breachOnly.value,
    })
  } finally {
    loading.value = false
  }
}

function openDetail(row: StockPositionBreakdown) {
  detailRow.value = row
  rollingWeeks.value = []
  if (!planRunId.value) return
  layout.openRightPanel(`Stock position: ${row.sku} × ${row.warehouse_code}`)

  detailLoading.value = true
  store
    .fetchStockPositionRolling(planRunId.value, row.warehouse_code, row.sku, 12)
    .then((data) => {
      rollingWeeks.value = data
    })
    .finally(() => {
      detailLoading.value = false
    })
}

watch([planRunId, warehouseFilter, productFamilyFilter, breachOnly], load, { immediate: true })

onMounted(() => {
  store.fetchPlanRuns()
  adminStore.fetchProducts()
  adminStore.fetchWarehouses()
})
</script>

<style scoped>
.stock-position-detail {
  padding: 0.5rem 0;
  font-size: 0.875rem;
}
.stock-position-detail dl dt {
  font-weight: 500;
}
</style>
