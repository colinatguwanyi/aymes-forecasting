<template>
  <div class="page-content-inner">
    <h1 class="text-xl font-semibold text-slate-800 mb-1">Data Health</h1>
    <p class="muted mb-6">Readiness to run plan. Green = OK, Amber = warning, Red = blocking.</p>

    <section v-if="loading" class="content-section">Loading...</section>
    <template v-else>
      <div class="health-cards grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div class="health-card" :class="productsStatus">
          <h3 class="card-title">Products</h3>
          <p class="card-value">{{ health?.products?.count ?? 0 }} total, {{ health?.products?.active ?? 0 }} active</p>
          <p v-if="(health?.products?.count ?? 0) === 0" class="card-warn">No products loaded</p>
        </div>
        <div class="health-card" :class="demandStatus">
          <h3 class="card-title">Demand (Sales Out)</h3>
          <p class="card-value">Latest: {{ health?.demand?.latest_week ?? '—' }}</p>
          <p class="card-meta">{{ health?.demand?.skus_with_demand ?? 0 }} SKUs, {{ health?.demand?.weeks_available ?? 0 }} weeks</p>
          <p v-if="!health?.demand?.latest_week" class="card-warn">No recent demand</p>
        </div>
        <div class="health-card" :class="sohStatus">
          <h3 class="card-title">Stock On Hand</h3>
          <p class="card-value">Latest: {{ health?.soh?.latest_week ?? '—' }}</p>
          <p class="card-meta">{{ health?.soh?.skus_with_stock ?? 0 }} SKUs with stock</p>
          <p v-if="!health?.soh?.latest_week" class="card-warn">No stock loaded</p>
        </div>
        <div class="health-card" :class="policiesStatus">
          <h3 class="card-title">Planning Policies</h3>
          <p class="card-value">{{ health?.planning_policies?.count ?? 0 }} policies</p>
          <p class="card-meta">~{{ health?.planning_policies?.required_approx ?? 0 }} needed (products × warehouses)</p>
        </div>
        <div class="health-card" :class="mappingStatus">
          <h3 class="card-title">BLP Mapping</h3>
          <p class="card-value">{{ health?.mapping?.warehouse_product_codes_count ?? 0 }} codes mapped</p>
          <p v-if="health?.mapping?.units_missing_pct != null && health.mapping.units_missing_pct > 0" class="card-warn">
            BLP mapping incomplete: {{ health.mapping.units_missing_pct }}% units missing
          </p>
        </div>
        <div class="health-card" :class="readyStatus">
          <h3 class="card-title">Ready to Plan</h3>
          <p class="card-value">{{ health?.ready_to_plan ? 'Yes' : 'No' }}</p>
          <p v-if="!health?.ready_to_plan" class="card-warn">Complete setup steps first</p>
        </div>
      </div>
      <div v-if="warnings.length" class="mt-6 p-4 rounded-lg bg-amber-50 border border-amber-200">
        <h3 class="font-semibold text-amber-800 mb-2">Warnings</h3>
        <ul class="list-disc list-inside text-amber-800 text-sm space-y-1">
          <li v-for="(w, i) in warnings" :key="i">{{ w }}</li>
        </ul>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '@/api/client'

interface DataHealth {
  products: { count: number; active: number }
  demand: { latest_week: string | null; weeks_available: number; skus_with_demand: number }
  soh: { latest_week: string | null; skus_with_stock: number }
  mapping: { blp_coverage_pct?: number; units_missing_pct?: number; warehouse_product_codes_count: number }
  planning_policies: { count: number; required_approx: number }
  ready_to_plan: boolean
}

const loading = ref(true)
const health = ref<DataHealth | null>(null)

const productsStatus = computed(() => ((health.value?.products?.count ?? 0) > 0 ? 'status-ok' : 'status-fail'))
const demandStatus = computed(() => (health.value?.demand?.latest_week ? 'status-ok' : 'status-fail'))
const sohStatus = computed(() => (health.value?.soh?.latest_week ? 'status-ok' : 'status-fail'))
const policiesStatus = computed(() => {
  const c = health.value?.planning_policies?.count ?? 0
  const r = health.value?.planning_policies?.required_approx ?? 0
  if (c >= r) return 'status-ok'
  if (c > 0) return 'status-warn'
  return 'status-fail'
})
const mappingStatus = computed(() => {
  const missing = health.value?.mapping?.units_missing_pct
  if (missing == null || missing === 0) return 'status-ok'
  if (missing < 20) return 'status-warn'
  return 'status-fail'
})
const readyStatus = computed(() => (health.value?.ready_to_plan ? 'status-ok' : 'status-fail'))

const warnings = computed(() => {
  const w: string[] = []
  if (!health.value?.demand?.latest_week) w.push('No recent demand — upload Sales Out')
  if (!health.value?.soh?.latest_week) w.push('No stock loaded — upload SOH')
  const missing = health.value?.mapping?.units_missing_pct
  if (missing != null && missing > 0) w.push(`BLP mapping incomplete: ${missing}% units missing`)
  return w
})

async function load() {
  loading.value = true
  try {
    const { data } = await api.get<DataHealth>('/v1/reports/data-health')
    health.value = data
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.health-cards {
  max-width: 48rem;
}
.health-card {
  padding: 1rem 1.25rem;
  border-radius: 0.5rem;
  border: 1px solid rgb(226 232 240);
  background: white;
}
.health-card.status-ok {
  border-left: 4px solid rgb(34 197 94);
  background: rgb(240 253 244);
}
.health-card.status-warn {
  border-left: 4px solid rgb(234 179 8);
  background: rgb(254 252 232);
}
.health-card.status-fail {
  border-left: 4px solid rgb(239 68 68);
  background: rgb(254 242 242);
}
.card-title {
  font-weight: 600;
  font-size: 0.875rem;
  color: rgb(30 41 59);
  margin-bottom: 0.25rem;
}
.card-value {
  font-size: 1rem;
  color: rgb(51 65 85);
}
.card-meta {
  font-size: 0.75rem;
  color: rgb(100 116 139);
  margin-top: 0.25rem;
}
.card-warn {
  font-size: 0.75rem;
  color: rgb(185 28 28);
  margin-top: 0.5rem;
}
</style>
