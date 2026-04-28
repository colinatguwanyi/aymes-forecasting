<template>
  <div class="page-shell workflow-hub space-y-6">
    <header class="page-header workflow-hub__header">
      <div>
        <h1>Data</h1>
        <p class="muted mt-1">Load, check and fix the data that feeds forecasting and planning.</p>
      </div>
      <button type="button" class="btn-secondary" :disabled="loadOperation.isRunning.value" @click="loadHub">
        Refresh
      </button>
    </header>

    <OperationStatusPanel :operation="loadOperation.operation" />

    <section class="workflow-summary-grid" aria-label="Data summary">
      <article class="workflow-summary-card" :class="health?.ready_to_plan ? 'is-ok' : 'is-warn'">
        <span class="workflow-summary-card__label">Planning readiness</span>
        <strong>{{ health?.ready_to_plan ? 'Ready' : health ? 'Needs attention' : 'Loading' }}</strong>
        <p>Demand-only: {{ health?.ready_for_demand_only ? 'ready' : 'not ready' }}</p>
      </article>
      <article class="workflow-summary-card">
        <span class="workflow-summary-card__label">Products</span>
        <strong>{{ formatInt(health?.products?.active ?? 0) }}</strong>
        <p>{{ formatInt(health?.products?.count ?? 0) }} total products</p>
      </article>
      <article class="workflow-summary-card">
        <span class="workflow-summary-card__label">Latest demand</span>
        <strong>{{ health?.demand?.latest_week ?? 'No data' }}</strong>
        <p>{{ formatInt(health?.demand?.skus_with_demand ?? 0) }} SKUs · {{ formatInt(health?.demand?.weeks_available ?? 0) }} weeks</p>
      </article>
      <article class="workflow-summary-card">
        <span class="workflow-summary-card__label">Latest stock</span>
        <strong>{{ health?.soh?.latest_week ?? 'No data' }}</strong>
        <p>{{ formatInt(health?.soh?.skus_with_stock ?? 0) }} SKUs with stock</p>
      </article>
      <article class="workflow-summary-card">
        <span class="workflow-summary-card__label">Recent imports</span>
        <strong>{{ formatInt(importRuns.length) }}</strong>
        <p>{{ latestImportLabel }}</p>
      </article>
    </section>

    <section class="workflow-card-grid" aria-label="Data actions">
      <router-link v-for="action in actions" :key="action.to" :to="action.to" class="workflow-action-card">
        <h2>{{ action.title }}</h2>
        <p>{{ action.description }}</p>
        <span>{{ action.cta }}</span>
      </router-link>
    </section>

    <section class="card card-body">
      <div class="flex items-center justify-between gap-3 mb-3">
        <h2 class="section-title m-0">Recent import history</h2>
        <router-link to="/imports" class="btn-secondary text-sm">Open imports</router-link>
      </div>
      <div v-if="!importRuns.length" class="muted text-sm">No recent imports found.</div>
      <ul v-else class="workflow-list">
        <li v-for="run in importRuns.slice(0, 5)" :key="run.id">
          <span>
            <strong>{{ run.entity }}</strong>
            <small>{{ run.file_name || 'No file name' }}</small>
          </span>
          <span :class="statusBadgeClass(run.status)">{{ run.status }}</span>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import api from '@/api/client'
import OperationStatusPanel from '@/components/common/OperationStatusPanel.vue'
import { useOperation } from '@/composables/useOperation'

interface DataHealth {
  products: { count: number; active: number }
  demand: { latest_week: string | null; weeks_available: number; skus_with_demand: number }
  soh: { latest_week: string | null; skus_with_stock: number }
  planning_policies: { count: number; required_approx: number }
  ready_to_plan: boolean
  ready_for_demand_only?: boolean
}

interface ImportRun {
  id: string
  entity: string
  file_name: string | null
  status: string
  started_at: string | null
}

const health = ref<DataHealth | null>(null)
const importRuns = ref<ImportRun[]>([])
const loadOperation = useOperation('Load data hub')

const actions = [
  { to: '/imports', title: 'Import data', description: 'Upload product, sales, stock and demand files.', cta: 'Open imports' },
  { to: '/imports/rejections', title: 'Fix rejected rows', description: 'Review rejected import rows and missing product mappings.', cta: 'Open rejections' },
  { to: '/reports/data-health', title: 'Check data health', description: 'See readiness, coverage gaps and SKU diagnostics.', cta: 'Open data health' },
  { to: '/reports/sales-grid', title: 'Review sales data', description: 'Inspect weekly demand loaded into the platform.', cta: 'Open sales grid' },
  { to: '/reports/stock-on-hand-grid', title: 'Review SOH data', description: 'Inspect stock on hand by product and week.', cta: 'Open SOH grid' },
  { to: '/reports/stock-coverage', title: 'Check stock coverage', description: 'Compare on-hand stock to average weekly demand.', cta: 'Open coverage' },
]

const latestImportLabel = computed(() => {
  const latest = importRuns.value[0]?.started_at
  return latest ? `Latest ${formatDateTime(latest)}` : 'No import timestamp'
})

function formatInt(value: number): string {
  return Number.isFinite(value) ? value.toLocaleString() : String(value)
}

function formatDateTime(value: string): string {
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function statusBadgeClass(status: string): string {
  const s = status.toLowerCase()
  if (s === 'success') return 'badge-success'
  if (s === 'failed') return 'badge-danger'
  if (s === 'pending') return 'badge-warn'
  return 'badge-info'
}

async function loadHub(): Promise<void> {
  await loadOperation.runWithOperation(
    'Load data hub',
    async () => {
      const [healthRes, runsRes] = await Promise.all([
        api.get<DataHealth>('/v1/reports/data-health'),
        api.get<ImportRun[]>('/ingestion/runs', { params: { limit: 20 } }),
      ])
      health.value = healthRes.data
      importRuns.value = Array.isArray(runsRes.data) ? runsRes.data : []
    },
    {
      runningMessage: 'Loading data status...',
      successMessage: 'Data status refreshed.',
    },
  )
}

onMounted(() => {
  void loadHub()
})
</script>

<style scoped>
.workflow-hub__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}
.workflow-summary-grid,
.workflow-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
  gap: 1rem;
}
.workflow-summary-card,
.workflow-action-card {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.75rem;
  background: white;
  padding: 1rem;
}
.workflow-summary-card {
  border-left: 4px solid rgb(148 163 184);
}
.workflow-summary-card.is-ok {
  border-left-color: rgb(34 197 94);
  background: rgb(240 253 244);
}
.workflow-summary-card.is-warn {
  border-left-color: rgb(234 179 8);
  background: rgb(254 252 232);
}
.workflow-summary-card__label {
  display: block;
  color: rgb(100 116 139);
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.workflow-summary-card strong {
  display: block;
  margin-top: 0.35rem;
  color: rgb(15 23 42);
  font-size: 1.25rem;
}
.workflow-summary-card p,
.workflow-action-card p {
  margin: 0.35rem 0 0;
  color: rgb(71 85 105);
  font-size: 0.875rem;
}
.workflow-action-card {
  color: inherit;
  text-decoration: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.workflow-action-card:hover {
  border-color: rgb(147 197 253);
  box-shadow: 0 8px 20px rgb(15 23 42 / 0.08);
}
.workflow-action-card h2 {
  margin: 0;
  color: rgb(15 23 42);
  font-size: 1rem;
  font-weight: 700;
}
.workflow-action-card span {
  display: inline-block;
  margin-top: 0.75rem;
  color: rgb(37 99 235);
  font-size: 0.875rem;
  font-weight: 600;
}
.workflow-list {
  margin: 0;
  padding: 0;
  list-style: none;
}
.workflow-list li {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.65rem 0;
  border-top: 1px solid rgb(226 232 240);
}
.workflow-list small {
  display: block;
  color: rgb(100 116 139);
}
</style>
