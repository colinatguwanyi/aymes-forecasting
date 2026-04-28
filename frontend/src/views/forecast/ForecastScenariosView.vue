<template>
  <div class="page-shell space-y-6">
    <header class="page-header">
      <h1>Forecast scenarios</h1>
      <p class="muted mt-1 max-w-3xl m-0">
        <strong>Scenarios</strong> here mean <strong>plan runs</strong> — named supply-planning snapshots (baseline, blended, actuals, etc.) that combine demand inputs,
        policies, and inventory so you can compare stock risk, exceptions, and orders side by side. Picking or pinning a
        <strong>baseline forecast run</strong> tells a scenario which published weekly forecast to use when demand is driven by forecast rather than raw actuals.
      </p>
    </header>

    <section class="card card-body text-sm space-y-4" aria-labelledby="concepts-heading">
      <h2 id="concepts-heading" class="text-base font-medium text-slate-800 m-0">How the pieces fit together</h2>
      <ul class="list-disc pl-5 space-y-2 text-slate-700 m-0">
        <li>
          <strong>Baseline forecast runs</strong> (published weekly forecasts by training week) are listed and pinned from
          <router-link to="/planning/scenario-manager" class="text-primary-600 hover:underline">Scenario Manager</router-link>
          and on the
          <router-link to="/forecast/dashboard" class="text-primary-600 hover:underline">Forecast dashboard</router-link>.
          They are the demand signal when a plan run uses baseline or blended demand — not the same thing as a MySQL engine batch job.
        </li>
        <li>
          <strong>Planning scenarios</strong> are individual <strong>plan runs</strong>: each has a scenario name, run date, demand source, freeze settings, and optional warehouse scope.
          You create them from the supply dashboard, then manage freeze/recalc and forecast pinning in Scenario Manager, and view grids or projections by selecting that run.
        </li>
        <li>
          <strong>Exports</strong> are CSVs and files derived from a chosen plan run (projected inventory, planned orders, exceptions) under
          <router-link to="/exports" class="text-primary-600 hover:underline">Planning exports</router-link>,
          or engine / legacy forecast files from
          <router-link to="/forecast/exports" class="text-primary-600 hover:underline">Forecast export</router-link>
          and
          <router-link to="/admin/forecast-engine" class="text-primary-600 hover:underline">Forecast Settings</router-link>.
        </li>
      </ul>
    </section>

    <section aria-labelledby="actions-heading">
      <h2 id="actions-heading" class="text-base font-medium text-slate-800 mb-3">Where to go next</h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        <router-link
          v-for="item in actionCards"
          :key="item.to"
          :to="item.to"
          class="card card-body block no-underline text-inherit transition-shadow hover:shadow-md hover:border-primary-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
        >
          <h3 class="text-sm font-semibold text-primary-800 mb-1">{{ item.title }}</h3>
          <p class="text-sm text-slate-600 m-0">{{ item.blurb }}</p>
        </router-link>
      </div>
    </section>

    <section class="card card-body" aria-labelledby="recent-heading">
      <h2 id="recent-heading" class="text-base font-medium text-slate-800 mb-1">Recent plan runs</h2>
      <p class="text-xs text-slate-500 m-0 mb-3">
        Newest first from <code class="bg-slate-100 px-1 rounded">GET /plan/runs</code> (same list as Scenario Manager). Open a run in the planning grid when you want a pre-selected scenario.
      </p>
      <div v-if="loadState === 'loading'" class="muted text-sm m-0">Loading plan runs…</div>
      <div v-else-if="loadState === 'error'" class="rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2 text-sm text-slate-800">
        <p class="m-0 mb-2">{{ loadError || 'Could not load plan runs.' }}</p>
        <button type="button" class="btn-secondary text-sm" @click="load">Retry</button>
      </div>
      <p v-else-if="!recentScenarios.length" class="muted text-sm m-0">
        No plan runs yet. Create one from the
        <router-link to="/" class="text-primary-600 hover:underline">Supply Dashboard</router-link>,
        then manage freezes and forecast pinning in Scenario Manager.
      </p>
      <div v-else class="app-table-wrap">
        <table class="app-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Scenario</th>
              <th>Demand source</th>
              <th>Run date</th>
              <th>Plan start</th>
              <th>Baseline week</th>
              <th>Created</th>
              <th>Created by</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in recentScenarios" :key="r.id">
              <td class="text-slate-800">{{ formatPlanRunLabel(r) }}</td>
              <td>{{ r.scenario_name }}</td>
              <td class="text-slate-600">{{ r.demand_source ?? '—' }}</td>
              <td class="tabular-nums text-sm text-slate-600">{{ fmtDateOnly(r.run_at) }}</td>
              <td class="tabular-nums text-sm text-slate-600">{{ fmtDateOnly(r.plan_start_week_start) }}</td>
              <td class="tabular-nums text-sm text-slate-600">{{ fmtDateOnly(r.baseline_train_end_week_start ?? r.selected_train_end_week_start) }}</td>
              <td class="text-sm text-slate-600">{{ fmtDateTime(r.created_at) }}</td>
              <td class="text-sm text-slate-600">{{ r.created_by?.trim() || '—' }}</td>
              <td>
                <router-link
                  class="text-primary-600 hover:underline text-sm whitespace-nowrap"
                  :to="{ path: '/planning-grid', query: { plan_run_id: String(r.id) } }"
                >
                  Planning grid
                </router-link>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { usePlanningStore } from '@/stores/planning'
import type { PlanRun } from '@/api/client'
import { formatPlanRunLabel } from '@/api/client'

/** Fields returned by PlanRunSchema; global `PlanRun` type may omit some. */
type PlanRunRow = PlanRun & {
  plan_start_week_start?: string | null
  created_by?: string | null
}

const store = usePlanningStore()

const loadState = ref<'loading' | 'ok' | 'error'>('loading')
const loadError = ref<string | null>(null)

const RECENT_LIMIT = 10

const recentScenarios = computed(() => (store.planRuns as PlanRunRow[]).slice(0, RECENT_LIMIT))

const actionCards = [
  {
    to: '/planning/scenario-manager',
    title: 'Scenario Manager',
    blurb: 'Freeze demand, recalculate, pin baseline forecast weeks, compare two runs, and view forecast health.',
  },
  {
    to: '/forecast/runs',
    title: 'Run forecast',
    blurb: 'See MySQL forecast engine runs and status; full console in Forecast Settings.',
  },
  {
    to: '/forecast/exports',
    title: 'Forecast export',
    blurb: 'Pointers to engine and legacy forecast file exports.',
  },
  {
    to: '/exports',
    title: 'Planning exports',
    blurb: 'Download CSVs for a selected plan run: projected inventory, orders, exceptions, and more.',
  },
  {
    to: '/forecast/dashboard',
    title: 'Forecast dashboard',
    blurb: 'Overview and latest published baseline week for planning (warehouse-scoped).',
  },
  {
    to: '/admin/forecast-engine',
    title: 'Forecast Settings',
    blurb: 'Engine configs, execute runs, diagnostics, supply-adjusted output, and legacy writes.',
  },
] as const

function fmtDateOnly(d: string | null | undefined): string {
  if (d == null || String(d).trim() === '') return '—'
  const s = String(d)
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10)
  const x = new Date(s)
  if (Number.isNaN(x.getTime())) return s
  return x.toISOString().slice(0, 10)
}

function fmtDateTime(iso: string | null | undefined): string {
  if (iso == null || String(iso).trim() === '') return '—'
  const x = new Date(iso)
  if (Number.isNaN(x.getTime())) return String(iso)
  return x.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

async function load(): Promise<void> {
  loadState.value = 'loading'
  loadError.value = null
  try {
    await store.fetchPlanRuns()
    loadState.value = 'ok'
  } catch (e: unknown) {
    loadState.value = 'error'
    const msg = e && typeof e === 'object' && 'response' in e
      ? (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      : undefined
    const detailStr = typeof msg === 'string' ? msg : msg != null ? JSON.stringify(msg) : null
    loadError.value = detailStr || (e instanceof Error ? e.message : 'Request failed.')
  }
}

onMounted(() => {
  void load()
})
</script>
