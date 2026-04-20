<template>
  <div class="border border-neutral-200 rounded-lg bg-white overflow-hidden">
    <div class="overflow-x-auto">
      <table class="w-full text-sm border-collapse">
        <thead class="sticky top-0 z-10 bg-neutral-50 border-b border-neutral-200">
          <tr>
            <th
              v-for="col in columns"
              :key="col.key"
              :class="[
                'px-3 py-2.5 text-left font-medium text-neutral-600 whitespace-nowrap',
                col.align === 'right' && 'text-right',
                col.sortable && 'cursor-pointer select-none hover:text-neutral-900',
              ]"
              @click="col.sortable && emit('sort', col.key)"
            >
              <span class="inline-flex items-center gap-1">
                {{ col.label }}
                <template v-if="col.sortable && sortField === col.key">
                  <span v-if="sortDir === 'asc'" aria-hidden="true">↑</span>
                  <span v-else aria-hidden="true">↓</span>
                </template>
              </span>
            </th>
            <th v-if="rowActions.length" class="w-12 px-3 py-2.5 text-right font-medium text-neutral-600"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td :colspan="columns.length + (rowActions.length ? 1 : 0)" class="px-3 py-8 text-center text-neutral-500">
              Loading…
            </td>
          </tr>
          <tr v-else-if="!rows.length">
            <td :colspan="columns.length + (rowActions.length ? 1 : 0)" class="px-3 py-12 text-center text-neutral-500">
              <slot name="empty">
                No data
              </slot>
            </td>
          </tr>
          <tr
            v-else
            v-for="(row, idx) in rows"
            :key="rowKey ? (row[rowKey] as string | number) : idx"
            :class="[
              'border-b border-neutral-100 hover:bg-neutral-50 transition-colors',
              onRowClick && 'cursor-pointer',
              selectable && selectedRows?.includes(row[rowKey as string] as string | number) && 'bg-neutral-100',
            ]"
            @click="onRowClick ? onRowClick(row) : undefined"
          >
            <td
              v-for="col in columns"
              :key="col.key"
              :class="[
                'px-3 py-2 text-neutral-800',
                col.align === 'right' && 'text-right',
              ]"
            >
              <slot :name="`cell-${col.key}`" :row="row" :value="row[col.key]">
                {{ formatCell(row[col.key], col) }}
              </slot>
            </td>
            <td v-if="rowActions.length" class="px-3 py-2 text-right" @click.stop>
              <div class="relative inline-block" :ref="(el) => setMenuEl(idx, el as HTMLElement)">
                <button
                  type="button"
                  class="p-1.5 rounded hover:bg-neutral-200 text-neutral-500 hover:text-neutral-700"
                  aria-label="Row actions"
                  @click.stop="toggleMenu(idx)"
                >
                  <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" /></svg>
                </button>
                <div
                  v-if="openMenuIdx === idx"
                  class="absolute right-0 mt-1 w-40 py-1 bg-white border border-neutral-200 rounded-md shadow-lg z-20"
                >
                  <button
                    v-for="action in rowActions"
                    :key="action.id"
                    type="button"
                    class="w-full text-left px-3 py-2 text-sm text-neutral-700 hover:bg-neutral-100"
                    @click="runAction(action, row)"
                  >
                    {{ action.label }}
                  </button>
                </div>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div
      v-if="pagination && pagination.total > 0"
      class="flex items-center justify-between gap-4 px-3 py-2 border-t border-neutral-200 bg-neutral-50 text-sm text-neutral-600"
    >
      <div class="flex items-center gap-2">
        <span>Rows per page</span>
        <select
          :value="pagination.pageSize"
          class="border border-neutral-300 rounded px-2 py-1 text-sm bg-white"
          @change="emit('update:pageSize', Number(($event.target as HTMLSelectElement).value))"
        >
          <option v-for="n in [10, 25, 50, 100]" :key="n" :value="n">{{ n }}</option>
        </select>
      </div>
      <div class="flex items-center gap-4">
        <span>
          {{ (pagination.page - 1) * pagination.pageSize + 1 }}–{{ Math.min(pagination.page * pagination.pageSize, pagination.total) }}
          of {{ pagination.total }}
        </span>
        <div class="flex gap-1">
          <button
            type="button"
            class="px-2 py-1 rounded border border-neutral-300 bg-white hover:bg-neutral-100 disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="pagination.page <= 1"
            @click="emit('update:page', pagination.page - 1)"
          >
            Previous
          </button>
          <button
            type="button"
            class="px-2 py-1 rounded border border-neutral-300 bg-white hover:bg-neutral-100 disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="pagination.page >= totalPages"
            @click="emit('update:page', pagination.page + 1)"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

export interface DataTableColumn {
  key: string
  label: string
  sortable?: boolean
  align?: 'left' | 'right'
  format?: 'text' | 'boolean' | 'number' | 'date'
}

export interface RowAction {
  id: string
  label: string
  handler: (row: Record<string, unknown>) => void
}

const props = withDefaults(
  defineProps<{
    columns: DataTableColumn[]
    rows: Record<string, unknown>[]
    rowKey?: string
    loading?: boolean
    pagination?: { page: number; pageSize: number; total: number }
    sortField?: string
    sortDir?: 'asc' | 'desc'
    selectable?: boolean
    selectedRows?: (string | number)[]
    rowActions?: RowAction[]
    onRowClick?: (row: Record<string, unknown>) => void
  }>(),
  {
    rowKey: 'id',
    loading: false,
    sortField: undefined,
    sortDir: 'asc',
    selectable: false,
    selectedRows: () => [],
    rowActions: () => [],
  }
)

const emit = defineEmits<{
  sort: [field: string]
  'update:page': [page: number]
  'update:pageSize': [size: number]
}>()

const totalPages = computed(() =>
  props.pagination
    ? Math.max(1, Math.ceil(props.pagination.total / props.pagination.pageSize))
    : 1
)

function formatCell(value: unknown, col: DataTableColumn): string {
  if (value == null) return '—'
  if (col.format === 'boolean') return value ? 'Yes' : 'No'
  if (col.format === 'number') return String(Number(value))
  if (col.format === 'date' && typeof value === 'string') return value.slice(0, 10)
  return String(value)
}

const openMenuIdx = ref<number | null>(null)
const menuEls = ref<Record<number, HTMLElement | null>>({})

function setMenuEl(idx: number, el: HTMLElement | null) {
  menuEls.value[idx] = el
}

function toggleMenu(idx: number) {
  openMenuIdx.value = openMenuIdx.value === idx ? null : idx
}

function runAction(action: RowAction, row: Record<string, unknown>) {
  openMenuIdx.value = null
  action.handler(row)
}

function onClickOutside(e: MouseEvent) {
  const el = openMenuIdx.value !== null ? menuEls.value[openMenuIdx.value] : null
  if (el && !el.contains(e.target as Node)) {
    openMenuIdx.value = null
  }
}

onMounted(() => document.addEventListener('click', onClickOutside))
onUnmounted(() => document.removeEventListener('click', onClickOutside))
</script>
