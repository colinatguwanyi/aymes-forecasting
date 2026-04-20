<template>
  <div class="space-y-6">
    <PageHeader title="Timelines" :breadcrumbs="[{ label: 'Admin', path: '/admin/timelines' }]" />

    <FilterBar v-model="search" search-placeholder="Filter by SKU or warehouse…" :has-active-filters="!!selectedSku || !!selectedWarehouse || !!selectedPlanRunId" @clear="selectedSku = ''; selectedWarehouse = ''; selectedPlanRunId = null; search = ''">
      <template #filters>
        <select v-model="selectedSku" class="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white min-w-48">
          <option value="">Select SKU</option>
          <option v-for="p in products" :key="p.id" :value="p.sku">{{ p.sku }} – {{ p.name ?? '' }}</option>
        </select>
        <select v-model="selectedWarehouse" class="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white min-w-40">
          <option value="">Select warehouse</option>
          <option v-for="w in warehouses" :key="w.id" :value="w.code">{{ w.code }} – {{ w.name ?? '' }}</option>
        </select>
        <select v-model="selectedPlanRunId" class="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white min-w-48">
          <option :value="null">No plan run</option>
          <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }}</option>
        </select>
      </template>
    </FilterBar>

    <template v-if="!selectedSku || !selectedWarehouse">
      <p class="text-sm text-neutral-500 py-8">Select SKU and Warehouse to view the timeline.</p>
    </template>

    <template v-else>
      <div v-if="loading" class="text-sm text-neutral-500 py-8">Loading timeline…</div>

      <template v-else-if="timeline">
        <div class="rounded-lg border border-neutral-200 bg-white p-6">
          <h2 class="text-base font-semibold text-neutral-900 mb-4">Lead time & markers</h2>
          <TimelineBar
            :week-labels="timeline.week_labels"
            :segments="timeline.segments"
            :markers="timeline.markers"
          />
        </div>

        <div class="rounded-lg border border-neutral-200 bg-white overflow-hidden">
          <h2 class="px-4 py-3 text-base font-semibold text-neutral-900 border-b border-neutral-200">Receipts by week</h2>
          <div class="overflow-x-auto max-h-[40vh] overflow-y-auto">
            <table class="w-full text-sm border-collapse">
              <thead class="sticky top-0 bg-neutral-50 border-b border-neutral-200">
                <tr>
                  <th class="px-3 py-2 text-left font-medium text-neutral-600">Week start</th>
                  <th class="px-3 py-2 text-right font-medium text-neutral-600">Qty</th>
                  <th class="px-3 py-2 text-left font-medium text-neutral-600">On time</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in timeline.receipts" :key="r.week_start" class="border-b border-neutral-100 hover:bg-neutral-50">
                  <td class="px-3 py-2">{{ r.week_start }}</td>
                  <td class="px-3 py-2 text-right">{{ r.qty }}</td>
                  <td class="px-3 py-2">{{ r.on_time ? 'Yes' : 'No' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="!timeline.receipts.length" class="px-4 py-8 text-sm text-neutral-500">No receipts in horizon.</p>
        </div>
      </template>

      <p v-else-if="error" class="text-sm text-red-600 py-4">{{ error }}</p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import api from '@/api/client'
import type { TimelineResponse } from '@/api/client'
import { useAdminStore } from '@/stores/admin'
import { usePlanningStore } from '@/stores/planning'
import PageHeader from '@/components/console/PageHeader.vue'
import FilterBar from '@/components/console/FilterBar.vue'
import TimelineBar from '@/components/TimelineBar.vue'

const adminStore = useAdminStore()
const planningStore = usePlanningStore()

const search = ref('')
const selectedSku = ref('')
const selectedWarehouse = ref('')
const selectedPlanRunId = ref<number | null>(null)

const loading = ref(false)
const timeline = ref<TimelineResponse | null>(null)
const error = ref<string | null>(null)

const products = computed(() => adminStore.products)
const warehouses = computed(() => adminStore.warehouses)
const planRuns = computed(() => planningStore.planRuns)

async function fetchTimeline() {
  if (!selectedSku.value || !selectedWarehouse.value) {
    timeline.value = null
    return
  }
  loading.value = true
  error.value = null
  try {
    const params = new URLSearchParams({
      sku: selectedSku.value,
      warehouse_code: selectedWarehouse.value,
      horizon_weeks: '52',
    })
    if (selectedPlanRunId.value != null) params.set('plan_run_id', String(selectedPlanRunId.value))
    const { data } = await api.get<TimelineResponse>(`/timeline?${params}`)
    timeline.value = data
  } catch (e: unknown) {
    const msg = e && typeof e === 'object' && 'message' in e ? String((e as { message: string }).message) : 'Failed to load timeline'
    error.value = msg
    timeline.value = null
  } finally {
    loading.value = false
  }
}

watch([selectedSku, selectedWarehouse, selectedPlanRunId], () => {
  fetchTimeline()
}, { immediate: false })

onMounted(async () => {
  await Promise.all([
    adminStore.fetchProducts(),
    adminStore.fetchWarehouses(),
    planningStore.fetchPlanRuns(),
  ])
  if (selectedSku.value && selectedWarehouse.value) fetchTimeline()
})
</script>
