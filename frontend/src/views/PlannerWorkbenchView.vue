<template>
  <div class="page-shell workflow-hub space-y-6">
    <header class="page-header workflow-hub__header">
      <div>
        <h1>Planner Workbench</h1>
        <p class="muted mt-1">Review plans, exceptions, projections and exports from one workflow entry point.</p>
      </div>
      <button type="button" class="btn-secondary" :disabled="loadOperation.isRunning.value" @click="loadHub">
        Refresh
      </button>
    </header>

    <OperationStatusPanel :operation="loadOperation.operation" />

    <section class="workflow-summary-grid" aria-label="Planner summary">
      <article class="workflow-summary-card" :class="readyCount > 0 ? 'is-ok' : 'is-warn'">
        <span class="workflow-summary-card__label">Ready locations</span>
        <strong>{{ readyCount }} / {{ readiness.length }}</strong>
        <p>Stock-aware readiness by location</p>
      </article>
      <article class="workflow-summary-card">
        <span class="workflow-summary-card__label">Planning runs</span>
        <strong>{{ formatInt(planRuns.length) }}</strong>
        <p>{{ latestPlanRunLabel }}</p>
      </article>
      <article class="workflow-summary-card" :class="health?.ready_for_demand_only ? 'is-ok' : 'is-warn'">
        <span class="workflow-summary-card__label">Demand-only planning</span>
        <strong>{{ health?.ready_for_demand_only ? 'Ready' : 'Not ready' }}</strong>
        <p>Useful when physical SOH is incomplete</p>
      </article>
      <article class="workflow-summary-card" :class="health?.ready_to_plan ? 'is-ok' : 'is-warn'">
        <span class="workflow-summary-card__label">Stock-aware planning</span>
        <strong>{{ health?.ready_to_plan ? 'Ready' : 'Needs setup' }}</strong>
        <p>Requires products, demand, SOH and policies</p>
      </article>
    </section>

    <section class="workflow-card-grid" aria-label="Workbench actions">
      <router-link v-for="action in actions" :key="action.to" :to="action.to" class="workflow-action-card">
        <h2>{{ action.title }}</h2>
        <p>{{ action.description }}</p>
        <span>{{ action.cta }}</span>
      </router-link>
    </section>

    <section class="card card-body">
      <div class="flex items-center justify-between gap-3 mb-3">
        <h2 class="section-title m-0">Latest plan runs</h2>
        <router-link to="/" class="btn-secondary text-sm">Start planning</router-link>
      </div>
      <div v-if="!planRuns.length" class="muted text-sm">No plan runs yet.</div>
      <ul v-else class="workflow-list">
        <li v-for="run in planRuns.slice(0, 5)" :key="run.id">
          <span>
            <strong>{{ formatPlanRunLabel(run) }}</strong>
            <small>{{ run.created_at }} · {{ planRunMode(run) }}</small>
          </span>
          <span class="workflow-list__actions">
            <router-link :to="{ path: '/planning-grid', query: { plan_run_id: String(run.id) } }">Grid</router-link>
            <router-link :to="{ path: '/inventory-projection', query: { plan_run_id: String(run.id) } }">Projection</router-link>
          </span>
        </li>
      </ul>
    </section>

    <section class="card card-body">
      <h2 class="section-title m-0 mb-3">Location readiness</h2>
      <div v-if="!readiness.length" class="muted text-sm">No readiness rows returned yet.</div>
      <ul v-else class="workflow-list">
        <li v-for="row in readiness" :key="row.warehouse_code">
          <span>
            <strong>{{ row.warehouse_code }}</strong>
            <small>{{ row.blockers.length ? row.blockers.join(', ') : 'No blockers' }}</small>
          </span>
          <span :class="row.ready ? 'badge-success' : 'badge-warn'">{{ row.ready ? 'Ready' : 'Not ready' }}</span>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import api, {
  formatPlanRunLabel,
  planRunPlanningMode,
  type PlanRun,
  type WarehouseReadinessItem,
} from '@/api/client'
import OperationStatusPanel from '@/components/common/OperationStatusPanel.vue'
import { useOperation } from '@/composables/useOperation'

interface DataHealth {
  ready_to_plan: boolean
  ready_for_demand_only?: boolean
}

const health = ref<DataHealth | null>(null)
const planRuns = ref<PlanRun[]>([])
const readiness = ref<WarehouseReadinessItem[]>([])
const loadOperation = useOperation('Load planner workbench')

const actions = [
  { to: '/', title: 'Start planning', description: 'Create a planning run using readiness-aware options.', cta: 'Open launchpad' },
  { to: '/planning-grid', title: 'Weekly planning grid', description: 'Review SKU-week plans and planner actions.', cta: 'Open grid' },
  { to: '/exceptions', title: 'Exceptions', description: 'Focus on stockouts, low cover and other items needing attention.', cta: 'Open exceptions' },
  { to: '/inventory-projection', title: 'Inventory projection', description: 'Review projected inventory for a selected plan run.', cta: 'Open projection' },
  { to: '/stock-position', title: 'Stock position', description: 'Understand current stock and coverage by product/location.', cta: 'Open stock position' },
  { to: '/planned-orders', title: 'Planned orders', description: 'Review generated replenishment recommendations.', cta: 'Open orders' },
  { to: '/sku-detail', title: 'SKU detail', description: 'Drill into one SKU for history, explanation and timeline context.', cta: 'Open SKU detail' },
  { to: '/exports', title: 'Planning exports', description: 'Download projected inventory, planned orders and exception reports.', cta: 'Open exports' },
]

const readyCount = computed(() => readiness.value.filter((row) => row.ready).length)
const latestPlanRunLabel = computed(() => planRuns.value[0] ? formatPlanRunLabel(planRuns.value[0]) : 'No planning runs')

function formatInt(value: number): string {
  return Number.isFinite(value) ? value.toLocaleString() : String(value)
}

function planRunMode(run: PlanRun): string {
  return planRunPlanningMode(run) === 'demand_only' ? 'Demand-only' : 'Stock-aware'
}

async function loadHub(): Promise<void> {
  await loadOperation.runWithOperation(
    'Load planner workbench',
    async () => {
      const [healthRes, runsRes, readinessRes] = await Promise.allSettled([
        api.get<DataHealth>('/v1/reports/data-health', { timeout: 10_000 }),
        api.get<PlanRun[]>('/plan/runs', { timeout: 10_000 }),
        api.get<WarehouseReadinessItem[]>('/v1/diagnostics/warehouse-readiness', {
          params: { demand_source: 'actuals', planning_mode: 'stock_aware' },
          timeout: 10_000,
        }),
      ])
      health.value = healthRes.status === 'fulfilled' ? healthRes.value.data : null
      planRuns.value = runsRes.status === 'fulfilled' && Array.isArray(runsRes.value.data) ? runsRes.value.data : []
      readiness.value = readinessRes.status === 'fulfilled' && Array.isArray(readinessRes.value.data) ? readinessRes.value.data : []
    },
    {
      timeoutMs: 15_000,
      runningMessage: 'Loading planner status...',
      successMessage: 'Planner Workbench refreshed.',
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
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
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
.workflow-list__actions {
  display: inline-flex;
  gap: 0.75rem;
  font-size: 0.875rem;
  font-weight: 600;
}
</style>
