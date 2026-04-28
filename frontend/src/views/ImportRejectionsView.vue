<template>
  <div class="page-shell space-y-6">
    <header class="page-header">
      <h1>Import rejections</h1>
      <p class="muted mt-1">
        Summarize a run’s rejected rows, fix missing products or mappings, then re-import or re-execute from
        <router-link to="/imports">Imports</router-link>.
      </p>
    </header>

    <section class="card card-body space-y-4">
      <div class="flex flex-wrap items-end gap-4">
        <div class="min-w-64 flex-1">
          <label class="form-label">Ingestion run</label>
          <select v-model="selectedRunId" class="select w-full" @change="onRunChange">
            <option value="">Select a run…</option>
            <option v-for="r in demandRuns" :key="r.id" :value="r.id">
              {{ r.id.slice(0, 8) }} · {{ r.status }} · {{ r.file_name || '—' }} · rejected
              {{ r.rejected_count?.toLocaleString() ?? 0 }}
            </option>
          </select>
        </div>
        <button type="button" class="btn-secondary" :disabled="!selectedRunId || loading" @click="loadSummary">
          Refresh summary
        </button>
        <button
          type="button"
          class="btn-secondary"
          :disabled="!selectedRunId || exportBusy"
          @click="downloadExport"
        >
          Download all rejections (CSV)
        </button>
      </div>
      <p v-if="loadError" class="text-sm text-red-600">{{ loadError }}</p>
    </section>

    <section v-if="summary && !loading" class="space-y-4">
      <div class="card card-body">
        <h2 class="text-base font-semibold text-slate-800">Run overview</h2>
        <dl class="mt-2 grid gap-2 text-sm sm:grid-cols-2">
          <div><dt class="text-slate-500 inline">Entity</dt> <dd class="inline font-medium">{{ summary.entity }}</dd></div>
          <div><dt class="text-slate-500 inline">Status</dt> <dd class="inline font-medium">{{ summary.status }}</dd></div>
          <div class="sm:col-span-2">
            <dt class="text-slate-500 inline">File</dt>
            <dd class="inline font-medium">{{ summary.file_name || '—' }}</dd>
          </div>
          <div>
            <dt class="text-slate-500 inline">Total rejections</dt>
            <dd class="inline font-medium tabular-nums">{{ summary.total_rejections?.toLocaleString() }}</dd>
          </div>
        </dl>
      </div>

      <div v-if="summary.by_reason?.length" class="card card-body">
        <h2 class="text-base font-semibold text-slate-800">By reason</h2>
        <ul class="mt-2 divide-y divide-slate-100 text-sm">
          <li v-for="(row, i) in summary.by_reason" :key="i" class="flex justify-between py-2 gap-4">
            <span class="text-slate-700 break-all">{{ row.reason }}</span>
            <span class="tabular-nums font-medium shrink-0">{{ row.count?.toLocaleString() }}</span>
          </li>
        </ul>
      </div>

      <div v-if="summary.demand_sku_not_found?.length" class="card card-body space-y-3">
        <div>
          <h2 class="text-base font-semibold text-slate-800">Missing or inactive SKUs</h2>
          <p class="text-sm text-slate-600 mt-1">{{ summary.hints?.sku_not_found }}</p>
        </div>
        <p class="text-xs text-slate-500">
          After adding products or mappings:
          <router-link class="underline" to="/imports">Imports</router-link>
          → re-upload demand, or run transform again if staging is still valid.
        </p>
        <div class="overflow-x-auto">
          <table class="app-table text-sm">
            <thead>
              <tr>
                <th>SKU (from file)</th>
                <th>After code map</th>
                <th>Warehouse</th>
                <th>Demand type</th>
                <th class="text-right">Rows</th>
                <th>Sample weeks</th>
                <th class="w-40">Next steps</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in summary.demand_sku_not_found" :key="i">
                <td class="font-mono">{{ row.sku_raw || '—' }}</td>
                <td class="font-mono text-slate-600">{{ row.sku_after_code_map || '—' }}</td>
                <td>{{ row.warehouse_code || '—' }}</td>
                <td>{{ row.demand_type || '—' }}</td>
                <td class="text-right tabular-nums">{{ row.rejection_count?.toLocaleString() }}</td>
                <td class="text-xs text-slate-600">{{ (row.sample_week_starts || []).join(', ') }}</td>
                <td>
                  <router-link
                    class="text-xs text-indigo-600 hover:underline block"
                    :to="{ path: '/admin/products' }"
                  >
                    Products
                  </router-link>
                  <router-link
                    class="text-xs text-indigo-600 hover:underline block"
                    :to="{ path: '/admin/warehouse-product-codes' }"
                  >
                    WH codes
                  </router-link>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="summary.demand_insufficient_history?.length" class="card card-body space-y-3">
        <div>
          <h2 class="text-base font-semibold text-slate-800">Insufficient history</h2>
          <p class="text-sm text-slate-600 mt-1">{{ summary.hints?.insufficient_history }}</p>
        </div>
        <div class="overflow-x-auto">
          <table class="app-table text-sm">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Warehouse</th>
                <th>Demand type</th>
                <th class="text-right">Series</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in summary.demand_insufficient_history" :key="i">
                <td class="font-mono">{{ row.sku }}</td>
                <td>{{ row.warehouse_code || '—' }}</td>
                <td>{{ row.demand_type || '—' }}</td>
                <td class="text-right tabular-nums">{{ row.rejection_count?.toLocaleString() }}</td>
                <td class="text-xs text-slate-600">{{ row.reason_detail }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <p
        v-if="summary && !summary.demand_sku_not_found?.length && !summary.demand_insufficient_history?.length"
        class="text-sm text-slate-600"
      >
        No demand transform SKU rollups for this run (rejections may be staging/validation only). Check
        <strong>By reason</strong> above or download the CSV.
      </p>
    </section>

    <p v-if="loading" class="text-sm text-slate-500">Loading…</p>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api/client'

interface RunOption {
  id: string
  entity: string
  file_name: string | null
  status: string
  rejected_count: number
}

interface RejectionSummary {
  run_id: string
  entity: string
  file_name: string | null
  status: string
  total_rejections: number
  by_reason: { reason: string; count: number }[]
  demand_sku_not_found: {
    sku_raw: string
    sku_after_code_map: string | null
    warehouse_code: string | null
    demand_type: string | null
    rejection_count: number
    sample_week_starts: string[]
  }[]
  demand_insufficient_history: {
    sku: string
    warehouse_code: string | null
    demand_type: string | null
    rejection_count: number
    reason_detail: string
  }[]
  hints?: { sku_not_found?: string; insufficient_history?: string }
}

const route = useRoute()
const router = useRouter()

const demandRuns = ref<RunOption[]>([])
const selectedRunId = ref('')
const summary = ref<RejectionSummary | null>(null)
const loading = ref(false)
const loadError = ref('')
const exportBusy = ref(false)

async function loadRunList() {
  const { data } = await api.get<RunOption[]>('/ingestion/runs', { params: { entity: 'demand', limit: 80 } })
  demandRuns.value = data
}

async function loadSummary() {
  if (!selectedRunId.value) {
    summary.value = null
    return
  }
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await api.get<RejectionSummary>(`/ingestion/runs/${selectedRunId.value}/rejections/summary`)
    summary.value = data
  } catch (e: unknown) {
    summary.value = null
    loadError.value = e instanceof Error ? e.message : 'Failed to load summary'
  } finally {
    loading.value = false
  }
}

function onRunChange() {
  void router.replace({ query: { ...route.query, run: selectedRunId.value || undefined } })
  void loadSummary()
}

async function downloadExport() {
  if (!selectedRunId.value) return
  exportBusy.value = true
  try {
    const res = await api.get(`/ingestion/runs/${selectedRunId.value}/rejections/export`, {
      responseType: 'blob',
    })
    const cd = res.headers['content-disposition'] as string | undefined
    let filename = `rejections_${selectedRunId.value.slice(0, 8)}.csv`
    if (cd) {
      const m = /filename="?([^";]+)"?/i.exec(cd)
      if (m?.[1]) filename = m[1]
    }
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  } finally {
    exportBusy.value = false
  }
}

watch(
  () => route.query.run,
  (run) => {
    if (typeof run === 'string' && run && run !== selectedRunId.value) {
      selectedRunId.value = run
      void loadSummary()
    }
  },
)

onMounted(async () => {
  try {
    await loadRunList()
  } catch {
    loadError.value = 'Could not load ingestion runs.'
  }
  const q = route.query.run
  if (typeof q === 'string' && q) {
    selectedRunId.value = q
    await loadSummary()
  }
})
</script>
