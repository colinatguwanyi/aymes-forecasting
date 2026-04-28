<template>
  <div class="page-shell space-y-6">
    <header class="page-header">
      <h1>Forecast Check</h1>
      <p class="muted mt-1 max-w-3xl">
        One plain-English check for whether planners should trust today&apos;s forecast.
      </p>
    </header>

    <section v-if="loading" class="card card-body">
      <p class="muted m-0">Checking forecast readiness...</p>
    </section>

    <section v-else-if="loadError" class="card card-body border-red-200 bg-red-50/60">
      <h2 class="text-base font-semibold text-red-900 m-0 mb-1">Forecast status: Blocked</h2>
      <p class="text-sm text-red-800 m-0 mb-3">{{ loadError }}</p>
      <button type="button" class="btn-secondary" @click="loadCheck">Try again</button>
    </section>

    <template v-else-if="check">
      <section class="forecast-check-banner" :class="bannerClass" role="status">
        <div>
          <p class="text-xs font-semibold uppercase tracking-wide m-0 mb-1">{{ bannerKicker }}</p>
          <h2 class="text-2xl font-semibold m-0">{{ check.headline }}</h2>
        </div>
        <span class="forecast-check-banner__badge">{{ overallLabel }}</span>
      </section>

      <section class="forecast-check-grid" aria-label="Forecast checks">
        <article
          v-for="card in cards"
          :key="card.title"
          class="card card-body forecast-check-card"
        >
          <div class="flex items-start justify-between gap-3">
            <h2 class="text-base font-semibold text-slate-900 m-0">{{ card.title }}</h2>
            <span :class="statusBadgeClass(card.status)">{{ statusLabel(card.status) }}</span>
          </div>
          <p v-if="card.latest" class="text-sm text-slate-500 m-0 mt-3">{{ card.latest }}</p>
          <p class="text-sm text-slate-800 m-0 mt-2 leading-relaxed">{{ card.message }}</p>
          <p v-if="card.detail" class="text-xs text-slate-500 m-0 mt-3">{{ card.detail }}</p>
        </article>
      </section>

      <section class="card card-body" aria-labelledby="forecast-actions-heading">
        <h2 id="forecast-actions-heading" class="text-base font-semibold text-slate-900 m-0 mb-3">
          What to do next
        </h2>
        <ol class="forecast-actions">
          <li v-for="action in check.actions" :key="action">{{ action }}</li>
        </ol>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  fetchForecastCheck,
  type ForecastCheck,
  type ForecastCheckStatus,
} from '@/api/client'

interface CheckCard {
  title: string
  status: ForecastCheckStatus
  latest?: string
  message: string
  detail?: string
}

const loading = ref(true)
const loadError = ref<string | null>(null)
const check = ref<ForecastCheck | null>(null)

const overallLabel = computed(() => (check.value ? statusLabel(check.value.overall_status) : 'Blocked'))
const bannerKicker = computed(() => {
  if (check.value?.overall_status === 'green') return 'Ready to use'
  if (check.value?.overall_status === 'amber') return 'Needs attention'
  return 'Do not rely on it yet'
})
const bannerClass = computed(() => `forecast-check-banner--${check.value?.overall_status ?? 'red'}`)

const cards = computed<CheckCard[]>(() => {
  if (!check.value) return []
  const c = check.value
  return [
    {
      title: 'Sales Out',
      status: c.sales_freshness.status,
      latest: latestLabel('Latest sales week', c.sales_freshness.latest_week),
      message: c.sales_freshness.message,
      detail: `${formatInt(c.sales_freshness.sku_count)} SKUs, ${formatInt(c.sales_freshness.weeks_available)} weeks available`,
    },
    {
      title: 'Stock On Hand',
      status: c.soh_freshness.status,
      latest: latestLabel('Latest stock week', c.soh_freshness.latest_week),
      message: c.soh_freshness.message,
      detail: `${formatInt(c.soh_freshness.sku_count)} SKUs with stock`,
    },
    {
      title: 'Forecast Run',
      status: c.forecast_run.status,
      latest: c.forecast_run.inference_date ? `Inference date: ${c.forecast_run.inference_date}` : 'Inference date: -',
      message: c.forecast_run.message,
      detail: c.forecast_run.latest_run_id
        ? `Run #${c.forecast_run.latest_run_id}${c.forecast_run.completed_at ? ` completed ${formatDateTime(c.forecast_run.completed_at)}` : ''}`
        : 'No completed run found',
    },
    {
      title: 'Plan Alignment',
      status: c.planning_alignment.status,
      latest: latestLabel('Latest baseline', c.planning_alignment.latest_baseline),
      message: c.planning_alignment.message,
      detail: `Plan baseline: ${c.planning_alignment.latest_plan_baseline ?? '-'}`,
    },
    {
      title: 'Data Coverage',
      status: c.sku_data_coverage.status,
      message: c.sku_data_coverage.message,
      detail: coverageDetail(c.sku_data_coverage),
    },
  ]
})

function latestLabel(label: string, value: string | null): string {
  return `${label}: ${value ?? '-'}`
}

function formatInt(n: number): string {
  return Number.isFinite(n) ? n.toLocaleString() : String(n)
}

function formatPercent(n: number | null): string {
  if (n == null || !Number.isFinite(n)) return '-'
  return `${Math.round(n * 100)}%`
}

function formatDateTime(value: string): string {
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function coverageDetail(coverage: ForecastCheck['sku_data_coverage']): string {
  return [
    `${formatInt(coverage.orphan_sku_count)} orphan SKU references`,
    `${formatInt(coverage.policy_gaps)} policy gaps`,
    `${formatInt(coverage.demand_without_soh_count ?? 0)} demand pairs without stock (${formatPercent(coverage.demand_without_soh_ratio)})`,
  ].join(' / ')
}

function statusLabel(status: ForecastCheckStatus): string {
  if (status === 'green') return 'OK'
  if (status === 'amber') return 'Warning'
  return 'Blocked'
}

function statusBadgeClass(status: ForecastCheckStatus): string {
  if (status === 'green') return 'badge-success'
  if (status === 'amber') return 'badge-warn'
  return 'badge-danger'
}

async function loadCheck(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    check.value = await fetchForecastCheck()
  } catch (e: unknown) {
    check.value = null
    loadError.value = e instanceof Error ? e.message : 'Could not complete the forecast check.'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadCheck()
})
</script>

<style scoped>
.forecast-check-banner {
  border-radius: 1rem;
  border: 1px solid;
  padding: 1.25rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.forecast-check-banner--green {
  background: rgb(236 253 245);
  border-color: rgb(167 243 208);
  color: rgb(6 78 59);
}

.forecast-check-banner--amber {
  background: rgb(255 251 235);
  border-color: rgb(252 211 77);
  color: rgb(120 53 15);
}

.forecast-check-banner--red {
  background: rgb(254 242 242);
  border-color: rgb(252 165 165);
  color: rgb(127 29 29);
}

.forecast-check-banner__badge {
  border-radius: 999px;
  background: rgb(255 255 255 / 0.78);
  padding: 0.4rem 0.75rem;
  font-size: 0.875rem;
  font-weight: 700;
  white-space: nowrap;
}

.forecast-check-grid {
  display: grid;
  grid-template-columns: repeat(1, minmax(0, 1fr));
  gap: 1rem;
}

.forecast-check-card {
  min-height: 10rem;
}

.forecast-actions {
  margin: 0;
  padding-left: 1.25rem;
  color: rgb(51 65 85);
  font-size: 0.925rem;
}

.forecast-actions li + li {
  margin-top: 0.5rem;
}

@media (min-width: 768px) {
  .forecast-check-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (min-width: 1280px) {
  .forecast-check-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
