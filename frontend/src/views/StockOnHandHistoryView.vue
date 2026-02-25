<template>
  <div class="page-content-inner">
    <h1 class="text-xl font-semibold text-slate-800 mb-1">Stock On Hand History</h1>
    <p class="muted mb-6">View on-hand units trend by week from imported SOH data (AAH/BLP). Uses W-TUE week bucketing.</p>

    <section class="content-section controls">
      <div class="form-row">
        <label class="form-label">Warehouse</label>
        <select v-model="warehouseCode" class="app-select" style="max-width: 14rem;">
          <option v-for="code in warehouseOptions" :key="code" :value="code">{{ code }}</option>
        </select>
      </div>
      <div class="form-row">
        <label class="form-label">SKU</label>
        <select v-model="selectedSku" class="app-select" style="max-width: 20rem;">
          <option value="">Select SKU…</option>
          <option v-for="p in filteredProducts" :key="p.id" :value="p.sku">{{ p.sku }} – {{ p.name || '—' }}</option>
        </select>
        <input
          v-model="skuSearch"
          type="text"
          class="app-input ml-2"
          placeholder="Search SKU…"
          style="max-width: 12rem;"
        />
      </div>
      <div class="form-row">
        <label class="form-label">Week range</label>
        <input v-model="weekFrom" type="date" class="app-input" style="max-width: 10rem;" />
        <span class="mx-2">to</span>
        <input v-model="weekTo" type="date" class="app-input" style="max-width: 10rem;" />
      </div>
      <div class="form-row">
        <button
          type="button"
          class="app-btn app-btn-primary"
          :disabled="!selectedSku || loading"
          @click="loadSeries"
        >
          {{ loading ? 'Loading…' : 'Load history' }}
        </button>
      </div>
    </section>

    <section v-if="loaded" class="content-section">
      <h2>On-hand trend</h2>
      <p v-if="!series.length" class="muted">No history for this SKU/warehouse/date range.</p>
      <template v-else>
        <div class="chart-wrap mb-4">
          <canvas ref="chartCanvas"></canvas>
        </div>
        <div class="app-table-wrap">
          <table class="app-table">
            <thead>
              <tr>
                <th>Week start</th>
                <th>On-hand units</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in series" :key="r.week_start">
                <td>{{ r.week_start }}</td>
                <td>{{ r.on_hand_units }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { Chart, registerables } from 'chart.js'
import api from '@/api/client'
import { useAdminStore } from '@/stores/admin'

Chart.register(...registerables)

const adminStore = useAdminStore()
const warehouseOptions = computed(() => {
  const codes = new Set<string>(['AAH'])
  adminStore.warehouses.forEach((w) => codes.add(w.code))
  return Array.from(codes).sort()
})
const products = computed(() => adminStore.products)

const warehouseCode = ref('AAH')
const selectedSku = ref('')
const skuSearch = ref('')
const weekFrom = ref('')
const weekTo = ref('')
const series = ref<Array<{ week_start: string; on_hand_units: number; on_order_units?: number | null }>>([])
const loading = ref(false)
const loaded = ref(false)
const chartCanvas = ref<HTMLCanvasElement | null>(null)
let chartInstance: Chart | null = null

const filteredProducts = computed(() => {
  const q = skuSearch.value.toLowerCase().trim()
  if (!q) return products.value.slice(0, 200)
  return products.value.filter(
    (p) =>
      p.sku.toLowerCase().includes(q) ||
      (p.name ?? '').toLowerCase().includes(q)
  ).slice(0, 200)
})

async function loadSeries() {
  if (!selectedSku.value) return
  loading.value = true
  loaded.value = false
  try {
    const params: Record<string, string> = {
      warehouse_code: warehouseCode.value,
      sku: selectedSku.value,
    }
    if (weekFrom.value) params.week_start_from = weekFrom.value
    if (weekTo.value) params.week_start_to = weekTo.value
    const { data } = await api.get<typeof series.value>('/v1/reports/stock-on-hand/series', { params })
    series.value = data
    loaded.value = true
    updateChart()
  } finally {
    loading.value = false
  }
}

function updateChart() {
  if (!chartCanvas.value || !series.value.length) {
    if (chartInstance) {
      chartInstance.destroy()
      chartInstance = null
    }
    return
  }
  if (chartInstance) chartInstance.destroy()
  chartInstance = new Chart(chartCanvas.value, {
    type: 'line',
    data: {
      labels: series.value.map((r) => r.week_start),
      datasets: [
        {
          label: 'On-hand units',
          data: series.value.map((r) => r.on_hand_units),
          borderColor: 'rgb(37, 99, 235)',
          backgroundColor: 'rgba(37, 99, 235, 0.1)',
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'top' } },
      scales: {
        y: { beginAtZero: true },
        x: { title: { display: true, text: 'Week start (W-TUE)' } },
      },
    },
  })
}

watch(series, () => updateChart(), { deep: true })

onMounted(async () => {
  await Promise.all([adminStore.fetchProducts(), adminStore.fetchWarehouses()])
})
</script>

<style scoped>
.chart-wrap {
  height: 300px;
  position: relative;
}
.controls .form-row {
  margin-bottom: 0.75rem;
}
.form-label {
  display: inline-block;
  min-width: 7rem;
  margin-right: 0.5rem;
}
</style>
