<template>
  <div class="page-content-inner">
    <h1 class="text-xl font-semibold text-slate-800 mb-1">Getting Started</h1>
    <p class="muted mb-6">Follow these 5 steps to load data and run your first plan. Sales Out is the default demand path.</p>

    <section v-if="loading" class="content-section">Loading...</section>
    <template v-else>
      <div class="setup-steps space-y-4">
        <!-- Step 1: Product Master -->
        <div class="setup-step" :class="step1Ok ? 'step-ok' : 'step-fail'">
          <div class="step-header">
            <span class="step-icon">{{ step1Ok ? '✓' : '○' }}</span>
            <span class="step-title">Step 1 — Product Master</span>
            <span class="step-status">{{ step1Ok ? `${productsCount} products` : 'No products' }}</span>
          </div>
          <p class="step-desc">Import products from Product Master CSV (Imports → Entity: Product Master).</p>
          <router-link to="/imports" class="app-btn app-btn-secondary text-sm">Go to Imports</router-link>
        </div>

        <!-- Step 2: Planning Policies -->
        <div class="setup-step" :class="step2Status">
          <div class="step-header">
            <span class="step-icon">{{ step2Icon }}</span>
            <span class="step-title">Step 2 — Planning Policies</span>
            <span class="step-status">{{ policiesCount }} policies (need ~{{ productsCount * warehousesCount }})</span>
          </div>
          <p class="step-desc">Create policies per SKU × warehouse. Use "Generate Default Policies for AAH" on the Policies page for quick setup.</p>
          <router-link to="/admin/policies" class="app-btn app-btn-secondary text-sm">Go to Policies</router-link>
        </div>

        <!-- Step 3: Sales Data -->
        <div class="setup-step" :class="step3Ok ? 'step-ok' : 'step-fail'">
          <div class="step-header">
            <span class="step-icon">{{ step3Ok ? '✓' : '○' }}</span>
            <span class="step-title">Step 3 — Sales Data (Default Path)</span>
            <span class="step-status">{{ step3Ok ? `Latest: ${demandLatestWeek}` : 'No demand' }}</span>
          </div>
          <p class="step-desc">Upload Sales Out CSV (Imports → Sales Out). Writes to demand_actuals (CUSTOMER, AAH).</p>
          <router-link to="/imports" class="app-btn app-btn-secondary text-sm">Go to Sales Out</router-link>
        </div>

        <!-- Step 4: Stock On Hand -->
        <div class="setup-step" :class="step4Ok ? 'step-ok' : 'step-fail'">
          <div class="step-header">
            <span class="step-icon">{{ step4Ok ? '✓' : '○' }}</span>
            <span class="step-title">Step 4 — Stock On Hand</span>
            <span class="step-status">{{ step4Ok ? `Latest: ${sohLatestWeek}` : 'No SOH' }}</span>
          </div>
          <p class="step-desc">Upload SOH CSV (Imports → Stock On Hand).</p>
          <router-link to="/imports" class="app-btn app-btn-secondary text-sm">Go to SOH</router-link>
        </div>

        <!-- Step 5: Ready to Plan -->
        <div class="setup-step" :class="readyToPlan ? 'step-ok step-ready' : 'step-fail'">
          <div class="step-header">
            <span class="step-icon">{{ readyToPlan ? '✓' : '○' }}</span>
            <span class="step-title">Step 5 — Ready to Plan</span>
          </div>
          <p v-if="readyToPlan" class="step-ready-msg">All data loaded. Run your first plan.</p>
          <p v-else class="step-blocked">Complete steps 1–4 above.</p>
          <router-link to="/" class="app-btn app-btn-primary" :class="{ 'opacity-50': !readyToPlan }">
            Go to Dashboard
          </router-link>
        </div>
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
  planning_policies: { count: number; required_approx: number }
  warehouses_count: number
  ready_to_plan: boolean
}

const loading = ref(true)
const health = ref<DataHealth | null>(null)

const productsCount = computed(() => health.value?.products?.count ?? 0)
const policiesCount = computed(() => health.value?.planning_policies?.count ?? 0)
const warehousesCount = computed(() => Math.max(1, health.value?.warehouses_count ?? 1))
const demandLatestWeek = computed(() => health.value?.demand?.latest_week ?? '—')
const sohLatestWeek = computed(() => health.value?.soh?.latest_week ?? '—')

const step1Ok = computed(() => productsCount.value > 0)
const step2Status = computed(() => {
  const need = productsCount.value * warehousesCount.value
  if (policiesCount.value >= need) return 'step-ok'
  if (policiesCount.value > 0) return 'step-warn'
  return 'step-fail'
})
const step2Icon = computed(() => {
  const s = step2Status.value
  return s === 'step-ok' ? '✓' : s === 'step-warn' ? '!' : '○'
})
const step3Ok = computed(() => !!health.value?.demand?.latest_week)
const step4Ok = computed(() => !!health.value?.soh?.latest_week)
const readyToPlan = computed(() => !!health.value?.ready_to_plan)

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
.setup-steps {
  max-width: 36rem;
}
.setup-step {
  padding: 1rem 1.25rem;
  border-radius: 0.5rem;
  border: 1px solid rgb(226 232 240);
  background: white;
}
.setup-step.step-ok {
  border-left: 4px solid rgb(34 197 94);
  background: rgb(240 253 244);
}
.setup-step.step-warn {
  border-left: 4px solid rgb(234 179 8);
  background: rgb(254 252 232);
}
.setup-step.step-fail {
  border-left: 4px solid rgb(239 68 68);
  background: rgb(254 242 242);
}
.setup-step.step-ready {
  font-weight: 500;
}
.step-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}
.step-icon {
  font-size: 1.25rem;
  font-weight: bold;
}
.step-title {
  font-weight: 600;
  color: rgb(30 41 59);
}
.step-status {
  margin-left: auto;
  font-size: 0.875rem;
  color: rgb(100 116 139);
}
.step-desc {
  font-size: 0.875rem;
  color: rgb(71 85 105);
  margin-bottom: 0.75rem;
}
.step-ready-msg {
  font-size: 1rem;
  color: rgb(22 101 52);
  margin-bottom: 0.75rem;
}
.step-blocked {
  font-size: 0.875rem;
  color: rgb(100 116 139);
  margin-bottom: 0.75rem;
}
</style>
