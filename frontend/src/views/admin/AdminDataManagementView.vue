<template>
  <div class="page-shell space-y-6">
    <header class="page-header">
      <h1>Data management</h1>
      <p class="muted mt-1">
        Control console for test databases: see whether data looks healthy, what to fix, which reset scope fits, and what to reload afterward.
        Preview is read-only; reset always needs the exact confirmation phrase and a non-production environment.
      </p>
    </header>

    <div class="dm-banner" role="alert">
      <strong>Use only in test/dev environments.</strong>
      Reset is blocked when the server <code>ENVIRONMENT</code> is production-like (e.g. prod, staging).
      Never run reset against a database you cannot afford to wipe.
    </div>

    <!-- 1. Data state console -->
    <section class="card card-body">
      <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h2 class="section-title m-0">Data state</h2>
          <p class="text-sm text-slate-600 mt-1 mb-0">
            Quick answer: <strong>{{ databaseCleanLabel }}</strong>
          </p>
        </div>
        <button
          type="button"
          class="btn-primary"
          :disabled="summaryLoading"
          @click="loadSummary"
        >
          {{ summaryLoading ? 'Loading…' : 'Refresh state' }}
        </button>
      </div>
      <OperationStatusPanel :operation="refreshDataOperation.operation" class="mb-4" />

      <div v-if="summary" class="dm-console-grid">
        <div
          v-for="card in stateCards"
          :key="card.key"
          class="dm-console-card"
          :class="`dm-console-card--${card.status}`"
        >
          <div class="dm-console-card__head">
            <span class="dm-console-card__label">{{ card.label }}</span>
            <span class="dm-status-pill" :class="`dm-status-pill--${card.status}`">{{ card.statusLabel }}</span>
          </div>
          <div class="dm-console-card__value">{{ card.displayValue }}</div>
          <p class="dm-console-card__hint">{{ card.hint }}</p>
        </div>
      </div>

      <div v-if="summary?.sku_integrity_highlights" class="mt-4 p-3 rounded-lg bg-slate-50 border border-slate-200 text-sm">
        <div class="font-medium text-slate-800 mb-2">What might be wrong (SKU integrity)</div>
        <ul class="space-y-1 text-slate-700 m-0 pl-4 list-disc">
          <li>Orphan policy SKUs: {{ summary.sku_integrity_highlights.orphan_planning_policy_sku_count }}</li>
          <li>Orphan demand (actuals) SKUs: {{ summary.sku_integrity_highlights.orphan_demand_actual_sku_distinct_count }}</li>
          <li>Orphan SOH SKUs: {{ summary.sku_integrity_highlights.orphan_inventory_snapshot_sku_distinct_count }}</li>
          <li v-if="summary.sku_integrity_highlights.orphan_demand_facts_sku_distinct_count != null">
            Orphan demand_facts SKUs: {{ summary.sku_integrity_highlights.orphan_demand_facts_sku_distinct_count }}
          </li>
        </ul>
        <p class="mt-2 mb-0 text-slate-600">{{ summary.sku_integrity_highlights.full_report_hint }}</p>
      </div>

      <p v-if="summary" class="mt-3 text-sm text-slate-600">
        Server environment: <code>{{ summary.environment }}</code>
        · Reset allowed:
        <strong :class="summary.reset_allowed ? 'text-green-700' : 'text-red-600'">{{ summary.reset_allowed ? 'yes' : 'no' }}</strong>
        <span v-if="summary.reset_blocked_reason"> — {{ summary.reset_blocked_reason }}</span>
      </p>
    </section>

    <!-- 3. Recommended action -->
    <section class="card card-body dm-reco" :class="recommendation.scopeId ? 'dm-reco--has-scope' : 'dm-reco--none'">
      <h2 class="section-title mb-2">Recommended action</h2>
      <p class="text-sm text-slate-700 m-0 mb-3">{{ recommendation.message }}</p>
      <div v-if="recommendation.scopeId" class="flex flex-wrap items-center gap-2">
        <span class="text-sm text-slate-600">Suggested scope:</span>
        <span class="dm-reco-chip">{{ scopeLabel(recommendation.scopeId) }}</span>
        <button type="button" class="text-sm text-blue-700 underline hover:no-underline" @click="applyRecommendedScope">
          Use this scope
        </button>
      </div>
    </section>

    <!-- 4. Scope selection -->
    <section class="card card-body">
      <h2 class="section-title mb-1">Reset scope</h2>
      <p class="text-sm text-slate-600 mb-3">
        Fixed server-side allowlists only (not custom SQL). Choose the smallest scope that fixes your issue; use full reset when the database looks polluted.
      </p>

      <div v-if="masterScopeWarning" class="dm-inline-warn mb-4" role="status">
        {{ masterScopeWarning }}
      </div>

      <div class="dm-scope-grid">
        <button
          v-for="opt in scopeOptions"
          :key="opt.id"
          type="button"
          class="dm-scope-card"
          :class="{
            'dm-scope-card--active': selectedScope === opt.id,
            'dm-scope-card--recommended': recommendation.scopeId === opt.id,
            'dm-scope-card--danger': opt.id === 'full_test_data',
          }"
          @click="selectedScope = opt.id"
        >
          <span class="dm-scope-card__title">{{ scopeLabel(opt.id) }}</span>
          <span v-if="recommendation.scopeId === opt.id" class="dm-scope-card__badge">Suggested</span>
          <span class="dm-scope-card__desc">{{ opt.description || SCOPE_LABELS[opt.id] }}</span>
        </button>
      </div>

      <div class="flex flex-wrap items-center gap-3 mt-4">
        <button
          type="button"
          class="btn-primary"
          :disabled="previewLoading"
          @click="loadPreview"
        >
          {{ previewLoading ? 'Loading…' : 'Refresh preview' }}
        </button>
        <span class="text-sm text-slate-500">
          Preview updates when you change scope. Large DBs: row counts can take several minutes — “Refresh state” finishes on its own.
        </span>
      </div>
      <OperationStatusPanel :operation="resetPreviewOperation.operation" class="mt-4" />
    </section>

    <!-- 5. Preview -->
    <section class="card card-body">
      <h2 class="section-title mb-2">Reset preview (dry run)</h2>
      <p class="text-sm text-slate-600 mb-3">No database changes. Technical table list is optional.</p>

      <template v-if="preview">
        <div class="dm-business-summary">
          <div class="font-medium text-slate-900 mb-1">What this reset clears</div>
          <p class="text-sm text-slate-700 m-0">{{ businessSummarySentence }}</p>
        </div>
        <p v-if="preview.scope_description" class="text-sm text-slate-600 mt-3 mb-0">{{ preview.scope_description }}</p>

        <button
          type="button"
          class="dm-details-toggle mt-4"
          @click="showTechnicalPreview = !showTechnicalPreview"
        >
          {{ showTechnicalPreview ? 'Hide' : 'Show' }} technical details (tables &amp; row counts)
        </button>

        <div v-show="showTechnicalPreview" class="mt-4 space-y-4">
          <div class="overflow-x-auto">
            <table class="app-table w-full text-sm">
              <thead>
                <tr>
                  <th class="text-left">Table</th>
                  <th class="text-right">Rows (before)</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in preview.affected_tables" :key="row.table">
                  <td><code>{{ row.table }}</code></td>
                  <td class="text-right">{{ row.row_count_before?.toLocaleString?.() ?? row.row_count_before }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="grid gap-4 md:grid-cols-2">
            <div>
              <div class="font-medium text-slate-800 mb-2">Preserved (reference)</div>
              <ul class="text-sm text-slate-700 m-0 pl-4 max-h-48 overflow-auto list-disc">
                <li v-for="p in preview.preserved_tables" :key="p.table">
                  <code>{{ p.table }}</code><span v-if="!p.present" class="text-slate-400"> (not in DB)</span>
                </li>
              </ul>
            </div>
            <div>
              <div class="font-medium text-slate-800 mb-2">Warnings</div>
              <ul class="text-sm text-amber-900 m-0 pl-4 list-disc">
                <li v-for="(w, i) in preview.warnings" :key="i">{{ w }}</li>
              </ul>
            </div>
          </div>
        </div>

        <p class="mt-4 text-sm text-slate-600">
          Required confirmation phrase:
          <code class="bg-slate-100 px-1 rounded">{{ preview.confirm_phrase_required }}</code>
        </p>
      </template>
      <p v-else-if="!previewLoading && !previewError" class="text-sm text-slate-500">
        Preview not loaded. Use <strong>Refresh preview</strong> or change scope.
      </p>
      <p v-else-if="previewLoading" class="text-sm text-slate-500">Loading preview…</p>
    </section>

    <!-- 6. Reset execution -->
    <section
      class="card card-body border-red-200 dm-reset-panel"
      :class="selectedScope === 'full_test_data' ? 'dm-reset-panel--full' : 'dm-reset-panel--scoped'"
    >
      <h2 class="section-title text-red-900 mb-2">Reset execution</h2>
      <p class="text-sm text-slate-800 mb-2">
        <span class="font-medium">You are about to reset:</span>
        {{ scopeLabel(preview?.scope || selectedScope) }}
        <span class="text-slate-500">(<code class="text-xs">{{ preview?.scope || selectedScope }}</code>)</span>
      </p>
      <p v-if="selectedScope === 'full_test_data'" class="text-sm font-semibold text-red-900 mb-2">
        Full test data is the most destructive scope — it removes products, warehouses, facts, plans, staging, and ingestion run metadata (per server allowlist).
      </p>
      <p class="text-sm text-red-800 mb-3">
        Identity, app settings, sku_code_map, suppliers, and forecast <em>config</em> rows stay unless the scope clears forecast run history.
      </p>
      <p class="text-sm text-slate-600 mb-3">
        Large databases may take several minutes to finish on the server. The button only reflects the reset request — data state cards refresh afterward and may lag slightly.
      </p>
      <p v-if="!previewLoaded" class="text-sm text-slate-600 mb-3">Wait for preview to finish loading for this scope.</p>
      <div v-else class="space-y-3 max-w-lg">
        <div>
          <label class="form-label">Type confirmation exactly (scope-specific)</label>
          <input
            v-model="confirmText"
            type="text"
            class="input w-full font-mono"
            autocomplete="off"
            :placeholder="preview?.confirm_phrase_required || '…'"
            :disabled="resetLoading || !preview?.reset_allowed"
          />
        </div>
        <button
          type="button"
          class="px-4 py-2 rounded-md text-white font-medium bg-red-700 hover:bg-red-800 disabled:opacity-45 disabled:cursor-not-allowed"
          :disabled="resetLoading || !canExecuteReset"
          @click="runReset"
        >
          {{ resetLoading ? 'Resetting…' : 'Execute reset' }}
        </button>
        <p v-if="!preview?.reset_allowed" class="text-sm text-red-700">Reset is disabled for this server environment.</p>
      </div>
      <OperationStatusPanel :operation="resetExecutionOperation.operation" class="mt-4">
        <template #retry>
          <button
            v-if="resetExecutionOperation.operation.status === 'timed_out'"
            type="button"
            class="btn-secondary"
            :disabled="previewLoading"
            @click="loadPreview"
          >
            Refresh preview before retrying
          </button>
        </template>
      </OperationStatusPanel>
    </section>

    <!-- 7. Reload checklist -->
    <section class="card card-body">
      <h2 class="section-title mb-2">After a reset — reload checklist</h2>
      <p class="text-sm text-slate-600 mb-4">
        Use this as a guide; check items off as you complete them. (Stored only in this browser session.)
      </p>
      <div class="dm-checklist">
        <div v-for="group in reloadChecklist" :key="group.title" class="dm-checklist__group">
          <div class="dm-checklist__group-title">{{ group.title }}</div>
          <ul class="dm-checklist__list">
            <li v-for="item in group.items" :key="item.id" class="dm-checklist__item">
              <label class="dm-checklist__label">
                <input v-model="item.done" type="checkbox" class="dm-checklist__cb" />
                <span>{{ item.label }}</span>
              </label>
            </li>
          </ul>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import OperationStatusPanel from '@/components/common/OperationStatusPanel.vue'
import { useOperation } from '@/composables/useOperation'
import api, {
  ADMIN_DATA_MANAGEMENT_READ_TIMEOUT_MS,
} from '../../api/client'

type CheckStatus = 'ok' | 'warning' | 'problem'

const EXPECTED = {
  productsMin: 100,
  productsMax: 200,
  warehousesMin: 1,
  warehousesMax: 5,
  suspiciousProducts: 0,
  suspiciousWarehouses: 0,
} as const

const SCOPE_LABELS: Record<string, string> = {
  full_test_data: 'Full test data (all platform tables)',
  planning_runs_only: 'Planning runs only',
  demand_and_sales: 'Demand & sales (facts + stage)',
  soh_inventory: 'SOH / inventory snapshots',
  policies: 'Planning policies only',
  product_master: 'Product master + SKU dependents',
  warehouse_master: 'Warehouse master + WH dependents',
  mappings: 'Warehouse mappings only',
  staging_and_rejections: 'Ingestion staging & runs',
  forecast_history: 'Forecast run history (engine + baseline)',
}

/** Business-facing phrases for preview summary (aligned with backend scopes, not raw SQL). */
const SCOPE_BUSINESS_CLEARS: Record<string, string[]> = {
  full_test_data: [
    'products',
    'warehouses',
    'planning runs and planned orders',
    'demand and sales facts (and related stage rows)',
    'SOH / inventory snapshots',
    'planning policies',
    'warehouse mappings',
    'ingestion staging and run logs',
    'baseline / weekly backbone and forecast run outputs (per allowlist)',
  ],
  planning_runs_only: ['planning runs', 'planned orders', 'plan run events and overrides'],
  demand_and_sales: ['demand actuals', 'weekly demand facts', 'demand and sales-out staging'],
  soh_inventory: ['inventory snapshots (daily/weekly)', 'SOH staging'],
  policies: ['planning policies'],
  product_master: [
    'planning outputs',
    'demand / SOH / receipts',
    'policies',
    'baseline and weekly backbone rows',
    'warehouse–product links and product attributes',
    'products',
  ],
  warehouse_master: [
    'planning outputs',
    'demand / SOH / receipts',
    'policies',
    'baseline and weekly backbone rows',
    'mappings and lanes',
    'warehouses',
  ],
  mappings: ['warehouse product codes', 'warehouse branch mapping'],
  staging_and_rejections: ['ingestion stage tables', 'rejections', 'ingestion run metadata'],
  forecast_history: [
    'published and baseline platform forecasts',
    'forecast run metrics',
    'forecast engine runs',
    'results',
    'diagnostics',
    'training series',
    'synced forecast sales/stock weekly tables (if present)',
  ],
}

function scopeLabel(id: string): string {
  return SCOPE_LABELS[id] || id
}

function formatInt(n: unknown): string {
  if (typeof n !== 'number') return String(n ?? '—')
  return n.toLocaleString()
}

function statusLabel(s: CheckStatus): string {
  if (s === 'ok') return 'OK'
  if (s === 'warning') return 'Warning'
  return 'Problem'
}

interface SkuIntegrityHighlights {
  orphan_planning_policy_sku_count: number
  orphan_demand_actual_sku_distinct_count: number
  orphan_inventory_snapshot_sku_distinct_count: number
  orphan_demand_facts_sku_distinct_count: number | null
  full_report_hint: string
}

interface DataManagementSummary extends Record<string, unknown> {
  environment?: string
  reset_allowed?: boolean
  reset_blocked_reason?: string | null
  sku_integrity_highlights?: SkuIntegrityHighlights
}

const refreshDataOperation = useOperation('Refresh data preview')
const resetPreviewOperation = useOperation('Reset preview')
const resetExecutionOperation = useOperation('Reset staging data')
const summaryLoading = refreshDataOperation.isRunning
const summary = ref<DataManagementSummary | null>(null)

const selectedScope = ref('full_test_data')
const scopeOptions = ref<{ id: string; confirm_phrase_required: string; description?: string }[]>([])

const previewLoading = resetPreviewOperation.isRunning
const previewError = computed(() =>
  resetPreviewOperation.operation.status === 'failed' || resetPreviewOperation.operation.status === 'timed_out',
)
const preview = ref<{
  scope: string
  scope_description?: string
  affected_tables: { table: string; row_count_before: number }[]
  preserved_tables: { table: string; present: boolean }[]
  warnings: string[]
  confirm_phrase_required: string
  reset_allowed: boolean
} | null>(null)

const showTechnicalPreview = ref(false)

const previewLoaded = computed(() => preview.value != null)
const confirmText = ref('')
const requiredPhrase = computed(() => (preview.value?.confirm_phrase_required || '').trim())
const canExecuteReset = computed(
  () =>
    previewLoaded.value &&
    preview.value?.reset_allowed === true &&
    requiredPhrase.value.length > 0 &&
    confirmText.value === requiredPhrase.value,
)

const resetLoading = resetExecutionOperation.isRunning

const n = (v: unknown) => (typeof v === 'number' ? v : 0)

const highlights = computed(() => {
  const h = summary.value?.sku_integrity_highlights as Record<string, unknown> | undefined
  return {
    orphanPolicy: n(h?.orphan_planning_policy_sku_count),
    orphanDemand: n(h?.orphan_demand_actual_sku_distinct_count),
    orphanSoh: n(h?.orphan_inventory_snapshot_sku_distinct_count),
    orphanFacts: h?.orphan_demand_facts_sku_distinct_count != null ? n(h?.orphan_demand_facts_sku_distinct_count) : 0,
    hasFacts: h?.orphan_demand_facts_sku_distinct_count != null,
  }
})

const totalOrphanSkus = computed(() => {
  const h = highlights.value
  return h.orphanPolicy + h.orphanDemand + h.orphanSoh + (h.hasFacts ? h.orphanFacts : 0)
})

const masterDataClean = computed(() => {
  if (!summary.value) return false
  const p = n(summary.value.product_count)
  const w = n(summary.value.warehouse_count)
  const sp = n(summary.value.suspicious_product_count)
  const sw = n(summary.value.suspicious_warehouse_count)
  return (
    sp === 0 &&
    sw === 0 &&
    p >= EXPECTED.productsMin &&
    p <= EXPECTED.productsMax &&
    w >= EXPECTED.warehousesMin &&
    w <= EXPECTED.warehousesMax
  )
})

const polluted = computed(() => {
  if (!summary.value) return false
  return (
    n(summary.value.suspicious_product_count) > EXPECTED.suspiciousProducts ||
    n(summary.value.suspicious_warehouse_count) > EXPECTED.suspiciousWarehouses ||
    n(summary.value.product_count) > EXPECTED.productsMax ||
    n(summary.value.warehouse_count) > EXPECTED.warehousesMax
  )
})

const recommendation = computed(() => {
  if (!summary.value) {
    return { scopeId: null as string | null, message: 'Refresh state to see a recommendation.' }
  }
  if (polluted.value) {
    return {
      scopeId: 'full_test_data',
      message:
        'Data looks polluted (suspicious rows or counts outside the expected test range). A full test-data reset is recommended before relying on this database.',
    }
  }

  const plan = n(summary.value.plan_run_count)
  const demand = n(summary.value.demand_row_count)
  const soh = n(summary.value.soh_weekly_row_count)
  const pol = n(summary.value.planning_policy_count)
  const onlyPlans = plan > 0 && demand === 0 && soh === 0 && pol === 0

  if (masterDataClean.value && onlyPlans) {
    return {
      scopeId: 'planning_runs_only',
      message:
        'Master data counts look normal and only planning runs are present. Clearing planning runs only is usually enough.',
    }
  }

  if (masterDataClean.value && plan === 0 && demand > 0 && soh === 0 && pol === 0) {
    return {
      scopeId: 'demand_and_sales',
      message: 'Demand/sales facts look populated while other areas are empty. Consider a demand & sales scoped reset.',
    }
  }

  if (masterDataClean.value && plan === 0 && demand === 0 && soh > 0 && pol === 0) {
    return {
      scopeId: 'soh_inventory',
      message: 'SOH snapshots are present without other signals. Consider an SOH/inventory scoped reset.',
    }
  }

  if (masterDataClean.value && plan === 0 && demand === 0 && soh === 0 && pol > 0) {
    return {
      scopeId: 'policies',
      message: 'Only planning policies are present. You can clear policies alone if that matches your test goal.',
    }
  }

  if (masterDataClean.value && totalOrphanSkus.value > 0) {
    return {
      scopeId: null,
      message:
        'Counts look in range but SKU integrity reports orphans. Review the report above, then pick a scope (often mappings, demand, SOH, policies, or full reset) based on what failed.',
    }
  }

  if (masterDataClean.value && plan > 0) {
    return {
      scopeId: 'planning_runs_only',
      message:
        'Master data looks fine and planning runs exist. Start by clearing planning runs; use additional scopes if facts or policies still look wrong.',
    }
  }

  if (!masterDataClean.value && !polluted.value) {
    return {
      scopeId: null,
      message:
        'Counts are outside the usual test band but not in the “polluted” rule set. Reload masters from source or choose a scope manually after preview.',
    }
  }

  return {
    scopeId: null,
    message: 'No reset recommended from automated rules. Use preview to confirm a manual scope if you still need a wipe.',
  }
})

const databaseCleanLabel = computed(() => {
  if (!summary.value) return '—'
  if (polluted.value) return 'Likely needs a full reset or master reload.'
  if (!masterDataClean.value) return 'Review counts — outside typical test band.'
  if (totalOrphanSkus.value > 0) return 'Mostly healthy counts; check SKU integrity.'
  return 'Counts look like a typical test database.'
})

function productCountStatus(p: number): { status: CheckStatus; hint: string } {
  if (p >= EXPECTED.productsMin && p <= EXPECTED.productsMax) {
    return { status: 'ok', hint: `Expected for this console: ${EXPECTED.productsMin}–${EXPECTED.productsMax}.` }
  }
  if (p === 0) {
    return { status: 'problem', hint: 'No products — load master or reset.' }
  }
  if (p < EXPECTED.productsMin) {
    return { status: 'warning', hint: `Below ${EXPECTED.productsMin}; may be empty or partial import.` }
  }
  return { status: 'warning', hint: `Above ${EXPECTED.productsMax}; may be polluted or non-test data.` }
}

function warehouseCountStatus(w: number): { status: CheckStatus; hint: string } {
  if (w >= EXPECTED.warehousesMin && w <= EXPECTED.warehousesMax) {
    return { status: 'ok', hint: `Expected: ${EXPECTED.warehousesMin}–${EXPECTED.warehousesMax}.` }
  }
  if (w === 0) {
    return { status: 'problem', hint: 'No warehouses — load master or reset.' }
  }
  if (w < EXPECTED.warehousesMin) {
    return { status: 'warning', hint: 'Fewer than expected test warehouses.' }
  }
  return { status: 'warning', hint: 'More than expected; check for extra test or prod-like rows.' }
}

function suspiciousStatus(count: number, kind: 'product' | 'warehouse'): { status: CheckStatus; hint: string } {
  if (count === 0) {
    return { status: 'ok', hint: `No heuristic-flagged test ${kind} patterns.` }
  }
  return { status: 'problem', hint: 'Heuristic matches — investigate or full reset.' }
}

function planningStatus(plan: number): { status: CheckStatus; hint: string } {
  if (plan === 0) return { status: 'ok', hint: 'No plan runs stored.' }
  if (plan < 50) return { status: 'warning', hint: 'Plan runs present — clear with planning scope if retesting.' }
  return { status: 'warning', hint: 'Many plan runs — consider planning or full reset.' }
}

function demandStatus(demand: number, orphanDemand: number): { status: CheckStatus; hint: string } {
  if (demand === 0 && orphanDemand === 0) return { status: 'ok', hint: 'No demand rows; no orphan demand SKUs flagged.' }
  if (orphanDemand > 0) return { status: 'problem', hint: 'Orphan demand SKUs — fix masters or scoped demand reset.' }
  if (demand > 0) return { status: 'warning', hint: 'Demand present — use demand scope if facts are wrong.' }
  return { status: 'ok', hint: '' }
}

function sohStatus(soh: number, orphanSoh: number): { status: CheckStatus; hint: string } {
  if (soh === 0 && orphanSoh === 0) return { status: 'ok', hint: 'No weekly SOH; no orphan SOH SKUs flagged.' }
  if (orphanSoh > 0) return { status: 'problem', hint: 'Orphan SOH SKUs — fix mappings/masters or SOH scope.' }
  if (soh > 0) return { status: 'warning', hint: 'SOH rows present — use SOH scope if snapshots are stale.' }
  return { status: 'ok', hint: '' }
}

function policiesStatus(pol: number, orphanPol: number): { status: CheckStatus; hint: string } {
  if (pol === 0 && orphanPol === 0) return { status: 'ok', hint: 'No policies; no orphan policy SKUs.' }
  if (orphanPol > 0) return { status: 'problem', hint: 'Policies reference missing SKUs — fix products or policies scope.' }
  if (pol > 0) return { status: 'warning', hint: 'Policies present — clear with policies scope if retesting.' }
  return { status: 'ok', hint: '' }
}

const stateCards = computed(() => {
  if (!summary.value) return []
  const p = n(summary.value.product_count)
  const w = n(summary.value.warehouse_count)
  const plan = n(summary.value.plan_run_count)
  const demand = n(summary.value.demand_row_count)
  const soh = n(summary.value.soh_weekly_row_count)
  const pol = n(summary.value.planning_policy_count)
  const sp = n(summary.value.suspicious_product_count)
  const sw = n(summary.value.suspicious_warehouse_count)
  const h = highlights.value

  const ps = productCountStatus(p)
  const ws = warehouseCountStatus(w)
  const pls = planningStatus(plan)
  const ds = demandStatus(demand, h.orphanDemand)
  const ss = sohStatus(soh, h.orphanSoh)
  const pos = policiesStatus(pol, h.orphanPolicy)
  const sps = suspiciousStatus(sp, 'product')
  const sws = suspiciousStatus(sw, 'warehouse')

  return [
    { key: 'products', label: 'Products', displayValue: formatInt(p), status: ps.status, statusLabel: statusLabel(ps.status), hint: ps.hint },
    { key: 'warehouses', label: 'Warehouses', displayValue: formatInt(w), status: ws.status, statusLabel: statusLabel(ws.status), hint: ws.hint },
    { key: 'planning', label: 'Planning data', displayValue: `${formatInt(plan)} runs`, status: pls.status, statusLabel: statusLabel(pls.status), hint: pls.hint },
    { key: 'demand', label: 'Demand / sales', displayValue: `${formatInt(demand)} rows`, status: ds.status, statusLabel: statusLabel(ds.status), hint: ds.hint },
    { key: 'soh', label: 'SOH', displayValue: `${formatInt(soh)} weekly rows`, status: ss.status, statusLabel: statusLabel(ss.status), hint: ss.hint },
    { key: 'policies', label: 'Policies', displayValue: formatInt(pol), status: pos.status, statusLabel: statusLabel(pos.status), hint: pos.hint },
    { key: 'susp_p', label: 'Suspicious products', displayValue: formatInt(sp), status: sps.status, statusLabel: statusLabel(sps.status), hint: sps.hint },
    { key: 'susp_w', label: 'Suspicious warehouses', displayValue: formatInt(sw), status: sws.status, statusLabel: statusLabel(sws.status), hint: sws.hint },
  ]
})

const businessSummarySentence = computed(() => {
  const id = preview.value?.scope || selectedScope.value
  const parts = SCOPE_BUSINESS_CLEARS[id]
  if (!parts?.length) return 'See technical details for affected tables.'
  return `This reset will clear: ${parts.join(', ')}.`
})

const masterScopeWarning = computed(() => {
  if (selectedScope.value === 'product_master') {
    return 'This scope removes products and dependent planning and fact data. Prefer full test data unless you intentionally refresh SKU master only.'
  }
  if (selectedScope.value === 'warehouse_master') {
    return 'This scope removes warehouses and dependent planning and fact data. Prefer full test data unless you intentionally refresh site master only.'
  }
  return ''
})

type ChecklistItem = { id: string; label: string; done: boolean }
type ChecklistGroup = { title: string; items: ChecklistItem[] }

const reloadChecklist = reactive<ChecklistGroup[]>([
  {
    title: 'Master data',
    items: [
      { id: 'm1', label: 'Product master (ingestion)', done: false },
      { id: 'm2', label: 'Warehouse master', done: false },
    ],
  },
  {
    title: 'Mappings',
    items: [{ id: 'g1', label: 'Warehouse product / branch / code mappings', done: false }],
  },
  {
    title: 'Facts',
    items: [
      { id: 'f1', label: 'Sales / demand actuals', done: false },
      { id: 'f2', label: 'SOH / inventory snapshots', done: false },
    ],
  },
  {
    title: 'Policies',
    items: [{ id: 'p1', label: 'Planning policies', done: false }],
  },
  {
    title: 'Validation',
    items: [
      { id: 'v1', label: 'Data health / SKU integrity report', done: false },
      { id: 'v2', label: 'Re-check this Data state console', done: false },
    ],
  },
  {
    title: 'Test runs',
    items: [
      { id: 't1', label: 'Stock-aware test plan run', done: false },
      { id: 't2', label: 'Demand-only test plan run', done: false },
    ],
  },
])

function applyRecommendedScope() {
  const id = recommendation.value.scopeId
  if (id && scopeOptions.value.some((o) => o.id === id)) {
    selectedScope.value = id
  }
}

async function loadSummary() {
  const scopeBefore = selectedScope.value
  const data = await refreshDataOperation.runWithOperation(
    'Refresh data preview',
    async () => {
      try {
        const response = await api.get<Record<string, unknown>>('/admin/data-management/summary', {
          timeout: ADMIN_DATA_MANAGEMENT_READ_TIMEOUT_MS,
        })
        return response.data
      } catch (e: unknown) {
        throw new Error(errMsg(e))
      }
    },
    {
      runningMessage: 'Refreshing database state...',
      successMessage: 'Data state refreshed.',
      timeoutMessage: 'The request did not return in time. Refresh data preview before retrying.',
      nextActions: ['Refresh data preview before retrying.'],
    },
  )
  if (!data) return
  summary.value = data
  const scopes = data.available_scopes as { id: string; confirm_phrase_required: string; description?: string }[] | undefined
  if (Array.isArray(scopes) && scopes.length) {
    scopeOptions.value = scopes
    if (!scopes.some((s) => s.id === selectedScope.value)) {
      selectedScope.value = scopes[0].id
    }
  }
  if (selectedScope.value === scopeBefore) {
    void loadPreview()
  }
}

async function loadPreview() {
  const data = await resetPreviewOperation.runWithOperation(
    'Reset preview',
    async () => {
      try {
        const response = await api.get<NonNullable<typeof preview.value>>(
          '/admin/data-management/reset-preview',
          {
            params: { scope: selectedScope.value },
            timeout: ADMIN_DATA_MANAGEMENT_READ_TIMEOUT_MS,
          },
        )
        return response.data
      } catch (e: unknown) {
        throw new Error(errMsg(e))
      }
    },
    {
      runningMessage: `Loading reset preview for ${scopeLabel(selectedScope.value)}...`,
      successMessage: 'Reset preview refreshed.',
      timeoutMessage: 'The request did not return in time. Refresh preview before retrying.',
      nextActions: ['Refresh preview before retrying.'],
    },
  )
  if (!data) return
  preview.value = data
  confirmText.value = ''
}

watch(selectedScope, () => {
  preview.value = null
  confirmText.value = ''
  resetPreviewOperation.resetOperation('Reset preview')
  void loadPreview()
})

/** Readable reset error from FastAPI detail (string or object). */
function formatResetDetail(detail: unknown): string {
  if (detail == null) return 'Request failed'
  if (typeof detail === 'string') return detail
  if (typeof detail === 'object' && detail !== null) {
    const o = detail as Record<string, unknown>
    const parts: string[] = []
    if (typeof o.message === 'string') parts.push(o.message)
    if (o.lock_timeout === true) {
      parts.push('(HTTP 503 — lock timeout: close other sessions using this database, then retry.)')
    }
    if (o.partial_reset === true && Array.isArray(o.deleted_tables_committed) && o.deleted_tables_committed.length) {
      parts.push(
        `Partial reset: these tables were already cleared before the failure: ${(o.deleted_tables_committed as string[]).join(', ')}.`,
      )
    }
    if (parts.length) return parts.join('\n\n')
    try {
      return JSON.stringify(detail, null, 2)
    } catch {
      return String(detail)
    }
  }
  return String(detail)
}

function errMsg(e: unknown): string {
  const ax = e as {
    code?: string
    message?: string
    response?: { data?: { detail?: unknown } }
  }
  const msg = ax.message?.toLowerCase() ?? ''
  if (ax.code === 'ECONNABORTED' || msg.includes('timeout')) {
    return 'Request timed out. The database may be very large — try again, pick a smaller reset scope for preview, or check API/MySQL load.'
  }
  const d = ax.response?.data?.detail
  if (typeof d === 'string') return d
  if (d && typeof d === 'object' && 'message' in d) return String((d as { message: string }).message)
  return e instanceof Error ? e.message : 'Request failed'
}

async function runReset() {
  const scope = preview.value?.scope || selectedScope.value
  const data = await resetExecutionOperation.runWithOperation(
    scope === 'staging_and_rejections' ? 'Reset staging data' : `Reset ${scopeLabel(scope)}`,
    async () => {
      try {
        const response = await api.post('/admin/data-management/reset', {
          scope,
          confirm_text: confirmText.value,
        })
        return response.data as Record<string, unknown>
      } catch (e: unknown) {
        const ax = e as { response?: { data?: { detail?: unknown } } }
        throw new Error(formatResetDetail(ax.response?.data?.detail ?? errMsg(e)))
      }
    },
    {
      runningMessage: `Resetting ${scopeLabel(scope)}...`,
      successMessage: (result) => {
        const message = result && typeof result === 'object' ? (result as Record<string, unknown>).message : null
        return typeof message === 'string' ? message : 'Reset completed.'
      },
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh preview before retrying.',
      nextActions: ['Refresh preview before retrying.', 'Check the preview counts before starting another reset.'],
    },
  )
  if (!data) return
  resetExecutionOperation.completeOperation({
    message: typeof data.message === 'string' ? data.message : 'Reset completed.',
    technicalDetails: data,
  })
  confirmText.value = ''
  for (const g of reloadChecklist) {
    for (const it of g.items) it.done = false
  }
  void loadSummary()
}

onMounted(() => {
  void loadSummary()
})
</script>

<style scoped>
.dm-banner {
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
  border: 1px solid rgb(251 191 36);
  background: rgb(254 252 232);
  color: rgb(113 63 18);
  font-size: 0.875rem;
  line-height: 1.45;
}
.dm-banner code {
  font-size: 0.8125rem;
  background: rgb(254 243 199);
  padding: 0.05rem 0.35rem;
  border-radius: 0.25rem;
}

.dm-console-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(11.5rem, 1fr));
  gap: 0.75rem;
}
.dm-console-card {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.5rem;
  padding: 0.75rem;
  background: rgb(255 255 255);
  text-align: left;
}
.dm-console-card--ok {
  border-color: rgb(167 243 208);
  background: rgb(240 253 244);
}
.dm-console-card--warning {
  border-color: rgb(253 224 71);
  background: rgb(254 252 232);
}
.dm-console-card--problem {
  border-color: rgb(252 165 165);
  background: rgb(254 242 242);
}
.dm-console-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.35rem;
}
.dm-console-card__label {
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: rgb(100 116 139);
}
.dm-console-card__value {
  font-size: 1.2rem;
  font-weight: 700;
  color: rgb(30 41 59);
  margin-top: 0.35rem;
}
.dm-console-card__hint {
  font-size: 0.75rem;
  color: rgb(71 85 105);
  margin: 0.35rem 0 0;
  line-height: 1.35;
}
.dm-status-pill {
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  padding: 0.15rem 0.4rem;
  border-radius: 999px;
  background: rgb(241 245 249);
  color: rgb(71 85 105);
}
.dm-status-pill--ok {
  background: rgb(209 250 229);
  color: rgb(6 95 70);
}
.dm-status-pill--warning {
  background: rgb(254 249 195);
  color: rgb(113 63 18);
}
.dm-status-pill--problem {
  background: rgb(254 226 226);
  color: rgb(127 29 29);
}

.dm-reco {
  border: 1px solid rgb(226 232 240);
}
.dm-reco--has-scope {
  border-color: rgb(165 180 252);
  background: rgb(238 242 255);
}
.dm-reco--none {
  background: rgb(248 250 252);
}
.dm-reco-chip {
  font-size: 0.8125rem;
  font-weight: 600;
  padding: 0.2rem 0.55rem;
  border-radius: 0.35rem;
  background: rgb(224 231 255);
  color: rgb(49 46 129);
}

.dm-inline-warn {
  font-size: 0.875rem;
  padding: 0.65rem 0.85rem;
  border-radius: 0.5rem;
  border: 1px solid rgb(253 186 116);
  background: rgb(255 247 237);
  color: rgb(124 45 18);
}

.dm-scope-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
  gap: 0.65rem;
}
.dm-scope-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  text-align: left;
  border: 1px solid rgb(226 232 240);
  border-radius: 0.5rem;
  padding: 0.75rem 0.85rem;
  background: rgb(255 255 255);
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.dm-scope-card:hover {
  border-color: rgb(148 163 184);
}
.dm-scope-card--active {
  border-color: rgb(59 130 246);
  box-shadow: 0 0 0 1px rgb(59 130 246);
}
.dm-scope-card--recommended:not(.dm-scope-card--active) {
  border-color: rgb(129 140 248);
  background: rgb(245 243 255);
}
.dm-scope-card--danger.dm-scope-card--active {
  border-color: rgb(220 38 38);
  box-shadow: 0 0 0 1px rgb(220 38 38);
}
.dm-scope-card__title {
  font-size: 0.875rem;
  font-weight: 600;
  color: rgb(30 41 59);
}
.dm-scope-card__badge {
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  margin-top: 0.25rem;
  color: rgb(67 56 202);
}
.dm-scope-card__desc {
  font-size: 0.75rem;
  color: rgb(100 116 139);
  margin-top: 0.35rem;
  line-height: 1.35;
}

.dm-business-summary {
  padding: 0.85rem 1rem;
  border-radius: 0.5rem;
  border: 1px solid rgb(226 232 240);
  background: rgb(248 250 252);
}

.dm-details-toggle {
  font-size: 0.875rem;
  color: rgb(29 78 216);
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  text-decoration: underline;
}
.dm-details-toggle:hover {
  color: rgb(30 64 175);
}

.dm-reset-panel--full {
  background: rgb(254 242 242);
}
.dm-reset-panel--scoped {
  background: rgb(255 247 237);
}

.dm-checklist__group {
  margin-bottom: 1rem;
}
.dm-checklist__group-title {
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: rgb(100 116 139);
  margin-bottom: 0.35rem;
}
.dm-checklist__list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.dm-checklist__item + .dm-checklist__item {
  margin-top: 0.35rem;
}
.dm-checklist__label {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: rgb(51 65 85);
  cursor: pointer;
}
.dm-checklist__cb {
  margin-top: 0.15rem;
}
</style>
