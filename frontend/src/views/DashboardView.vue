<template>
  <div class="page-content-inner dashboard-launchpad">
    <section v-if="loading" class="content-section">Loading…</section>

    <template v-else>
      <!-- 1. Start planning -->
      <section class="launch-card launch-card--primary">
        <h1 class="launch-card__h1">Start planning</h1>
        <p class="launch-card__lede">
          Choose <strong>mode</strong> and <strong>warehouse scope</strong>, then run. Per-warehouse readiness follows the mode you select.
        </p>

        <OperationStatusPanel :operation="runPlanOperation.operation" class="mb-4">
          <template #retry>
            <div class="run-feedback__links">
              <router-link to="/imports">Imports</router-link>
              <router-link to="/admin/policies">Policies</router-link>
              <router-link to="/reports/data-health">Diagnostics</router-link>
            </div>
          </template>
        </OperationStatusPanel>

        <div class="launch-field-group">
          <span class="form-label launch-label">Planning mode</span>
          <div class="launch-radio-row">
            <label class="launch-radio">
              <input v-model="planningMode" type="radio" value="stock_aware" />
              <span><strong>Stock-aware</strong> — uses SOH snapshots for physical-style projection.</span>
            </label>
            <label class="launch-radio">
              <input v-model="planningMode" type="radio" value="demand_only" />
              <span><strong>Demand-only</strong> — modeled position; no SOH required.</span>
            </label>
          </div>
        </div>

        <div class="launch-field-group">
          <span class="form-label launch-label">Warehouse scope</span>
          <div class="launch-radio-row launch-radio-row--compact">
            <label class="launch-radio launch-radio--inline">
              <input v-model="warehouseScope" type="radio" value="AAH" />
              <span>AAH</span>
              <span v-if="warehouseReadiness" class="launch-ready-pill" :class="readinessFor('AAH')?.ready ? 'is-yes' : 'is-no'">
                {{ readinessFor('AAH')?.ready ? 'Ready' : (readinessFor('AAH') ? 'Not ready' : '') }}
              </span>
            </label>
            <label class="launch-radio launch-radio--inline">
              <input v-model="warehouseScope" type="radio" value="BLP" />
              <span>BLP</span>
              <span v-if="warehouseReadiness" class="launch-ready-pill" :class="readinessFor('BLP')?.ready ? 'is-yes' : 'is-no'">
                {{ readinessFor('BLP')?.ready ? 'Ready' : (readinessFor('BLP') ? 'Not ready' : '') }}
              </span>
            </label>
            <label class="launch-radio launch-radio--inline">
              <input v-model="warehouseScope" type="radio" value="all_ready" />
              <span>All ready warehouses</span>
              <span v-if="warehouseReadiness" class="text-xs text-slate-500">({{ warehouseReadiness.filter(r => r.ready).length }} ready)</span>
            </label>
          </div>
        </div>

        <form class="launch-run-row" @submit.prevent="runScenario">
          <button
            type="submit"
            class="app-btn app-btn-primary launch-run-btn"
            :disabled="runPlanLoading || !readyToPlan"
            :title="readyToPlan ? 'Create a new plan run.' : 'Complete setup first.'"
          >
            {{ runPlanLoading ? 'Running…' : runPlanButtonLabel }}
          </button>
          <details class="launch-advanced">
            <summary>Advanced run options</summary>
            <div class="form-inline plan-run-form mt-2">
              <label class="form-label">Run name</label>
              <input v-model="runName" type="text" class="app-input" placeholder="e.g. Q1 baseline" style="max-width: 14rem;" />
              <label class="form-label">Scenario</label>
              <select v-model="scenarioName" class="app-select" required style="max-width: 12rem;">
                <option value="baseline">Baseline</option>
                <option value="blended">Blended</option>
                <option value="actuals">Actuals</option>
                <option value="Conservative">Conservative</option>
                <option value="Aggressive">Aggressive</option>
                <option value="Promo uplift">Promo uplift</option>
              </select>
              <label class="form-label">Demand source</label>
              <select v-model="demandSource" class="app-select" style="max-width: 14rem;">
                <option value="actuals">Actuals (Sales Out)</option>
                <option value="baseline">Baseline forecast</option>
                <option value="blended">Blended</option>
              </select>
              <label class="form-label">Freeze weeks</label>
              <input v-model.number="freezeWeeks" type="number" min="0" max="52" class="app-input" style="max-width: 4rem;" />
            </div>
          </details>
        </form>
        <p class="launch-hint text-xs text-slate-500">
          <router-link to="/reports/data-health" class="text-blue-600 hover:underline">Data Health</router-link>
          for full diagnostics ·
          <router-link to="/setup" class="text-blue-600 hover:underline">Setup</router-link>
        </p>
      </section>

      <!-- 3. Smart alert -->
      <section
        v-if="smartAlert && !dataHealthLoading && skuIntegrityLoaded"
        class="smart-alert"
        :class="`smart-alert--${smartAlert.severity}`"
        role="status"
      >
        <h2 class="smart-alert__title">{{ smartAlert.headline }}</h2>
        <ul v-if="smartAlert.bullets.length" class="smart-alert__list">
          <li v-for="(b, i) in smartAlert.bullets" :key="i">{{ b }}</li>
        </ul>
      </section>

      <!-- 2. Readiness + plan coverage -->
      <section v-if="!dataHealthLoading && dataHealth" class="readiness-section">
        <h2 class="section-heading">Can I run planning?</h2>
        <div class="readiness-grid">
          <div class="readiness-tile">
            <div class="readiness-tile__label">Products</div>
            <div class="readiness-tile__value">{{ dataHealth.products?.count ?? '—' }} <span class="readiness-tile__sub">({{ dataHealth.products?.active ?? 0 }} active)</span></div>
          </div>
          <div class="readiness-tile">
            <div class="readiness-tile__label">Demand</div>
            <div class="readiness-tile__value">{{ dataHealth.demand?.latest_week ?? '—' }}</div>
            <div class="readiness-tile__sub">{{ dataHealth.demand?.skus_with_demand ?? 0 }} SKUs</div>
          </div>
          <div class="readiness-tile">
            <div class="readiness-tile__label">SOH</div>
            <div class="readiness-tile__value">{{ dataHealth.soh?.latest_week ?? '—' }}</div>
            <div class="readiness-tile__sub">{{ dataHealth.soh?.skus_with_stock ?? 0 }} SKUs</div>
          </div>
          <div class="readiness-tile">
            <div class="readiness-tile__label">Policies</div>
            <div class="readiness-tile__value">{{ dataHealth.planning_policies?.count ?? 0 }}</div>
          </div>
          <div class="readiness-tile" :class="dataHealth.ready_to_plan ? 'readiness-tile--ok' : 'readiness-tile--warn'">
            <div class="readiness-tile__label">Ready (stock-aware)</div>
            <div class="readiness-tile__value">{{ dataHealth.ready_to_plan ? 'Yes' : 'No' }}</div>
          </div>
          <div class="readiness-tile" :class="dataHealth.ready_for_demand_only ? 'readiness-tile--ok' : 'readiness-tile--warn'">
            <div class="readiness-tile__label">Ready (demand-only)</div>
            <div class="readiness-tile__value">{{ dataHealth.ready_for_demand_only ? 'Yes' : 'No' }}</div>
          </div>
          <div
            class="readiness-tile readiness-tile--kpi"
            :class="planCoverageKpiTone"
            :title="planCoverageTooltip"
          >
            <div class="readiness-tile__label">Plan coverage</div>
            <div class="readiness-tile__value readiness-tile__value--lg">{{ planCoverageLabel }}</div>
            <div class="readiness-tile__sub">{{ planCoverageSub }}</div>
          </div>
        </div>
      </section>

      <!-- 4. Latest run + next steps -->
      <section v-if="planRuns.length" class="launch-card launch-card--run">
        <h2 class="section-heading">After you run — where to go next</h2>
        <p class="text-sm text-slate-600 mb-3">
          Focus selects which run opens in the tools below. Default is the most recent.
        </p>
        <div class="run-focus-row">
          <label class="run-focus-label">
            <span class="text-sm text-slate-600">Focus run</span>
            <select v-model="selectedRunId" class="app-select run-focus-select">
              <option :value="null">Select…</option>
              <option v-for="r in planRuns" :key="r.id" :value="r.id">{{ formatPlanRunLabel(r) }}</option>
            </select>
          </label>
        </div>
        <div v-if="focusedRun" class="run-detail">
          <p class="run-detail__title"><strong>{{ formatPlanRunLabel(focusedRun) }}</strong></p>
          <ul class="run-detail__meta">
            <li><span class="run-detail__k">Mode</span> {{ planRunModeShort(focusedRun) }}</li>
            <li><span class="run-detail__k">Run at</span> {{ focusedRun.run_at }}</li>
            <li><span class="run-detail__k">Created</span> {{ focusedRun.created_at }}</li>
            <li v-if="warehouseScopeLabel"><span class="run-detail__k">Scope</span> {{ warehouseScopeLabel }}</li>
          </ul>
        </div>
        <nav v-if="selectedRunId" class="next-nav" aria-label="Open focused run">
          <router-link
            class="next-nav__btn"
            :to="{ path: '/planning-grid', query: { plan_run_id: String(selectedRunId) } }"
          >Weekly Planning Grid</router-link>
          <router-link
            class="next-nav__btn"
            :to="{ path: '/inventory-projection', query: { plan_run_id: String(selectedRunId) } }"
          >Inventory Projection</router-link>
          <router-link class="next-nav__btn" to="/planning/scenario-manager">Scenario Manager</router-link>
          <router-link class="next-nav__btn" to="/exports">Exports</router-link>
        </nav>
        <p v-else class="text-sm text-slate-500">Select a focus run to enable shortcuts.</p>
      </section>

      <section v-else-if="!loading" class="launch-card text-sm text-slate-600">
        No plan runs yet. Run planning above to create one.
      </section>

      <!-- 6. Help (secondary) -->
      <div class="help-wrap">
        <PageHelpPanel page-key="Dashboard" />
      </div>

      <!-- 5. Secondary analysis -->
      <details class="dashboard-more launch-details">
        <summary>Risk summaries &amp; top SKUs (optional)</summary>
        <p class="text-sm text-slate-600 mt-2 mb-3">
          For the <strong>focused</strong> run. Prefer the Planning Grid or Inventory Projection for daily review.
        </p>
        <div v-if="!selectedRunId" class="muted">Select a focus run above.</div>
        <template v-else>
          <div class="risk-summary-grid">
            <div class="risk-summary-card">
              <h3 class="risk-summary-card__title">Next 8 weeks</h3>
              <p class="risk-summary-card__stat">Stockouts: {{ stockoutCount8 }}</p>
              <p class="risk-summary-card__stat">SKU/wh at risk: {{ atRiskSkus8.length }}</p>
            </div>
            <div class="risk-summary-card">
              <h3 class="risk-summary-card__title">Next 13 weeks</h3>
              <p class="risk-summary-card__stat">Stockouts: {{ stockoutCount13 }}</p>
              <p class="risk-summary-card__stat">SKU/wh at risk: {{ atRiskSkus13.length }}</p>
            </div>
          </div>
          <h3 class="text-sm font-medium text-slate-800 mt-4 mb-2">Top SKUs by risk (max 5)</h3>
          <div v-if="topRisksLimited.length" class="app-table-wrap">
            <table class="app-table app-table--wide">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Warehouse</th>
                  <th>Weeks at risk</th>
                  <th>Min WOC</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(row, i) in topRisksLimited"
                  :key="i"
                  class="top-risk-row"
                  @click="goToPlanningGrid(row)"
                >
                  <td>{{ row.sku }}</td>
                  <td>{{ row.warehouse_code }}</td>
                  <td>{{ row.stockoutWeeks }}</td>
                  <td>{{ row.minWoc }}</td>
                  <td>
                    <router-link :to="planningGridLink(row)" class="view-icon" title="View in grid" @click.stop>View</router-link>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="muted">No stockout risk for this run.</p>
        </template>
      </details>

      <details class="dashboard-more launch-details">
        <summary>Recent runs <span v-if="planRuns.length > 5" class="text-slate-500 font-normal">({{ planRuns.length }} total)</span></summary>
        <p v-if="planRuns.length > 5" class="text-sm text-slate-600 mt-2">Showing 5 most recent. Click a row to set focus.</p>
        <p v-else class="text-sm text-slate-600 mt-2">Click a row to set focus.</p>
        <div class="app-table-wrap">
          <table class="app-table app-table--wide">
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Mode</th>
                <th>Demand</th>
                <th>Freeze</th>
                <th>Run at</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="r in recentRunsLimited"
                :key="r.id"
                :class="{ 'row-selected': selectedRunId === r.id }"
                @click="selectedRunId = r.id"
              >
                <td>{{ formatPlanRunLabel(r) }}</td>
                <td class="text-sm text-slate-600 whitespace-nowrap">{{ planRunModeShort(r) }}</td>
                <td>{{ r.demand_source ?? 'actuals' }}</td>
                <td>{{ r.freeze_weeks ?? 4 }}</td>
                <td>{{ r.run_at }}</td>
                <td>{{ r.created_at }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePlanningStore } from '@/stores/planning'
import type { PlanRun, ProjectedInventory } from '@/api/client'
import { formatPlanRunLabel, planRunPlanningMode, fetchWarehouseReadiness, type WarehouseReadinessItem } from '@/api/client'
import { useBannerStore } from '@/stores/banner'
import api from '@/api/client'
import PageHelpPanel from '@/components/console/PageHelpPanel.vue'
import OperationStatusPanel from '@/components/common/OperationStatusPanel.vue'
import { useOperation } from '@/composables/useOperation'

interface DataHealth {
  products?: { count: number; active: number }
  demand: { latest_week: string | null; weeks_available?: number; skus_with_demand?: number }
  soh: { latest_week: string | null; skus_with_stock?: number }
  planning_policies: { count: number; required_approx?: number }
  ready_to_plan: boolean
  ready_for_demand_only?: boolean
}

interface SkuIntegrityPayload {
  plan_coverage: { numerator: number; denominator: number; ratio: number | null }
  orphan_skus: {
    planning_policy_rows: { count: number }
    inventory_snapshots_weekly_distinct_sku: { count: number }
    demand_actuals_distinct_sku: { count: number }
    demand_facts_weekly_distinct_sku: { orphan_sku_distinct_count: number | null; error: string | null }
  }
}

const router = useRouter()
const store = usePlanningStore()
const bannerStore = useBannerStore()
const loading = ref(true)
const runPlanOperation = useOperation('Planning run')
const runPlanLoading = runPlanOperation.isRunning
const runName = ref('')
const scenarioName = ref('baseline')
const demandSource = ref<'actuals' | 'baseline' | 'blended'>('actuals')
const planningMode = ref<'stock_aware' | 'demand_only'>('stock_aware')
const freezeWeeks = ref(4)
const selectedRunId = ref<number | null>(null)
const dataHealth = ref<DataHealth | null>(null)
const dataHealthLoading = ref(true)
const skuIntegrityFull = ref<SkuIntegrityPayload | null>(null)
const skuIntegrityLoaded = ref(false)

const planCoverageTooltip =
  'Percentage of policy SKU×warehouse pairs that have both demand and stock on hand.'

const planRuns = computed(() => store.planRuns)

const focusedRun = computed(() => planRuns.value.find((r) => r.id === selectedRunId.value) ?? null)

const warehouseScopeLabel = computed(() => {
  const r = focusedRun.value
  if (!r?.warehouses_scope?.length) return ''
  return r.warehouses_scope.join(', ')
})

const recentRunsLimited = computed(() =>
  [...planRuns.value].sort((a, b) => b.id - a.id).slice(0, 5)
)

const planCoverageRatio = computed(() => skuIntegrityFull.value?.plan_coverage?.ratio ?? null)

const planCoverageLabel = computed(() => {
  const p = skuIntegrityFull.value?.plan_coverage
  if (!skuIntegrityLoaded.value) return '…'
  if (!p || p.denominator === 0) return 'Not available yet'
  if (p.ratio == null) return 'Not available yet'
  return `${Math.round(p.ratio * 1000) / 10}%`
})

const planCoverageSub = computed(() => {
  const p = skuIntegrityFull.value?.plan_coverage
  if (!skuIntegrityLoaded.value) return 'Loading…'
  if (!p || p.denominator === 0) return 'Add policies to measure coverage'
  if (p.ratio == null) return '—'
  return `${p.numerator} / ${p.denominator} policy pairs with demand & SOH`
})

const planCoverageKpiTone = computed(() => {
  const p = skuIntegrityFull.value?.plan_coverage
  if (!skuIntegrityLoaded.value || !p || p.denominator === 0 || p.ratio == null) return ''
  const r = p.ratio
  if (r >= 0.8) return 'readiness-tile--cov-high'
  if (r >= 0.5) return 'readiness-tile--cov-mid'
  return 'readiness-tile--cov-low'
})

const orphanSkuTotal = computed(() => {
  if (!skuIntegrityFull.value) return 0
  const o = skuIntegrityFull.value.orphan_skus
  const df = o.demand_facts_weekly_distinct_sku.orphan_sku_distinct_count ?? 0
  return (
    o.planning_policy_rows.count +
    o.inventory_snapshots_weekly_distinct_sku.count +
    o.demand_actuals_distinct_sku.count +
    df
  )
})

const smartAlert = computed((): { severity: 'green' | 'amber' | 'red'; headline: string; bullets: string[] } | null => {
  if (!dataHealth.value) return null
  const bullets: string[] = []
  const r = planCoverageRatio.value
  const orphans = skuIntegrityLoaded.value ? orphanSkuTotal.value : 0

  if (orphans > 0) {
    bullets.push(`${orphans} orphan SKU issue(s) reported in diagnostics — fix master data or mappings before trusting stock-aware results.`)
  }
  if (skuIntegrityLoaded.value && r != null && r < 0.5) {
    bullets.push(`Plan coverage is below 50% (${Math.round(r * 1000) / 10}%) — many policy pairs lack demand or SOH for stock-aware planning.`)
  } else if (skuIntegrityLoaded.value && r != null && r >= 0.5 && r < 0.8) {
    bullets.push(`Plan coverage is partial (${Math.round(r * 1000) / 10}%) — review Data Health for gaps.`)
  }
  if (
    dataHealth.value.ready_for_demand_only &&
    !dataHealth.value.ready_to_plan
  ) {
    bullets.push('Demand-only planning is available; stock-aware needs SOH (and overlap) — choose mode to match your goal.')
  }
  if (orphans > 0) {
    return {
      severity: 'red',
      headline: 'Data integrity: orphan SKUs detected',
      bullets: bullets.slice(0, 4),
    }
  }
  if (skuIntegrityLoaded.value && r != null && r < 0.5) {
    return {
      severity: 'red',
      headline: 'Stock-aware coverage is low',
      bullets: bullets.length ? bullets.slice(0, 4) : ['Review policy × demand × SOH alignment in Data Health.'],
    }
  }
  if (
    (skuIntegrityLoaded.value && r != null && r >= 0.5 && r < 0.8) ||
    (dataHealth.value.ready_for_demand_only && !dataHealth.value.ready_to_plan)
  ) {
    return {
      severity: 'amber',
      headline: 'Guidance: partial coverage or demand-only path',
      bullets: bullets.length ? bullets.slice(0, 4) : ['See readiness tiles and Plan coverage.'],
    }
  }
  return {
    severity: 'green',
    headline: 'No blocking issues from current checks',
    bullets: ['Continue with a test plan run, then open the grid or projections.'],
  }
})

const readyToPlan = computed(() => {
  const h = dataHealth.value
  if (!h) return false
  if (planningMode.value === 'demand_only') {
    return h.planning_policies.count > 0 && !!h.demand?.latest_week
  }
  return !!h.ready_to_plan
})

const runPlanButtonLabel = computed(() => {
  const scenario = scenarioName.value.charAt(0).toUpperCase() + scenarioName.value.slice(1)
  const demand = demandSource.value === 'actuals' ? 'Actuals' : demandSource.value === 'baseline' ? 'Baseline' : 'Blended'
  const mode = planningMode.value === 'demand_only' ? 'Demand-only' : 'Stock-aware'
  return `Run plan (${scenario} • ${demand} • ${mode} • Freeze ${freezeWeeks.value}w)`
})

function planRunModeShort(r: PlanRun): string {
  if (planRunPlanningMode(r) === 'demand_only') {
    return r.progress_meta?.synthetic_starting_inventory ? 'Demand-only · synth' : 'Demand-only'
  }
  return 'Stock-aware'
}

function planningGridLink(row: { sku: string; warehouse_code: string }) {
  return {
    path: '/planning-grid',
    query: {
      plan_run_id: String(selectedRunId.value),
      sku: row.sku,
      warehouse_code: row.warehouse_code,
    },
  }
}

function goToPlanningGrid(row: { sku: string; warehouse_code: string }) {
  router.push(planningGridLink(row))
}

function readinessFor(wh: string): WarehouseReadinessItem | undefined {
  return warehouseReadiness.value.find((r) => r.warehouse_code === wh)
}

function condenseBlockers(blockers: string[]): string {
  const parts: string[] = []
  if (blockers.some((b) => /SOH|Stock On Hand/i.test(b))) parts.push('SOH')
  if (blockers.some((b) => /demand|sales|Direct sales/i.test(b))) parts.push('demand')
  if (blockers.some((b) => /polic/i.test(b))) parts.push('policies')
  return parts.length ? `missing ${parts.join('/')}` : 'not ready'
}

const warehouseScope = ref<'AAH' | 'BLP' | 'all_ready'>('AAH')
const warehouseReadiness = ref<WarehouseReadinessItem[]>([])
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
})

const topRisksLimited = computed(() => topRisks.value.slice(0, 5))

function resolveWarehousesScope(): string[] | null {
  if (warehouseScope.value === 'AAH') return ['AAH']
  if (warehouseScope.value === 'BLP') return ['BLP']
  if (warehouseScope.value === 'all_ready') {
    const ready = warehouseReadiness.value.filter((r) => r.ready).map((r) => r.warehouse_code)
    return ready.length ? ready : null
  }
  return null
}

async function runScenario() {
  const notes = runName.value.trim() || `${scenarioName.value} ${new Date().toISOString().slice(0, 10)}`
  const whScope = resolveWarehousesScope()
  const run = await runPlanOperation.runWithOperation(
    'Planning run',
    async () => {
      try {
        return await store.runPlan(
          scenarioName.value,
          undefined,
          demandSource.value,
          freezeWeeks.value,
          notes,
          whScope,
          planningMode.value
        )
      } catch (err: unknown) {
        const res = err && typeof err === 'object' && 'response' in err ? (err as { response?: { status?: number; data?: unknown } }).response : null
        if (res?.status === 400 && res?.data && typeof res.data === 'object' && 'detail' in res.data) {
          const detail = res.data.detail as { code?: string; message?: string; skipped_warehouses?: Array<{ warehouse_code: string; blockers: string[] }> }
          const skipped = detail.skipped_warehouses?.map((s) => `${s.warehouse_code}: ${s.blockers.join('; ')}`).join('\n')
          const message = detail.code === 'demo_data_detected' ? 'Demo data disabled; please load real data.' : detail.message || 'Plan run failed.'
          throw new Error(skipped ? `${message}\n${skipped}` : message)
        }
        throw err
      }
    },
    {
      runningMessage: 'Running planning scenario...',
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh plan runs before retrying.',
      nextActions: ['Refresh plan runs before retrying.', 'Check Data Health if the run does not appear.'],
    },
  )
  if (!run) return
  try {
    await store.fetchPlanRuns()
    if (store.planRuns.length) selectedRunId.value = store.planRuns[0].id
    const meta = run.progress_meta as {
      plan_start_week_start?: string | null
      warehouses_planned?: string[]
      warehouses_planned_detail?: Array<{ warehouse_code: string; latest_soh_week_start?: string; latest_demand_week_start?: string; skus_planned?: number }>
      warehouses_skipped?: string[]
      skipped_warehouses_detail?: Array<{ warehouse_code: string; blockers: string[] }>
    } | undefined
    const planAnchor = meta?.plan_start_week_start ?? '—'
    const plannedDetail = meta?.warehouses_planned_detail ?? []
    const skippedDetail = meta?.skipped_warehouses_detail ?? []
    const plannedParts = plannedDetail.length
      ? plannedDetail.map(
          (d) =>
            `${d.warehouse_code} (plan horizon ${planAnchor}; demand actuals through: ${d.latest_demand_week_start ?? '—'}; SOH week: ${d.latest_soh_week_start ?? '—'}; SKUs in plan: ${d.skus_planned ?? 0})`,
        )
      : (meta?.warehouses_planned ?? []).map((wh) => wh)
    const plannedMsg = plannedParts.length ? `Planned: ${plannedDetail.length ? plannedParts.join('. ') : plannedParts.join(', ')}.` : ''
    const skippedMsg = skippedDetail.map((s) => {
      const missing = condenseBlockers(s.blockers)
      return `${s.warehouse_code} (${missing})`
    }).join(', ')
    const planMsg = plannedMsg
    const skipMsg = skippedMsg ? `Skipped: ${skippedMsg}.` : ''
    const msg = [planMsg, skipMsg].filter(Boolean).join(' ') || `"${run.scenario_name}" created.`
    runPlanOperation.completeOperation({
      message: 'Plan created.',
      detail: msg,
      technicalDetails: run,
    })
    bannerStore.add({
      type: 'success',
      title: 'Plan run created',
      message: msg,
      actionLink: { to: '/reports/data-health', label: 'View diagnostics' },
    })
  } catch (err: unknown) {
    runPlanOperation.failOperation(err)
  }
}

async function loadDataHealth() {
  dataHealthLoading.value = true
  try {
    const { data } = await api.get<DataHealth>('/v1/reports/data-health')
    dataHealth.value = data
  } finally {
    dataHealthLoading.value = false
  }
}

async function loadWarehouseReadiness() {
  warehouseReadiness.value = await fetchWarehouseReadiness(demandSource.value, planningMode.value)
}

watch([demandSource, planningMode], loadWarehouseReadiness)

async function loadSkuIntegritySummary() {
  skuIntegrityLoaded.value = false
  try {
    const { data } = await api.get<SkuIntegrityPayload>('/v1/reports/data-health/sku-integrity')
    skuIntegrityFull.value = data
  } catch {
    skuIntegrityFull.value = null
  } finally {
    skuIntegrityLoaded.value = true
  }
}

onMounted(async () => {
  try {
    await Promise.all([
      store.fetchPlanRuns(),
      loadDataHealth(),
      loadWarehouseReadiness(),
      loadSkuIntegritySummary(),
    ])
    if (store.planRuns.length && selectedRunId.value == null) selectedRunId.value = store.planRuns[0].id
  } catch (err: unknown) {
    const res = err && typeof err === 'object' && 'response' in err ? (err as { response?: { status?: number; data?: { detail?: unknown } } }).response : null
    const detail = res?.data?.detail
    const msg =
      res?.status === 503
        ? (typeof detail === 'string' ? detail : 'Database unavailable. Start MySQL and the API.')
        : detail != null
          ? typeof detail === 'string'
            ? detail
            : JSON.stringify(detail)
          : 'Could not load dashboard data. Is the API running on port 8000?'
    bannerStore.add({ type: 'error', title: 'Dashboard load failed', message: msg })
  } finally {
    loading.value = false
  }
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
.dashboard-launchpad {
  width: 100%;
  max-width: 1600px;
  margin: 0 auto;
}
.section-heading {
  font-size: 1rem;
  font-weight: 600;
  color: rgb(30 41 59);
  margin: 0 0 0.75rem;
}
.launch-card {
  background: white;
  border: 1px solid rgb(226 232 240);
  border-radius: 0.5rem;
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.25rem;
}
.launch-card--primary {
  border-left: 4px solid rgb(33 74 125);
}
.launch-card__h1 {
  font-size: 1.25rem;
  font-weight: 600;
  color: rgb(15 23 42);
  margin: 0 0 0.5rem;
}
.launch-card__lede {
  font-size: 0.875rem;
  color: rgb(71 85 105);
  margin: 0 0 1.25rem;
  line-height: 1.45;
  max-width: 48rem;
}
.launch-field-group {
  margin-bottom: 1rem;
}
.launch-label {
  display: block;
  margin-bottom: 0.35rem;
}
.launch-radio-row {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.launch-radio-row--compact {
  flex-direction: row;
  flex-wrap: wrap;
  gap: 1rem;
}
.launch-radio {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: rgb(51 65 85);
  cursor: pointer;
}
.launch-radio--inline {
  align-items: center;
}
.launch-ready-pill {
  font-size: 0.65rem;
  padding: 0.1rem 0.35rem;
  border-radius: 0.25rem;
  margin-left: 0.25rem;
}
.launch-ready-pill.is-yes {
  background: rgb(220 252 231);
  color: rgb(22 101 52);
}
.launch-ready-pill.is-no {
  background: rgb(254 249 195);
  color: rgb(133 77 14);
}
.launch-run-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 1rem;
  margin-top: 1rem;
}
.launch-run-btn {
  min-height: 2.5rem;
  padding-left: 1.25rem;
  padding-right: 1.25rem;
}
.launch-advanced summary {
  cursor: pointer;
  font-size: 0.8125rem;
  color: rgb(71 85 105);
}
.launch-hint {
  margin: 1rem 0 0;
}
.run-feedback {
  border-radius: 0.375rem;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
  font-size: 0.875rem;
}
.run-feedback--error {
  background: rgb(254 242 242);
  border: 1px solid rgb(252 165 165);
  color: rgb(127 29 29);
}
.run-feedback--ok {
  background: rgb(240 253 244);
  border: 1px solid rgb(134 239 172);
  color: rgb(22 101 52);
}
.run-feedback__list {
  margin: 0.5rem 0 0;
  padding-left: 1.25rem;
}
.run-feedback__links {
  display: flex;
  gap: 1rem;
  margin-top: 0.5rem;
  font-size: 0.8125rem;
}
.run-feedback__links a {
  font-weight: 500;
  text-decoration: underline;
  color: inherit;
}
.smart-alert {
  border-radius: 0.5rem;
  padding: 1rem 1.25rem;
  margin-bottom: 1.25rem;
  border: 1px solid rgb(226 232 240);
}
.smart-alert--green {
  background: rgb(240 253 244);
  border-color: rgb(167 243 208);
}
.smart-alert--amber {
  background: rgb(254 252 232);
  border-color: rgb(253 224 71);
}
.smart-alert--red {
  background: rgb(254 242 242);
  border-color: rgb(252 165 165);
}
.smart-alert__title {
  font-size: 0.9375rem;
  font-weight: 600;
  margin: 0 0 0.5rem;
  color: rgb(15 23 42);
}
.smart-alert__list {
  margin: 0;
  padding-left: 1.25rem;
  font-size: 0.8125rem;
  color: rgb(51 65 85);
  line-height: 1.45;
}
.readiness-section {
  margin-bottom: 1.25rem;
}
.readiness-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 0.75rem;
}
.readiness-tile {
  background: white;
  border: 1px solid rgb(226 232 240);
  border-radius: 0.375rem;
  padding: 0.75rem 1rem;
}
.readiness-tile--ok {
  border-left: 3px solid rgb(34 197 94);
}
.readiness-tile--warn {
  border-left: 3px solid rgb(234 179 8);
}
.readiness-tile--cov-high {
  border-left: 3px solid rgb(34 197 94);
  background: rgb(240 253 244);
}
.readiness-tile--cov-mid {
  border-left: 3px solid rgb(234 179 8);
  background: rgb(254 252 232);
}
.readiness-tile--cov-low {
  border-left: 3px solid rgb(239 68 68);
  background: rgb(254 242 242);
}
.readiness-tile__label {
  font-size: 0.75rem;
  font-weight: 600;
  color: rgb(71 85 105);
  margin-bottom: 0.25rem;
}
.readiness-tile__value {
  font-size: 1rem;
  font-weight: 600;
  color: rgb(15 23 42);
}
.readiness-tile__value--lg {
  font-size: 1.25rem;
}
.readiness-tile__sub {
  font-size: 0.75rem;
  color: rgb(100 116 139);
  margin-top: 0.2rem;
}
.run-focus-row {
  margin-bottom: 1rem;
}
.run-focus-label {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  max-width: 28rem;
}
.run-focus-select {
  width: 100%;
  max-width: 28rem;
}
.run-detail {
  background: rgb(248 250 252);
  border-radius: 0.375rem;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
}
.run-detail__title {
  margin: 0 0 0.5rem;
  font-size: 0.875rem;
}
.run-detail__meta {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: 0.8125rem;
  color: rgb(51 65 85);
}
.run-detail__meta li {
  margin: 0.2rem 0;
}
.run-detail__k {
  display: inline-block;
  min-width: 5rem;
  color: rgb(100 116 139);
}
.next-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.next-nav__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.5rem 1rem;
  font-size: 0.8125rem;
  font-weight: 500;
  color: rgb(255 255 255);
  background: rgb(33 74 125);
  border-radius: 0.375rem;
  text-decoration: none;
}
.next-nav__btn:hover {
  background: rgb(26 60 104);
}
.help-wrap {
  margin-bottom: 1rem;
  max-width: 56rem;
}
.form-inline { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
.plan-run-form .form-label { margin-left: 0.5rem; margin-right: 0.25rem; }
.form-label { font-size: 0.875rem; }
.app-table tbody tr { cursor: pointer; }
.app-table tbody tr.row-selected { background: var(--border); }
.app-table--wide {
  width: 100%;
}
.top-risk-row:hover {
  background: rgb(248 250 252);
}
.view-icon {
  font-size: 0.75rem;
  color: rgb(59 130 246);
  text-decoration: none;
}
.view-icon:hover {
  text-decoration: underline;
}
.launch-details summary {
  cursor: pointer;
  font-weight: 600;
  font-size: 0.9375rem;
  color: rgb(51 65 85);
  list-style: none;
}
.launch-details summary::-webkit-details-marker {
  display: none;
}
.risk-summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
  gap: 0.75rem;
}
.risk-summary-card {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.375rem;
  padding: 0.5rem 0.75rem;
  background: rgb(248 250 252);
}
.risk-summary-card__title {
  margin: 0 0 0.35rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: rgb(51 65 85);
}
.risk-summary-card__stat {
  margin: 0.15rem 0;
  font-size: 0.8125rem;
  color: rgb(71 85 105);
}
</style>
