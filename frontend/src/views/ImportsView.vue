<template>
  <div class="imports-view">
    <h1>Imports</h1>
    <p class="muted">Upload CSV with dry-run validation. Fix row errors then confirm import.</p>

    <section class="card">
      <h2>CSV templates (download)</h2>
      <ul class="template-links">
        <li><a href="/api/templates/inventory-snapshots" download>Inventory snapshots</a></li>
        <li><a href="/api/templates/receipts" download>Receipts</a></li>
        <li><a href="/api/templates/demand-actuals" download>Demand actuals</a></li>
        <li><a href="/api/templates/samples-withdrawals" download>Samples withdrawals</a></li>
        <li><a href="/api/templates/products" download>Products</a></li>
      </ul>
    </section>

    <section class="card">
      <h2>Upload</h2>
      <select v-model="importType" class="select">
        <option value="inventory-snapshots">Inventory snapshots</option>
        <option value="receipts">Receipts</option>
        <option value="demand-actuals">Demand actuals</option>
        <option value="samples-withdrawals">Samples withdrawals</option>
        <option value="products">Products</option>
      </select>
      <input type="file" ref="fileInput" accept=".csv" @change="onFileSelect" class="file-input" />
      <div class="actions">
        <button @click="dryRun" :disabled="!file">Dry run (validate)</button>
        <button @click="confirmImport" :disabled="!file || !result?.valid_rows" class="btn-confirm">Confirm import</button>
      </div>
    </section>

    <section v-if="result" class="card result">
      <h2>Result</h2>
      <p><strong>Valid:</strong> {{ result.valid ? 'Yes' : 'No' }}</p>
      <p><strong>Total rows:</strong> {{ result.total_rows }}</p>
      <p><strong>Valid rows:</strong> {{ result.valid_rows }}</p>
      <div v-if="result.errors?.length" class="errors">
        <h3>Row errors</h3>
        <table class="table">
          <thead>
            <tr>
              <th>Row</th>
              <th>Errors</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in result.errors" :key="e.row">
              <td>{{ e.row }}</td>
              <td>{{ e.errors.join(', ') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="result.preview?.length" class="preview">
        <h3>Preview (first 5 rows)</h3>
        <pre>{{ JSON.stringify(result.preview, null, 2) }}</pre>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import api from '@/api/client'
import type { ImportDryRunResult } from '@/api/client'
const importType = ref<'inventory-snapshots' | 'receipts' | 'demand-actuals' | 'samples-withdrawals' | 'products'>('inventory-snapshots')
const fileInput = ref<HTMLInputElement | null>(null)
const file = ref<File | null>(null)
const result = ref<ImportDryRunResult | null>(null)

function onFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  file.value = target.files?.[0] ?? null
  result.value = null
}

async function dryRun() {
  if (!file.value) return
  const form = new FormData()
  form.append('file', file.value)
  const { data } = await api.post<ImportDryRunResult>(`/import/${importType.value}?dry_run=true`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  result.value = data
}

async function confirmImport() {
  if (!file.value) return
  const form = new FormData()
  form.append('file', file.value)
  const { data } = await api.post<ImportDryRunResult>(`/import/${importType.value}?dry_run=false`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  result.value = data
  file.value = null
  if (fileInput.value) fileInput.value.value = ''
}
</script>

<style scoped>
.imports-view { display: flex; flex-direction: column; gap: 1rem; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 1rem; }
.card h2 { margin: 0 0 0.5rem 0; font-size: 1rem; }
.template-links { list-style: none; padding: 0; margin: 0; }
.template-links a { color: var(--accent); text-decoration: none; }
.template-links a:hover { text-decoration: underline; }
.select { padding: 0.35rem 0.5rem; border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg); color: var(--text); margin-right: 0.5rem; }
.file-input { margin: 0.5rem 0; }
.actions { display: flex; gap: 0.5rem; margin-top: 0.5rem; }
.actions button { padding: 0.35rem 0.75rem; background: var(--accent); color: var(--bg); border: none; border-radius: var(--radius); cursor: pointer; }
.actions button:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-confirm { background: var(--success) !important; }
.result .errors, .result .preview { margin-top: 0.5rem; }
.result .table { width: 100%; border-collapse: collapse; }
.result .table th, .result .table td { text-align: left; padding: 0.5rem; border-bottom: 1px solid var(--border); }
.result pre { font-size: 0.85rem; overflow: auto; }
.muted { color: var(--muted); margin: 0.5rem 0; }
</style>
