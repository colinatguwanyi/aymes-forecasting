<template>
  <div class="page-shell space-y-6">
    <header class="page-header">
      <h1>Forecasting Methods</h1>
      <p class="muted mt-1">Governance & audit: inputs, transformations, outputs, and method sign-off.</p>
    </header>

    <section v-if="loading" class="card card-body">
      <p class="muted">Loading…</p>
    </section>

    <template v-else-if="doc">
      <!-- Method version & last updated -->
      <section class="card card-body flex flex-wrap items-center justify-between gap-4">
        <div>
          <span class="text-sm font-medium text-slate-700">Method version</span>
          <span class="ml-2 font-mono text-slate-900">{{ doc.method_version }}</span>
        </div>
        <div>
          <span class="text-sm font-medium text-slate-700">Last updated</span>
          <span class="ml-2 text-slate-600">{{ doc.updated_at }}</span>
        </div>
      </section>

      <!-- Accordion sections -->
      <section class="card">
        <button
          type="button"
          class="card-header w-full text-left flex items-center justify-between py-3 px-4"
          :class="{ 'border-b': accordionOpen.overview }"
          @click="accordionOpen.overview = !accordionOpen.overview"
        >
          <span class="font-medium text-slate-800">Overview</span>
          <span class="text-slate-400">{{ accordionOpen.overview ? '▼' : '▶' }}</span>
        </button>
        <div v-show="accordionOpen.overview" class="card-body border-t border-slate-200">
          <p class="text-sm text-slate-600">{{ (doc.overview as any)?.description }}</p>
          <dl class="mt-3 text-sm grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
            <dt class="text-slate-500">Timezone</dt>
            <dd>{{ (doc.overview as any)?.timezone }}</dd>
            <dt class="text-slate-500">Week anchor</dt>
            <dd>{{ (doc.overview as any)?.week_anchor }}</dd>
          </dl>
        </div>
      </section>

      <section class="card">
        <button
          type="button"
          class="card-header w-full text-left flex items-center justify-between py-3 px-4"
          :class="{ 'border-b': accordionOpen.inputs }"
          @click="accordionOpen.inputs = !accordionOpen.inputs"
        >
          <span class="font-medium text-slate-800">Inputs</span>
          <span class="text-slate-400">{{ accordionOpen.inputs ? '▼' : '▶' }}</span>
        </button>
        <div v-show="accordionOpen.inputs" class="card-body border-t border-slate-200 space-y-4">
          <div v-for="([k, v]) in Object.entries((doc.inputs ?? {}) as any)" :key="k" class="border-b border-slate-100 pb-3 last:border-0 last:pb-0">
            <h4 class="font-medium text-slate-800 capitalize">{{ String(k).replace(/_/g, ' ') }}</h4>
            <p class="text-sm text-slate-600 mt-0.5">{{ (v as any)?.description }}</p>
            <p class="text-xs text-slate-500 mt-1">Maps to: {{ formatMapsTo(v) }}</p>
          </div>
        </div>
      </section>

      <section class="card">
        <button
          type="button"
          class="card-header w-full text-left flex items-center justify-between py-3 px-4"
          :class="{ 'border-b': accordionOpen.timeSeriesPrep }"
          @click="accordionOpen.timeSeriesPrep = !accordionOpen.timeSeriesPrep"
        >
          <span class="font-medium text-slate-800">Time series prep</span>
          <span class="text-slate-400">{{ accordionOpen.timeSeriesPrep ? '▼' : '▶' }}</span>
        </button>
        <div v-show="accordionOpen.timeSeriesPrep" class="card-body border-t border-slate-200">
          <dl class="text-sm space-y-2">
            <div><dt class="text-slate-500 font-medium">Calendar</dt><dd>{{ (doc.time_series_prep as any)?.calendar }}</dd></div>
            <div><dt class="text-slate-500 font-medium">Bucket rule</dt><dd>{{ (doc.time_series_prep as any)?.bucket_rule }}</dd></div>
            <div v-if="(doc.time_series_prep as any)?.dedupe_rules?.length">
              <dt class="text-slate-500 font-medium">Dedupe rules</dt>
              <dd><ul class="list-disc pl-4 mt-1"><li v-for="(r, i) in (doc.time_series_prep as any).dedupe_rules" :key="i">{{ r }}</li></ul></dd>
            </div>
          </dl>
        </div>
      </section>

      <section class="card">
        <button
          type="button"
          class="card-header w-full text-left flex items-center justify-between py-3 px-4"
          :class="{ 'border-b': accordionOpen.forecasting }"
          @click="accordionOpen.forecasting = !accordionOpen.forecasting"
        >
          <span class="font-medium text-slate-800">Forecast methods</span>
          <span class="text-slate-400">{{ accordionOpen.forecasting ? '▼' : '▶' }}</span>
        </button>
        <div v-show="accordionOpen.forecasting" class="card-body border-t border-slate-200">
          <p class="text-sm text-slate-600">Modes: {{ (doc.forecasting as any)?.modes?.join(', ') }}</p>
          <p class="text-sm text-slate-600 mt-2">Baseline selection: {{ (doc.forecasting as any)?.baseline_selection }}</p>
          <p class="text-sm text-slate-600 mt-1">Blending rule: {{ (doc.forecasting as any)?.blending_rule }}</p>
        </div>
      </section>

      <section class="card">
        <button
          type="button"
          class="card-header w-full text-left flex items-center justify-between py-3 px-4"
          :class="{ 'border-b': accordionOpen.planningIntegration }"
          @click="accordionOpen.planningIntegration = !accordionOpen.planningIntegration"
        >
          <span class="font-medium text-slate-800">Planning integration</span>
          <span class="text-slate-400">{{ accordionOpen.planningIntegration ? '▼' : '▶' }}</span>
        </button>
        <div v-show="accordionOpen.planningIntegration" class="card-body border-t border-slate-200">
          <p class="text-sm text-slate-600">Freeze weeks: {{ (doc.planning_integration as any)?.freeze_weeks }}</p>
          <p class="text-sm text-slate-600 mt-1">Order rounding: {{ formatStringList((doc.planning_integration as any)?.order_rounding, '; ') }}</p>
          <p class="text-sm text-slate-600 mt-1">Lead time sources: {{ formatStringList((doc.planning_integration as any)?.lead_time_sources, '; ') }}</p>
        </div>
      </section>

      <section class="card">
        <button
          type="button"
          class="card-header w-full text-left flex items-center justify-between py-3 px-4"
          :class="{ 'border-b': accordionOpen.limitations }"
          @click="accordionOpen.limitations = !accordionOpen.limitations"
        >
          <span class="font-medium text-slate-800">Known limitations</span>
          <span class="text-slate-400">{{ accordionOpen.limitations ? '▼' : '▶' }}</span>
        </button>
        <div v-show="accordionOpen.limitations" class="card-body border-t border-slate-200">
          <ul class="list-disc pl-4 text-sm text-slate-600 space-y-1">
            <li v-for="(lim, i) in (doc.known_limitations as any)" :key="i">{{ lim }}</li>
          </ul>
        </div>
      </section>

      <!-- Method version & sign-off -->
      <section class="card card-body">
        <h3 class="section-title mb-3">Method acknowledgement / sign-off</h3>
        <p class="text-sm text-slate-600 mb-3">Signed off by {{ acknowledgements.length }} user(s).</p>
        <div v-if="acknowledgements.length" class="overflow-x-auto mb-4">
          <table class="app-table">
            <thead><tr><th>User</th><th>Date</th><th>Notes</th></tr></thead>
            <tbody>
              <tr v-for="a in acknowledgements" :key="a.id">
                <td>{{ a.created_by }}</td>
                <td>{{ a.acknowledged_at }}</td>
                <td>{{ a.notes || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="flex flex-wrap items-end gap-3">
          <div>
            <label class="form-label block">Type ACKNOWLEDGE to sign off</label>
            <input v-model="acknowledgeTyped" type="text" placeholder="ACKNOWLEDGE" class="app-input max-w-xs" />
          </div>
          <div>
            <label class="form-label block">Notes (optional)</label>
            <input v-model="acknowledgeNotes" type="text" placeholder="e.g. Approved for FY26 planning" class="app-input max-w-xs" />
          </div>
          <button
            type="button"
            class="btn-primary"
            :disabled="acknowledgeTyped.toUpperCase() !== 'ACKNOWLEDGE'"
            @click="doAcknowledge"
          >
            Acknowledge / sign off
          </button>
        </div>
      </section>

      <!-- View raw JSON -->
      <section class="card">
        <button
          type="button"
          class="card-header w-full text-left flex items-center justify-between py-3 px-4"
          :class="{ 'border-b': accordionOpen.rawJson }"
          @click="accordionOpen.rawJson = !accordionOpen.rawJson"
        >
          <span class="font-medium text-slate-800">View raw JSON</span>
          <span class="text-slate-400">{{ accordionOpen.rawJson ? '▼' : '▶' }}</span>
        </button>
        <div v-show="accordionOpen.rawJson" class="card-body border-t border-slate-200">
          <pre class="text-xs bg-slate-50 p-4 rounded overflow-auto max-h-96">{{ JSON.stringify(doc, null, 2) }}</pre>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import api from '@/api/client'
import type { ForecastMethodsDoc, ForecastMethodAcknowledgement } from '@/api/client'

const loading = ref(true)
const doc = ref<ForecastMethodsDoc | null>(null)
const acknowledgements = ref<ForecastMethodAcknowledgement[]>([])
const acknowledgeTyped = ref('')
const acknowledgeNotes = ref('')
const accordionOpen = reactive({
  overview: true,
  inputs: false,
  timeSeriesPrep: false,
  forecasting: false,
  planningIntegration: false,
  limitations: false,
  rawJson: false,
})

/** Avoid `Record<…>` / complex `as` in template — HTML parser treats `<` as tags. */
function formatMapsTo(v: unknown): string {
  const m = (v as { maps_to?: unknown })?.maps_to
  if (Array.isArray(m)) return (m as string[]).join(', ')
  if (m != null && typeof m === 'string') return m
  return ''
}

function formatStringList(val: unknown, sep: string): string {
  if (Array.isArray(val)) return (val as string[]).join(sep)
  return ''
}

async function loadDoc() {
  const { data } = await api.get<ForecastMethodsDoc>('/admin/forecast-methods')
  doc.value = data
}

async function loadAcknowledgements() {
  if (!doc.value?.method_version) return
  const { data } = await api.get<ForecastMethodAcknowledgement[]>('/admin/forecast-methods/acknowledgements', {
    params: { method_version: doc.value.method_version },
  })
  acknowledgements.value = Array.isArray(data) ? data : []
}

async function doAcknowledge() {
  if (!doc.value || acknowledgeTyped.value.toUpperCase() !== 'ACKNOWLEDGE') return
  const audit = doc.value.audit as { hash?: string }
  const hash = audit?.hash ?? ''
  try {
    await api.post('/admin/forecast-methods/acknowledge', {
      method_version: doc.value.method_version,
      method_hash: hash,
      notes: acknowledgeNotes.value || undefined,
      created_by: 'user',
    })
    acknowledgeTyped.value = ''
    acknowledgeNotes.value = ''
    await loadAcknowledgements()
  } catch (err: unknown) {
    const msg = err && typeof err === 'object' && 'response' in err
      ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      : null
    alert(msg ? `Sign-off failed: ${typeof msg === 'string' ? msg : JSON.stringify(msg)}` : 'Sign-off failed.')
  }
}

onMounted(async () => {
  await loadDoc()
  await loadAcknowledgements()
  loading.value = false
})
</script>

<style scoped>
.section-title { font-size: 1rem; font-weight: 500; color: rgb(30 41 59); }
</style>
