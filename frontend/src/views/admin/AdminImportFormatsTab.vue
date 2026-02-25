<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-xl font-semibold text-slate-800">Import Formats</h2>
      <p class="text-sm text-slate-600 mt-1">Field requirements per import type. Required / Optional / Not used.</p>
    </div>

    <!-- Matrix table -->
    <section class="card overflow-x-auto">
      <h3 class="section-title px-5 py-3 border-b border-slate-200">Field matrix</h3>
      <div class="overflow-x-auto">
        <table class="app-table min-w-max">
          <thead>
            <tr>
              <th class="text-left sticky left-0 bg-slate-50 z-10">Field</th>
              <th v-for="imp in IMPORT_FORMATS" :key="imp.id" class="text-center whitespace-nowrap px-3">
                {{ imp.title }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="field in allFields" :key="field">
              <td class="font-mono text-sm sticky left-0 bg-white z-10">{{ field }}</td>
              <td v-for="imp in IMPORT_FORMATS" :key="imp.id" class="text-center px-3">
                <span
                  v-if="getUsage(imp, field)"
                  class="text-xs px-2 py-0.5 rounded"
                  :class="usageClass(getUsage(imp, field)!)"
                >
                  {{ getUsage(imp, field) }}
                </span>
                <span v-else class="text-slate-300">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Per-import accordion cards -->
    <section>
      <h3 class="section-title mb-3">Per-import details</h3>
      <div class="space-y-2">
        <div
          v-for="imp in IMPORT_FORMATS"
          :key="imp.id"
          class="card overflow-hidden"
        >
          <button
            type="button"
            class="w-full text-left px-5 py-3 flex items-center justify-between hover:bg-slate-50"
            @click="toggle(imp.id)"
          >
            <span class="font-medium text-slate-800">{{ imp.title }}</span>
            <span class="text-slate-400">{{ expanded.has(imp.id) ? '▼' : '▶' }}</span>
          </button>
          <div v-show="expanded.has(imp.id)" class="border-t border-slate-200 px-5 py-3 text-sm space-y-2">
            <p><strong>Accepted:</strong> {{ imp.acceptedFileTypes }}</p>
            <p><strong>Required columns:</strong> {{ imp.requiredColumns.join(', ') }}</p>
            <p v-if="imp.notes" class="text-slate-600">{{ imp.notes }}</p>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { IMPORT_FORMATS, getAllFields, type FieldUsage } from '@/config/importFormats'

const allFields = computed(() => getAllFields())

const expanded = ref<Set<string>>(new Set(IMPORT_FORMATS.slice(0, 3).map((i) => i.id)))

function toggle(id: string) {
  const next = new Set(expanded.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expanded.value = next
}

function getUsage(imp: (typeof IMPORT_FORMATS)[0], field: string): FieldUsage | null {
  return imp.fields[field] ?? null
}

function usageClass(u: FieldUsage): string {
  if (u === 'required') return 'bg-amber-100 text-amber-800'
  if (u === 'optional') return 'bg-slate-100 text-slate-700'
  return 'bg-slate-50 text-slate-400'
}
</script>
