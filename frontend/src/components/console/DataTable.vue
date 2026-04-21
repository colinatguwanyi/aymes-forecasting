<template>
  <div class="data-table-wrapper" :class="[densityClass]">
    <div class="overflow-x-auto">
      <table class="w-full border-collapse data-table">
        <thead class="data-table-head">
          <tr>
            <th
              v-for="col in columns"
              :key="col.key"
              :class="[
                densityThClass,
                'text-left font-medium text-white/95 whitespace-nowrap',
                col.align === 'right' && 'text-right',
                col.sortable && 'cursor-pointer select-none hover:text-white',
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
            <th v-if="rowActions.length" :class="['w-12 text-right font-medium text-white/95', densityThClass]"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td :colspan="columns.length + (rowActions.length ? 1 : 0)" class="px-3 py-8 text-center text-slate-500 text-sm">
              Loading…
            </td>
          </tr>
          <tr v-else-if="!rows.length">
            <td :colspan="columns.length + (rowActions.length ? 1 : 0)" class="px-3 py-12 text-center text-slate-500 text-sm">
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
              densityRowClass,
              'border-b border-slate-200 hover:bg-slate-50 transition-colors',
              (idx % 2 === 1 && density === 'compact') && 'bg-slate-50/50',
              onRowClick && 'cursor-pointer',
              selectable && selectedRows?.includes(row[rowKey as string] as string | number) && 'bg-slate-100',
            ]"
            @click="onRowClick ? onRowClick(row) : undefined"
          >
            <td
              v-for="col in columns"
              :key="col.key"
              :class="[
                densityTdClass,
                'text-slate-700',
                col.align === 'right' && 'text-right',
              ]"
            >
              <slot :name="`cell-${col.key}`" :row="row" :value="row[col.key]">
                {{ formatCell(row[col.key], col) }}
              </slot>
            </td>
            <td v-if="rowActions.length" :class="['text-right', densityTdClass]" @click.stop>
              <div class="inline-block" :ref="(el) => setMenuEl(idx, el as HTMLElement)">
                <button
                  type="button"
                  class="p-1.5 rounded hover:bg-neutral-200 text-neutral-500 hover:text-neutral-700"
                  aria-label="Row actions"
                  @click.stop="toggleMenu(idx, row)"
                >
                  <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" /></svg>
                </button>
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

    <Teleport to="body">
      <div
        v-if="openMenuIdx !== null && menuPosition && openMenuRow"
        ref="floatingMenuRef"
        class="data-table-floating-menu"
        :style="{
          top: menuPosition.top,
          left: menuPosition.left,
        }"
        role="menu"
        @click.stop
      >
        <button
          v-for="action in rowActions"
          :key="action.id"
          type="button"
          class="w-full text-left px-3 py-2 text-sm text-neutral-700 hover:bg-neutral-100"
          role="menuitem"
          @click="runAction(action, openMenuRow)"
        >
          {{ action.label }}
        </button>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'

export interface DataTableColumn {
  key: string
  label: string
  sortable?: boolean
  align?: 'left' | 'right'
  format?: 'text' | 'boolean' | 'number' | 'date' | 'datetime'
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
    density?: 'compact' | 'comfortable'
  }>(),
  {
    rowKey: 'id',
    loading: false,
    sortField: undefined,
    sortDir: 'asc',
    selectable: false,
    selectedRows: () => [],
    rowActions: () => [],
    density: 'compact',
  }
)

const densityClass = computed(() => `density-${props.density}`)
const densityThClass = computed(() =>
  props.density === 'compact' ? 'px-3 py-1.5 text-xs font-semibold uppercase tracking-wide' : 'px-3 py-2.5 text-sm'
)
const densityTdClass = computed(() =>
  props.density === 'compact' ? 'px-3 py-1.5 text-sm' : 'px-3 py-2 text-sm'
)
const densityRowClass = computed(() => '')

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
  if (col.format === 'datetime' && typeof value === 'string')
    return value.includes('T') ? value.replace('T', ' ').slice(0, 19) : value.slice(0, 19)
  return String(value)
}

const MENU_WIDTH_PX = 160
const MENU_ITEM_APPROX_PX = 40

const openMenuIdx = ref<number | null>(null)
const openMenuRow = ref<Record<string, unknown> | null>(null)
const menuPosition = ref<{ top: string; left: string } | null>(null)
const menuEls = ref<Record<number, HTMLElement | null>>({})
const floatingMenuRef = ref<HTMLElement | null>(null)

function setMenuEl(idx: number, el: HTMLElement | null) {
  menuEls.value[idx] = el
}

function closeMenu() {
  openMenuIdx.value = null
  openMenuRow.value = null
  menuPosition.value = null
}

function positionFloatingMenu(idx: number) {
  const wrap = menuEls.value[idx]
  if (!wrap) return
  const btn = wrap.querySelector('button')
  if (!btn) return
  const rect = btn.getBoundingClientRect()
  const itemCount = Math.max(1, props.rowActions.length)
  const menuHeight = itemCount * MENU_ITEM_APPROX_PX + 8
  let top = rect.bottom + 4
  if (top + menuHeight > window.innerHeight - 8) {
    top = Math.max(8, rect.top - menuHeight - 4)
  }
  let left = rect.right - MENU_WIDTH_PX
  if (left < 8) left = 8
  if (left + MENU_WIDTH_PX > window.innerWidth - 8) {
    left = Math.max(8, window.innerWidth - MENU_WIDTH_PX - 8)
  }
  menuPosition.value = { top: `${top}px`, left: `${left}px` }
}

async function toggleMenu(idx: number, row: Record<string, unknown>) {
  if (openMenuIdx.value === idx) {
    closeMenu()
    return
  }
  openMenuIdx.value = idx
  openMenuRow.value = row
  menuPosition.value = { top: '0px', left: '0px' }
  await nextTick()
  positionFloatingMenu(idx)
}

function runAction(action: RowAction, row: Record<string, unknown>) {
  closeMenu()
  action.handler(row)
}

function onClickOutside(e: MouseEvent) {
  const t = e.target as Node
  if (floatingMenuRef.value?.contains(t)) return
  const idx = openMenuIdx.value
  if (idx !== null && menuEls.value[idx]?.contains(t)) return
  closeMenu()
}

function onScrollOrResize() {
  if (openMenuIdx.value !== null) positionFloatingMenu(openMenuIdx.value)
}

onMounted(() => {
  document.addEventListener('click', onClickOutside)
  window.addEventListener('scroll', onScrollOrResize, true)
  window.addEventListener('resize', onScrollOrResize)
})
onUnmounted(() => {
  document.removeEventListener('click', onClickOutside)
  window.removeEventListener('scroll', onScrollOrResize, true)
  window.removeEventListener('resize', onScrollOrResize)
})
</script>

<style scoped>
.data-table-wrapper {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.75rem;
  background: white;
  overflow: hidden;
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
}
.data-table-head {
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--table-header-bg, #153256);
  border-bottom: 1px solid #0f2847;
}
</style>

<style>
/* Unscoped: teleported to body */
.data-table-floating-menu {
  position: fixed;
  z-index: 10050;
  min-width: 10rem;
  width: 10rem;
  padding: 0.25rem 0;
  background: white;
  border: 1px solid rgb(229 231 235);
  border-radius: 0.375rem;
  box-shadow:
    0 10px 15px -3px rgb(0 0 0 / 0.1),
    0 4px 6px -4px rgb(0 0 0 / 0.1);
}
</style>
