<template>
  <div class="inventory-projection">
    <h1>Inventory Projection</h1>
    <p class="muted">Table and chart by SKU/warehouse. Compare up to two scenarios.</p>

    <section class="card controls">
      <label>Scenario 1</label>
      <select v-model="runId1" class="select">
        <option :value="null">—</option>
        <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
      </select>
      <label>Scenario 2</label>
      <select v-model="runId2" class="select">
        <option :value="null">—</option>
        <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ r.scenario_name }} ({{ r.created_at }})</option>
      </select>
      <label>SKU filter</label>
      <input v-model="skuFilter" placeholder="SKU" class="input" />
      <label>Warehouse filter</label>
      <input v-model="whFilter" placeholder="Warehouse" class="input" />
    </section>

    <section v-if="loading" class="card">Loading...</section>
    <template v-else>
      <section class="card">
        <h2>Projected inventory (Scenario 1)</h2>
        <table v-if="data1.length" class="table">
          <thead>
            <tr>
              <th>Week start</th>
              <th>SKU</th>
              <th>Warehouse</th>
              <th>Projected qty</th>
              <th>Weeks of cover</th>
              <th>Stockout</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in data1" :key="`1-${r.id}`" :class="{ stockout: r.stockout }">
              <td>{{ r.week_start }}</td>
              <td>{{ r.sku }}</td>
              <td>{{ r.warehouse_code }}</td>
              <td>{{ r.projected_qty }}</td>
              <td>{{ r.weeks_of_cover ?? '—' }}</td>
              <td>{{ r.stockout ? 'Yes' : 'No' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted">No data. Select a scenario and run a plan if needed.</p>
      </section>

      <section class="card">
        <h2>Projected inventory (Scenario 2)</h2>
        <table v-if="data2.length" class="table">
          <thead>
            <tr>
              <th>Week start</th>
              <th>SKU</th>
              <th>Warehouse</th>
              <th>Projected qty</th>
              <th>Weeks of cover</th>
              <th>Stockout</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in data2" :key="`2-${r.id}`" :class="{ stockout: r.stockout }">
              <td>{{ r.week_start }}</td>
              <td>{{ r.sku }}</td>
              <td>{{ r.warehouse_code }}</td>
              <td>{{ r.projected_qty }}</td>
              <td>{{ r.weeks_of_cover ?? '—' }}</td>
              <td>{{ r.stockout ? 'Yes' : 'No' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted">No data.</p>
      </section>

      <section class="card chart-section">
        <h2>Projected qty over time (first SKU/WH in list)</h2>
        <div class="chart-container" ref="chartContainer">
          <canvas ref="chartCanvas"></canvas>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { usePlanningStore } from '@/stores/planning'
import type { ProjectedInventory } from '@/api/client'
import { Chart, registerables } from 'chart.js'

Chart.register(...registerables)

const store = usePlanningStore()
const loading = ref(true)
const runId1 = ref<number | null>(null)
const runId2 = ref<number | null>(null)
const skuFilter = ref('')
const whFilter = ref('')
const data1 = ref<ProjectedInventory[]>([])
const data2 = ref<ProjectedInventory[]>([])
const chartCanvas = ref<HTMLCanvasElement | null>(null)
const chartContainer = ref<HTMLDivElement | null>(null)
let chartInstance: Chart | null = null

const planRuns = computed(() => store.planRuns)

async function load() {
  if (runId1.value) {
    data1.value = await store.fetchProjectedInventory(
      runId1.value,
      skuFilter.value || undefined,
      whFilter.value || undefined
    )
  } else {
    data1.value = []
  }
  if (runId2.value) {
    data2.value = await store.fetchProjectedInventory(
      runId2.value,
      skuFilter.value || undefined,
      whFilter.value || undefined
    )
  } else {
    data2.value = []
  }
  updateChart()
}

function updateChart() {
  if (!chartCanvas.value) return
  const firstKey = (arr: ProjectedInventory[]) => {
    if (!arr.length) return null
    const r = arr[0]
    return `${r.sku}|${r.warehouse_code}`
  }
  const key1 = firstKey(data1.value)
  const key2 = firstKey(data2.value)
  const series1 = key1 ? data1.value.filter((p) => `${p.sku}|${p.warehouse_code}` === key1) : []
  const series2 = key2 ? data2.value.filter((p) => `${p.sku}|${p.warehouse_code}` === key2) : []

  if (chartInstance) chartInstance.destroy()
  chartInstance = new Chart(chartCanvas.value, {
    type: 'line',
    data: {
      labels: series1.length ? series1.map((p) => p.week_start) : series2.map((p) => p.week_start),
      datasets: [
        { label: 'Scenario 1', data: series1.map((p) => parseFloat(p.projected_qty)), borderColor: '#58a6ff', fill: false },
        { label: 'Scenario 2', data: series2.map((p) => parseFloat(p.projected_qty)), borderColor: '#3fb950', fill: false },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: 'top' } },
      scales: { y: { beginAtZero: true } },
    },
  })
}

watch([runId1, runId2, skuFilter, whFilter], load)
onMounted(async () => {
  await store.fetchPlanRuns()
  if (store.planRuns.length) runId1.value = store.planRuns[0].id
  loading.value = false
  await load()
})
</script>

<style scoped>
.inventory-projection { display: flex; flex-direction: column; gap: 1rem; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 1rem; }
.card h2 { margin: 0 0 0.5rem 0; font-size: 1rem; }
.controls { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; }
.controls label { margin-right: 0.25rem; }
.select, .input { padding: 0.35rem 0.5rem; border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg); color: var(--text); }
.table { width: 100%; border-collapse: collapse; }
.table th, .table td { text-align: left; padding: 0.5rem; border-bottom: 1px solid var(--border); }
.table tr.stockout { background: rgba(248, 81, 73, 0.15); }
.muted { color: var(--muted); margin: 0.5rem 0; }
.chart-container { max-width: 800px; height: 300px; }
</style>
