<template>
  <div class="page-content-inner data-health-page">
    <h1 class="text-xl font-semibold text-slate-800 mb-1">Data Health</h1>
    <p class="muted mb-2">Readiness to run plan. Green = OK, Amber = warning, Red = blocking.</p>
    <p class="text-sm text-slate-600 mb-6 max-w-2xl leading-snug">
      <strong>Ready to Plan</strong> here is <strong>stock-aware</strong> (expects SOH as well as demand and policies).
      <strong>Demand-only</strong> planning can still run when products, demand, and policies are OK — SOH may be missing. Use the demand-only line on the <strong>Ready to Plan</strong> card when shown.
    </p>

    <section
      v-if="!integrityLoading && integrity && systemBannerSeverity"
      class="system-status-banner mb-6"
      :class="`system-status-banner--${systemBannerSeverity}`"
      role="status"
    >
      <h2 class="system-status-banner__headline">{{ systemBannerHeadline }}</h2>
      <ul class="system-status-banner__list">
        <li v-for="(b, i) in systemBannerBullets" :key="i">{{ b }}</li>
      </ul>
      <p class="system-status-banner__action"><strong>Recommended:</strong> {{ systemBannerAction }}</p>
    </section>

    <section v-if="loading" class="content-section">Loading...</section>
    <template v-else>
      <div class="health-cards">
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
          <h3 class="card-title">Ready to Plan (stock-aware)</h3>
          <p class="card-value">{{ health?.ready_to_plan ? 'Yes' : 'No' }}</p>
          <p v-if="health?.ready_for_demand_only != null" class="card-meta text-slate-600">
            Demand-only gate: {{ health.ready_for_demand_only ? 'OK (policies + demand)' : 'Not OK' }}
          </p>
          <p v-if="!health?.ready_to_plan" class="card-warn">Complete setup steps first (including SOH for stock-aware)</p>
        </div>
        <div
          v-if="!integrityLoading && integrity?.plan_coverage"
          class="health-card plan-coverage-kpi"
          :class="planCoverageKpiClass"
          :title="planCoverageTooltip"
        >
          <h3 class="card-title">Plan coverage</h3>
          <p class="card-value">
            <span class="plan-coverage-pct">{{ planCoveragePercentLabel }}</span>
            <span class="card-meta block mt-1">
              {{ integrity.plan_coverage.numerator }} / {{ integrity.plan_coverage.denominator }} policy pairs with demand &amp; SOH
            </span>
          </p>
          <p class="card-meta">SKU×warehouse policies that have both historical demand and at least one SOH snapshot.</p>
        </div>
      </div>
      <div v-if="warnings.length" class="mt-6 p-4 rounded-lg bg-amber-50 border border-amber-200">
        <h3 class="font-semibold text-amber-800 mb-2">Warnings</h3>
        <ul class="list-disc list-inside text-amber-800 text-sm space-y-1">
          <li v-for="(w, i) in warnings" :key="i">{{ w }}</li>
        </ul>
      </div>

      <section class="mt-10 integrity-section">
        <h2 class="text-lg font-semibold text-slate-800 mb-1">SKU &amp; planning coverage (read-only)</h2>
        <p class="text-sm text-slate-600 mb-4 max-w-3xl leading-snug">
          Compares canonical <code class="text-xs bg-slate-100 px-1 rounded">products.sku</code> to policies, SOH, and demand tables.
          Uses the latest demand/SOH week in the database as an anchor for &ldquo;recent&rdquo; windows (see parameters).
        </p>
        <div v-if="integrityLoading" class="text-sm text-slate-500">Loading diagnostics…</div>
        <div v-else-if="integrityError" class="text-sm text-red-700 p-3 rounded border border-red-200 bg-red-50">{{ integrityError }}</div>
        <template v-else-if="integrity">
          <div class="integrity-params text-xs text-slate-600 mb-4 p-3 rounded bg-slate-50 border border-slate-200 font-mono space-y-1">
            <div><strong>Recent demand cutoff:</strong> {{ integrity.parameters.recent_demand_cutoff_week_start }} (anchor {{ integrity.parameters.anchor_demand_latest_week ?? '—' }})</div>
            <div><strong>Recent SOH cutoff:</strong> {{ integrity.parameters.recent_soh_cutoff_week_start }} (anchor {{ integrity.parameters.anchor_soh_latest_week ?? '—' }})</div>
            <div><strong>Window:</strong> {{ integrity.parameters.recent_weeks }} weeks · <strong>Sample cap:</strong> {{ integrity.parameters.sample_limit }}</div>
          </div>

          <h3 class="text-sm font-semibold text-slate-700 mb-2">Orphan SKUs (not in products)</h3>
          <div class="integrity-grid mb-6">
            <div class="integrity-card">
              <div class="integrity-card__title">Planning policies</div>
              <div class="integrity-card__count">{{ integrity.orphan_skus.planning_policy_rows.count }}</div>
              <p class="integrity-card__hint">policy rows where sku missing from products</p>
              <table v-if="integrity.orphan_skus.planning_policy_rows.sample.length" class="integrity-table">
                <thead><tr><th>SKU</th><th>Warehouse</th></tr></thead>
                <tbody>
                  <tr v-for="(r, i) in integrity.orphan_skus.planning_policy_rows.sample" :key="'p'+i">
                    <td class="font-mono text-xs">{{ r.sku }}</td><td>{{ r.warehouse_code }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="integrity-card">
              <div class="integrity-card__title">SOH snapshots (distinct sku)</div>
              <div class="integrity-card__count">{{ integrity.orphan_skus.inventory_snapshots_weekly_distinct_sku.count }}</div>
              <table v-if="integrity.orphan_skus.inventory_snapshots_weekly_distinct_sku.sample.length" class="integrity-table">
                <thead><tr><th>SKU</th><th>WH</th><th>Latest week</th></tr></thead>
                <tbody>
                  <tr v-for="(r, i) in integrity.orphan_skus.inventory_snapshots_weekly_distinct_sku.sample" :key="'s'+i">
                    <td class="font-mono text-xs">{{ r.sku }}</td><td>{{ r.warehouse_code }}</td><td class="text-xs">{{ r.latest_week_start }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="integrity-card">
              <div class="integrity-card__title">Demand actuals (distinct sku)</div>
              <div class="integrity-card__count">{{ integrity.orphan_skus.demand_actuals_distinct_sku.count }}</div>
              <table v-if="integrity.orphan_skus.demand_actuals_distinct_sku.sample.length" class="integrity-table">
                <thead><tr><th>SKU</th><th>WH</th><th>Latest week</th></tr></thead>
                <tbody>
                  <tr v-for="(r, i) in integrity.orphan_skus.demand_actuals_distinct_sku.sample" :key="'d'+i">
                    <td class="font-mono text-xs">{{ r.sku }}</td><td>{{ r.warehouse_code }}</td><td class="text-xs">{{ r.latest_week_start }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="integrity-card">
              <div class="integrity-card__title">Demand facts weekly (distinct sku)</div>
              <p v-if="integrity.orphan_skus.demand_facts_weekly_distinct_sku.error" class="text-xs text-amber-800">{{ integrity.orphan_skus.demand_facts_weekly_distinct_sku.error }}</p>
              <template v-else>
                <div class="integrity-card__count">{{ integrity.orphan_skus.demand_facts_weekly_distinct_sku.orphan_sku_distinct_count ?? '—' }}</div>
                <table v-if="(integrity.orphan_skus.demand_facts_weekly_distinct_sku.orphan_sample ?? []).length" class="integrity-table">
                  <thead><tr><th>SKU</th><th>WH</th><th>Latest week</th></tr></thead>
                  <tbody>
                    <tr v-for="(r, i) in integrity.orphan_skus.demand_facts_weekly_distinct_sku.orphan_sample" :key="'f'+i">
                      <td class="font-mono text-xs">{{ r.sku }}</td><td>{{ r.warehouse_code }}</td><td class="text-xs">{{ r.latest_week_start }}</td>
                    </tr>
                  </tbody>
                </table>
              </template>
            </div>
          </div>

          <h3 class="text-sm font-semibold text-slate-700 mb-2">Demand actuals vs demand facts (distinct sku × warehouse)</h3>
          <p v-if="integrity.demand_actuals_vs_demand_facts_pairs.error" class="text-xs text-amber-800 mb-2">{{ integrity.demand_actuals_vs_demand_facts_pairs.error }}</p>
          <div v-else class="integrity-grid mb-6">
            <div class="integrity-card">
              <div class="integrity-card__title">In both</div>
              <div class="integrity-card__count">{{ integrity.demand_actuals_vs_demand_facts_pairs.pairs_in_both }}</div>
            </div>
            <div class="integrity-card">
              <div class="integrity-card__title">Only in demand_actuals</div>
              <div class="integrity-card__count">{{ integrity.demand_actuals_vs_demand_facts_pairs.pairs_only_in_demand_actuals }}</div>
              <table v-if="integrity.demand_actuals_vs_demand_facts_pairs.sample_only_in_actuals?.length" class="integrity-table">
                <thead><tr><th>SKU</th><th>WH</th></tr></thead>
                <tbody>
                  <tr v-for="(r, i) in integrity.demand_actuals_vs_demand_facts_pairs.sample_only_in_actuals" :key="'a'+i">
                    <td class="font-mono text-xs">{{ r.sku }}</td><td>{{ r.warehouse_code }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="integrity-card">
              <div class="integrity-card__title">Only in demand_facts_weekly</div>
              <div class="integrity-card__count">{{ integrity.demand_actuals_vs_demand_facts_pairs.pairs_only_in_demand_facts_weekly }}</div>
              <table v-if="integrity.demand_actuals_vs_demand_facts_pairs.sample_only_in_facts?.length" class="integrity-table">
                <thead><tr><th>SKU</th><th>WH</th></tr></thead>
                <tbody>
                  <tr v-for="(r, i) in integrity.demand_actuals_vs_demand_facts_pairs.sample_only_in_facts" :key="'b'+i">
                    <td class="font-mono text-xs">{{ r.sku }}</td><td>{{ r.warehouse_code }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <h3 class="text-sm font-semibold text-slate-700 mb-2">Coverage gaps (sku × warehouse)</h3>
          <div class="integrity-grid">
            <div class="integrity-card">
              <div class="integrity-card__title">Demand but no SOH (ever)</div>
              <div class="integrity-card__count">{{ integrity.coverage_gaps.demand_pair_no_soh_pair_ever.pair_count }}</div>
              <table v-if="integrity.coverage_gaps.demand_pair_no_soh_pair_ever.sample.length" class="integrity-table">
                <thead><tr><th>SKU</th><th>WH</th></tr></thead>
                <tbody>
                  <tr v-for="(r, i) in integrity.coverage_gaps.demand_pair_no_soh_pair_ever.sample" :key="'g1'+i">
                    <td class="font-mono text-xs">{{ r.sku }}</td><td>{{ r.warehouse_code }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="integrity-card">
              <div class="integrity-card__title">SOH but no policy</div>
              <div class="integrity-card__count">{{ integrity.coverage_gaps.soh_pair_no_planning_policy.pair_count }}</div>
              <table v-if="integrity.coverage_gaps.soh_pair_no_planning_policy.sample.length" class="integrity-table">
                <thead><tr><th>SKU</th><th>WH</th></tr></thead>
                <tbody>
                  <tr v-for="(r, i) in integrity.coverage_gaps.soh_pair_no_planning_policy.sample" :key="'g2'+i">
                    <td class="font-mono text-xs">{{ r.sku }}</td><td>{{ r.warehouse_code }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="integrity-card">
              <div class="integrity-card__title">Policy, no recent demand</div>
              <div class="integrity-card__count">{{ integrity.coverage_gaps.planning_policy_no_recent_demand.pair_count }}</div>
              <table v-if="integrity.coverage_gaps.planning_policy_no_recent_demand.sample.length" class="integrity-table">
                <thead><tr><th>SKU</th><th>WH</th></tr></thead>
                <tbody>
                  <tr v-for="(r, i) in integrity.coverage_gaps.planning_policy_no_recent_demand.sample" :key="'g3'+i">
                    <td class="font-mono text-xs">{{ r.sku }}</td><td>{{ r.warehouse_code }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="integrity-card">
              <div class="integrity-card__title">Policy, no recent SOH</div>
              <div class="integrity-card__count">{{ integrity.coverage_gaps.planning_policy_no_recent_soh.pair_count }}</div>
              <table v-if="integrity.coverage_gaps.planning_policy_no_recent_soh.sample.length" class="integrity-table">
                <thead><tr><th>SKU</th><th>WH</th></tr></thead>
                <tbody>
                  <tr v-for="(r, i) in integrity.coverage_gaps.planning_policy_no_recent_soh.sample" :key="'g4'+i">
                    <td class="font-mono text-xs">{{ r.sku }}</td><td>{{ r.warehouse_code }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>
      </section>
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
  ready_for_demand_only?: boolean
}

const loading = ref(true)
const health = ref<DataHealth | null>(null)
const integrityLoading = ref(true)
const integrityError = ref('')
const integrity = ref<SkuIntegrityReport | null>(null)

/** Mirrors GET /api/v1/reports/data-health/sku-integrity (loose typing). */
interface SkuIntegrityReport {
  parameters: {
    sample_limit: number
    recent_weeks: number
    recent_demand_cutoff_week_start: string
    recent_soh_cutoff_week_start: string
    anchor_demand_latest_week: string | null
    anchor_soh_latest_week: string | null
  }
  orphan_skus: {
    planning_policy_rows: { count: number; sample: Array<{ sku: string; warehouse_code: string }> }
    inventory_snapshots_weekly_distinct_sku: { count: number; sample: Array<{ sku: string; warehouse_code: string; latest_week_start: string | null }> }
    demand_actuals_distinct_sku: { count: number; sample: Array<{ sku: string; warehouse_code: string; latest_week_start: string | null }> }
    demand_facts_weekly_distinct_sku: {
      orphan_sku_distinct_count: number | null
      orphan_sample: Array<{ sku: string; warehouse_code: string; latest_week_start: string | null }>
      error: string | null
    }
  }
  demand_actuals_vs_demand_facts_pairs: {
    pairs_in_both: number | null
    pairs_only_in_demand_actuals: number | null
    pairs_only_in_demand_facts_weekly: number | null
    sample_only_in_actuals: Array<{ sku: string; warehouse_code: string }>
    sample_only_in_facts: Array<{ sku: string; warehouse_code: string }>
    error?: string | null
  }
  coverage_gaps: {
    demand_pair_no_soh_pair_ever: { pair_count: number; sample: Array<{ sku: string; warehouse_code: string }> }
    soh_pair_no_planning_policy: { pair_count: number; sample: Array<{ sku: string; warehouse_code: string }> }
    planning_policy_no_recent_demand: { pair_count: number; sample: Array<{ sku: string; warehouse_code: string }> }
    planning_policy_no_recent_soh: { pair_count: number; sample: Array<{ sku: string; warehouse_code: string }> }
  }
  plan_coverage: {
    numerator: number
    denominator: number
    ratio: number | null
  }
  demand_without_soh_ratio: number
}

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

const planCoverageTooltip =
  'Percentage of policy SKU×warehouse pairs that have both demand and stock on hand.'

const planCoverageRatio = computed(() => integrity.value?.plan_coverage?.ratio ?? null)

const planCoveragePercentLabel = computed(() => {
  const r = planCoverageRatio.value
  if (r == null) return '—'
  return `${Math.round(r * 1000) / 10}%`
})

const planCoverageKpiClass = computed(() => {
  const r = planCoverageRatio.value
  const d = integrity.value?.plan_coverage?.denominator ?? 0
  if (d === 0) return 'status-neutral'
  if (r == null) return 'status-warn'
  if (r > 0.8) return 'status-ok'
  if (r >= 0.5) return 'status-warn'
  return 'status-fail'
})

const orphanSkuTotal = computed(() => {
  if (!integrity.value) return 0
  const o = integrity.value.orphan_skus
  const df = o.demand_facts_weekly_distinct_sku.orphan_sku_distinct_count ?? 0
  return (
    o.planning_policy_rows.count +
    o.inventory_snapshots_weekly_distinct_sku.count +
    o.demand_actuals_distinct_sku.count +
    df
  )
})

const demandWithoutSohRatio = computed(() => integrity.value?.demand_without_soh_ratio ?? 0)

const sohWithoutPolicyCount = computed(
  () => integrity.value?.coverage_gaps.soh_pair_no_planning_policy.pair_count ?? 0,
)

const systemBannerSeverity = computed((): 'green' | 'amber' | 'red' | null => {
  if (!integrity.value) return null
  const r = planCoverageRatio.value
  const redCoverage = r != null && r < 0.7
  const redOrphans = orphanSkuTotal.value > 0
  if (redCoverage || redOrphans) return 'red'
  if (demandWithoutSohRatio.value > 0.3 || sohWithoutPolicyCount.value > 0) return 'amber'
  return 'green'
})

const systemBannerHeadline = computed(() => {
  switch (systemBannerSeverity.value) {
    case 'red':
      return 'System status: attention required before stock-aware planning'
    case 'amber':
      return 'System status: some coverage gaps — review before go-live'
    default:
      return 'System status: data alignment looks acceptable for testing'
  }
})

const systemBannerBullets = computed((): string[] => {
  const lines: string[] = []
  if (!integrity.value) return lines
  const pc = integrity.value.plan_coverage
  if (pc.denominator > 0 && pc.ratio != null) {
    lines.push(
      `Plan coverage (policy pairs with both demand and SOH): ${Math.round(pc.ratio * 1000) / 10}% (${pc.numerator}/${pc.denominator}).`,
    )
  } else if (pc.denominator === 0) {
    lines.push('Plan coverage: no planning policies — add policies to measure coverage.')
  } else {
    lines.push(`Plan coverage: ${pc.numerator}/${pc.denominator} policy pairs with demand and SOH.`)
  }
  if (orphanSkuTotal.value > 0) {
    lines.push(
      `Orphan SKUs (codes in facts/policies not in product master): ${orphanSkuTotal.value} total across orphan checks.`,
    )
  }
  if (demandWithoutSohRatio.value > 0.3) {
    lines.push(
      `Demand pairs without SOH exceed 30% of all demand pairs (${Math.round(demandWithoutSohRatio.value * 1000) / 10}%) — weak stock-aware alignment.`,
    )
  } else if (integrity.value.coverage_gaps.demand_pair_no_soh_pair_ever.pair_count > 0) {
    lines.push(
      `${integrity.value.coverage_gaps.demand_pair_no_soh_pair_ever.pair_count} demand SKU×warehouse pairs have no matching SOH history.`,
    )
  }
  if (sohWithoutPolicyCount.value > 0) {
    lines.push(
      `${sohWithoutPolicyCount.value} SOH SKU×warehouse pairs have no planning policy.`,
    )
  }
  return lines.slice(0, 5)
})

const systemBannerAction = computed(() => {
  const sev = systemBannerSeverity.value
  if (sev === 'red') {
    return 'Fix orphan SKUs in imports/master; align SOH with demand for stock-aware runs. Until fixed, use demand-only mode if policies and demand are sufficient.'
  }
  if (sev === 'amber') {
    return 'Backfill SOH for key demand pairs and add policies for stocked SKUs where needed. Use demand-only when intentionally skipping physical SOH.'
  }
  return 'Proceed with internal testing; monitor imports and SKU diagnostics below.'
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

async function loadSkuIntegrity() {
  integrityLoading.value = true
  integrityError.value = ''
  try {
    const { data } = await api.get<SkuIntegrityReport>('/v1/reports/data-health/sku-integrity')
    integrity.value = data
  } catch (e: unknown) {
    const msg = e && typeof e === 'object' && 'response' in e
      ? String((e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail ?? 'Request failed')
      : 'Could not load SKU integrity report.'
    integrityError.value = msg
    integrity.value = null
  } finally {
    integrityLoading.value = false
  }
}

onMounted(async () => {
  await load()
  await loadSkuIntegrity()
})
</script>

<style scoped>
.data-health-page {
  width: 100%;
  max-width: 1600px;
  margin: 0 auto;
}
.health-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
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
.health-card.status-neutral {
  border-left: 4px solid rgb(148 163 184);
  background: rgb(248 250 252);
}
.plan-coverage-pct {
  font-size: 1.25rem;
  font-weight: 600;
}
.system-status-banner {
  border-radius: 0.5rem;
  padding: 1rem 1.25rem;
  border: 1px solid rgb(226 232 240);
}
.system-status-banner--green {
  background: rgb(240 253 244);
  border-color: rgb(167 243 208);
}
.system-status-banner--amber {
  background: rgb(254 252 232);
  border-color: rgb(253 224 71);
}
.system-status-banner--red {
  background: rgb(254 242 242);
  border-color: rgb(252 165 165);
}
.system-status-banner__headline {
  font-size: 1rem;
  font-weight: 600;
  margin: 0 0 0.5rem;
  color: rgb(15 23 42);
}
.system-status-banner__list {
  margin: 0 0 0.75rem;
  padding-left: 1.25rem;
  font-size: 0.875rem;
  color: rgb(51 65 85);
  line-height: 1.45;
}
.system-status-banner__action {
  margin: 0;
  font-size: 0.8125rem;
  color: rgb(30 41 59);
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
.integrity-section {
  width: 100%;
  max-width: 1600px;
}
.integrity-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 0.75rem;
}
.integrity-card {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.375rem;
  padding: 0.75rem;
  background: white;
}
.integrity-card__title {
  font-size: 0.75rem;
  font-weight: 600;
  color: rgb(51 65 85);
  margin-bottom: 0.25rem;
}
.integrity-card__count {
  font-size: 1.25rem;
  font-weight: 600;
  color: rgb(15 23 42);
}
.integrity-card__hint {
  font-size: 0.65rem;
  color: rgb(100 116 139);
  margin: 0.25rem 0 0.5rem;
}
.integrity-table {
  width: 100%;
  font-size: 0.7rem;
  border-collapse: collapse;
  margin-top: 0.5rem;
}
.integrity-table th,
.integrity-table td {
  border: 1px solid rgb(226 232 240);
  padding: 0.2rem 0.35rem;
  text-align: left;
}
.integrity-table th {
  background: rgb(248 250 252);
}
</style>
