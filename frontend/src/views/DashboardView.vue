<template>
  <div class="page-content-inner">
    <p class="muted">Stockout risk next 8 / 13 weeks and top SKUs by risk.</p>

    <section v-if="loading" class="content-section">Loading...</section>
    <template v-else>
      <section class="content-section">
        <h2>Run a scenario</h2>
        <form @submit.prevent="runScenario" class="form-inline">
          <input v-model="scenarioName" class="app-input" placeholder="Scenario name" required style="max-width: 12rem;" />
          <button type="submit" class="app-btn app-btn-primary">Run plan</button>
        </form>
      </section>

      <section class="content-section">
        <h2>Stockout risk (next 8 weeks)</h2>
        <p v-if="!selectedRunId" class="muted">Select a scenario below to see risk.</p>
        <div v-else class="risk-summary">
          <p>Stockouts: {{ stockoutCount8 }}</p>
          <p>SKU/Warehouse combinations at risk: {{ atRiskSkus8.length }}</p>
        </div>
      </section>

      <section class="content-section">
        <h2>Stockout risk (next 13 weeks)</h2>
        <p v-if="!selectedRunId" class="muted">Select a scenario below.</p>
        <div v-else class="risk-summary">
          <p>Stockouts: {{ stockoutCount13 }}</p>
          <p>SKU/Warehouse at risk: {{ atRiskSkus13.length }}</p>
        </div>
      </section>

      <section class="content-section">
        <h2>Top SKUs by risk</h2>
        <select v-model="selectedRunId" class="app-select" style="max-width: 20rem; margin-bottom: 0.5rem;">
          <option :value="null">Select scenario</option>
          <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
        </select>
        <div v-if="selectedRunId && topRisks.length" class="app-table-wrap">
          <table class="app-table">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Warehouse</th>
                <th>Weeks at risk</th>
                <th>Min weeks of cover</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in topRisks" :key="i">
                <td>{{ row.sku }}</td>
                <td>{{ row.warehouse_code }}</td>
                <td>{{ row.stockoutWeeks }}</td>
                <td>{{ row.minWoc }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else-if="selectedRunId && !topRisks.length" class="muted">No stockout risk in projection.</p>
      </section>

      <section class="content-section">
        <h2>Plan runs</h2>
        <div class="app-table-wrap">
          <table class="app-table">
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Run at</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in planRuns" :key="r.id">
                <td>{{ r.scenario_name }}</td>
                <td>{{ r.run_at }}</td>
                <td>{{ r.created_at }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { usePlanningStore } from '@/stores/planning'
import type { ProjectedInventory } from '@/api/client'

const store = usePlanningStore()
const loading = ref(true)
const scenarioName = ref('baseline')
const selectedRunId = ref<number | null>(null)

const planRuns = computed(() => store.planRuns)

const projected = ref<ProjectedInventory[]>([])
const weeks8 = 8
const weeks13 = 13

const distinctWeeks = computed(() => {
  const set = new Set(projected.value.map((p) => p.week_start))
  return Array.from(set).sort()
})
const first8Weeks = computed(() => distinctWeeks.value.slice(0, weeks8))
const first13Weeks = computed(() => distinctWeeks.value.slice(0, weeks13))

const stockoutCount8 = computed(() =>
  projected.value.filter((p) => p.stockout && first8Weeks.value.includes(p.week_start)).length
)
const stockoutCount13 = computed(() =>
  projected.value.filter((p) => p.stockout && first13Weeks.value.includes(p.week_start)).length
)

const atRiskSkus8 = computed(() => {
  const set = new Set<string>()
  projected.value
    .filter((p) => p.stockout && first8Weeks.value.includes(p.week_start))
    .forEach((p) => set.add(`${p.sku}|${p.warehouse_code}`))
  return Array.from(set)
})
const atRiskSkus13 = computed(() => {
  const set = new Set<string>()
  projected.value
    .filter((p) => p.stockout && first13Weeks.value.includes(p.week_start))
    .forEach((p) => set.add(`${p.sku}|${p.warehouse_code}`))
  return Array.from(set)
})

const topRisks = computed(() => {
  const byKey: Record<string, { sku: string; warehouse_code: string; stockoutWeeks: number; minWoc: number }> = {}
  for (const p of projected.value) {
    const key = `${p.sku}|${p.warehouse_code}`
    if (!byKey[key]) {
      byKey[key] = { sku: p.sku, warehouse_code: p.warehouse_code, stockoutWeeks: 0, minWoc: 999 }
    }
    if (p.stockout) byKey[key].stockoutWeeks++
    const woc = p.weeks_of_cover ? parseFloat(p.weeks_of_cover) : 999
    if (woc < byKey[key].minWoc) byKey[key].minWoc = woc
  }
  return Object.values(byKey)
    .filter((x) => x.stockoutWeeks > 0)
    .sort((a, b) => b.stockoutWeeks - a.stockoutWeeks)
    .slice(0, 20)
})

async function runScenario() {
  await store.runPlan(scenarioName.value)
  await store.fetchPlanRuns()
  if (store.planRuns.length) selectedRunId.value = store.planRuns[0].id
}

onMounted(async () => {
  await store.fetchPlanRuns()
  if (store.planRuns.length) selectedRunId.value = store.planRuns[0].id
  loading.value = false
})

watch(selectedRunId, async (id) => {
  if (id) {
    projected.value = await store.fetchProjectedInventory(id)
  } else {
    projected.value = []
  }
}, { immediate: true })
</script>

<style scoped>
.form-inline { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
.risk-summary p { margin: 0.25rem 0; font-size: 0.875rem; }
</style>
