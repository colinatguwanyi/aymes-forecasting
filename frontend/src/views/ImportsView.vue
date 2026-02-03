<template>
  <div class="page-content-inner">
    <p class="muted">Upload CSV with dry-run validation. Fix row errors then confirm import.</p>

    <section class="content-section">
      <h2>CSV templates (download)</h2>
      <ul class="template-links">
        <li><a href="/api/templates/inventory-snapshots" download>Inventory snapshots</a></li>
        <li><a href="/api/templates/receipts" download>Receipts</a></li>
        <li><a href="/api/templates/demand-actuals" download>Demand actuals</a></li>
        <li><a href="/api/templates/samples-withdrawals" download>Samples withdrawals</a></li>
        <li><a href="/api/templates/products" download>Products</a></li>
      </ul>
    </section>

    <section class="content-section">
      <h2>Upload</h2>
      <select v-model="importType" class="app-select" style="max-width: 18rem; margin-bottom: 0.5rem;">
        <option value="inventory-snapshots">Inventory snapshots</option>
        <option value="receipts">Receipts</option>
        <option value="demand-actuals">Demand actuals</option>
        <option value="samples-withdrawals">Samples withdrawals</option>
        <option value="products">Products</option>
      </select>
      <input type="file" ref="fileInput" accept=".csv" @change="onFileSelect" class="file-input" />
      <div class="actions">
        <button type="button" @click="dryRun" :disabled="!file" class="app-btn app-btn-primary">Dry run (validate)</button>
        <button type="button" @click="confirmImport" :disabled="!file || !result?.valid_rows" class="app-btn app-btn-primary btn-confirm">Confirm import</button>
      </div>
    </section>

    <section v-if="result" class="content-section result">
      <h2>Result</h2>
      <p>Valid: {{ result.valid ? 'Yes' : 'No' }}</p>
      <p>Total rows: {{ result.total_rows }}</p>
      <p>Valid rows: {{ result.valid_rows }}</p>
      <div v-if="result.errors?.length" class="errors">
        <h3>Row errors</h3>
        <div class="app-table-wrap">
          <table class="app-table">
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
.template-links { list-style: none; padding: 0; margin: 0; }
.template-links a { color: var(--accent); text-decoration: none; font-size: 0.875rem; }
.template-links a:hover { text-decoration: underline; }
.file-input { margin: 0.5rem 0; display: block; }
.actions { display: flex; gap: 0.5rem; margin-top: 0.5rem; }
.btn-confirm { background: var(--success); border-color: var(--success); }
.result .errors, .result .preview { margin-top: 0.75rem; }
.result pre { font-size: 0.8125rem; overflow: auto; max-height: 12rem; }
.result h3 { font-size: 0.9375rem; margin-top: 0.5rem; }
</style>
