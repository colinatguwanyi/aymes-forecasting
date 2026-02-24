<template>
  <div class="page-shell space-y-6">
    <header class="page-header">
      <h1>Settings</h1>
      <p class="muted mt-1">App configuration (sample sales SOH warehouses, etc.).</p>
    </header>

    <section class="card card-body">
      <h3 class="section-title mb-2">Sample sales SOH warehouses</h3>
      <p class="text-sm text-slate-600 mb-3">Warehouse codes used for SOH in sample sales / planning. Default: BLP only. Comma-separated (e.g. BLP, WH2).</p>
      <div class="flex flex-wrap items-end gap-3">
        <div class="flex-1 min-w-[200px]">
          <label class="form-label">Warehouse codes</label>
          <input
            v-model="warehouseCodesInput"
            type="text"
            placeholder="BLP, WH2"
            class="input w-full"
          />
        </div>
        <button
          type="button"
          @click="saveSettings"
          :disabled="saving"
          class="btn-primary"
        >
          {{ saving ? 'Saving…' : 'Save' }}
        </button>
      </div>
      <p v-if="saveMessage" class="mt-2 text-sm" :class="saveMessage.startsWith('Error') ? 'text-red-600' : 'text-green-600'">
        {{ saveMessage }}
      </p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../../api/client'

const warehouseCodesInput = ref('')
const saving = ref(false)
const saveMessage = ref('')

async function loadSettings() {
  try {
    const { data } = await api.get<{ warehouse_codes: string[] }>('/admin/settings/sample-sales-soh-warehouses')
    warehouseCodesInput.value = (data.warehouse_codes || []).join(', ')
  } catch (e) {
    saveMessage.value = 'Error loading settings'
    console.error(e)
  }
}

async function saveSettings() {
  saving.value = true
  saveMessage.value = ''
  try {
    const codes = warehouseCodesInput.value
      .split(',')
      .map((c) => c.trim())
      .filter(Boolean)
    if (!codes.length) {
      saveMessage.value = 'Error: at least one warehouse code required'
      return
    }
    await api.put('/admin/settings/sample-sales-soh-warehouses', { warehouse_codes: codes })
    saveMessage.value = 'Saved'
    setTimeout(() => { saveMessage.value = '' }, 3000)
  } catch (e) {
    saveMessage.value = 'Error saving'
    console.error(e)
  } finally {
    saving.value = false
  }
}

onMounted(loadSettings)
</script>
