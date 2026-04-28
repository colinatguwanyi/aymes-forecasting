<template>
  <div class="sku-timeline">
    <p v-if="!weeks.length" class="sku-timeline__empty muted">No weeks to display for this SKU.</p>
    <template v-else>
      <div class="sku-timeline__card">
        <div
          class="timeline-row timeline-row--grid"
          :style="{ gridTemplateColumns: columnTemplate }"
        >
          <span class="row-label">Week</span>
          <span
            v-for="w in weeks"
            :key="'h' + w"
            class="timeline-cell timeline-cell--head"
          >{{ formatWeek(w) }}</span>
        </div>
        <div
          class="timeline-row timeline-row--grid"
          :style="{ gridTemplateColumns: columnTemplate }"
        >
          <span class="row-label">Projected</span>
          <span
            v-for="w in weeks"
            :key="'p' + w"
            :class="['timeline-cell', 'timeline-cell--projected', projectedCellClass(w)]"
            :title="`${projectedQty(w)} · ${projectedWoc(w)} woc`"
          >{{ projectedQty(w) }}</span>
        </div>
        <div
          class="timeline-row timeline-row--grid"
          :style="{ gridTemplateColumns: columnTemplate }"
        >
          <span class="row-label">Inbound</span>
          <span
            v-for="w in weeks"
            :key="'i' + w"
            :class="['timeline-cell', 'timeline-cell--inbound', inboundCellClass(w)]"
            :title="inboundLabel(w)"
          >{{ inboundLabel(w) }}</span>
        </div>
      </div>
      <div class="timeline-legend">
        <span class="legend-item"><span class="legend-dot cell-status-ok" /> Healthy</span>
        <span class="legend-item"><span class="legend-dot cell-status-warning" /> Low cover</span>
        <span class="legend-item"><span class="legend-dot cell-status-error" /> Stockout</span>
        <span class="legend-item legend-item--inbound"><span class="legend-chip">Order</span> Planned · <span class="legend-chip legend-chip--rec">Rec</span> Receipt</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ProjectedInventory, PlannedOrder, Receipt } from '@/api/client'

const props = defineProps<{
  projected: ProjectedInventory[]
  plannedOrders: PlannedOrder[]
  receipts: Receipt[]
}>()

/** Align rows that use the same calendar week but different serialized forms (date vs datetime string, Date). */
function weekKey(w: unknown): string {
  if (w == null || w === '') return ''
  if (w instanceof Date) return w.toISOString().slice(0, 10)
  const s = String(w).trim()
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10)
  return s
}

const weeks = computed(() => {
  const set = new Set<string>()
  props.projected.forEach((p) => set.add(weekKey(p.week_start)))
  props.plannedOrders.forEach((o) => set.add(weekKey(o.week_start)))
  props.receipts.forEach((r) => set.add(weekKey(r.week_start)))
  return Array.from(set).filter(Boolean).sort()
})

/** Same column widths for every row so Week / Projected / Inbound line up. */
const columnTemplate = computed(() => {
  const n = weeks.value.length
  if (!n) return '5.75rem'
  return `5.75rem repeat(${n}, minmax(4.5rem, 4.5rem))`
})

const projectedByWeek = computed(() => {
  const m = new Map<string, ProjectedInventory>()
  props.projected.forEach((p) => m.set(weekKey(p.week_start), p))
  return m
})

const ordersByWeek = computed(() => {
  const m = new Map<string, PlannedOrder[]>()
  props.plannedOrders.forEach((o) => {
    const k = weekKey(o.week_start)
    const list = m.get(k) ?? []
    list.push(o)
    m.set(k, list)
  })
  return m
})

const receiptsByWeek = computed(() => {
  const m = new Map<string, Receipt[]>()
  props.receipts.forEach((r) => {
    const k = weekKey(r.week_start)
    const list = m.get(k) ?? []
    list.push(r)
    m.set(k, list)
  })
  return m
})

function formatWeek(week: string): string {
  if (!week) return '—'
  return weekKey(week)
}

function projectedCellClass(week: string): string {
  const p = projectedByWeek.value.get(weekKey(week))
  if (!p) return 'is-empty'
  if (p.stockout) return 'cell-status-error'
  if (p.weeks_of_cover != null) {
    const woc = parseFloat(String(p.weeks_of_cover))
    if (woc < 2) return 'cell-status-warning'
  }
  return 'cell-status-ok'
}

function inboundCellClass(week: string): string {
  const k = weekKey(week)
  const orders = ordersByWeek.value.get(k) ?? []
  const recs = receiptsByWeek.value.get(k) ?? []
  const has =
    orders.some((o) => parseFloat(String(o.order_qty)) > 0) ||
    recs.some((r) => parseFloat(String(r.qty)) > 0)
  return has ? 'has-flow' : 'is-empty'
}

function formatQtyDisplay(v: string | undefined): string {
  if (v == null || v === '') return '—'
  const n = Number(String(v).trim().replace(/,/g, ''))
  if (Number.isNaN(n)) return String(v)
  if (Math.abs(n - Math.round(n)) < 1e-6) return String(Math.round(n))
  return String(Math.round(n * 100) / 100)
}

function projectedQty(week: string): string {
  const p = projectedByWeek.value.get(weekKey(week))
  return p ? formatQtyDisplay(p.projected_qty) : '—'
}

function projectedWoc(week: string): string {
  const p = projectedByWeek.value.get(weekKey(week))
  return p?.weeks_of_cover ?? '—'
}

function inboundLabel(week: string): string {
  const k = weekKey(week)
  const orders = ordersByWeek.value.get(k) ?? []
  const recs = receiptsByWeek.value.get(k) ?? []
  const orderQty = orders.reduce((s, o) => s + parseFloat(o.order_qty), 0)
  const recQty = recs.reduce((s, r) => s + parseFloat(r.qty), 0)
  const parts: string[] = []
  if (orderQty > 0) parts.push(`Order ${orderQty}`)
  if (recQty > 0) parts.push(`Rec ${recQty}`)
  return parts.length ? parts.join(' · ') : '—'
}
</script>

<style scoped>
.sku-timeline {
  overflow-x: auto;
  padding-bottom: 0.25rem;
}
.sku-timeline__empty {
  margin: 0;
  font-size: 0.875rem;
}
.sku-timeline__card {
  min-width: max-content;
  padding: 0.75rem 0.85rem 0.85rem;
  border-radius: 0.75rem;
  border: 1px solid rgb(226 232 240);
  background: linear-gradient(180deg, rgb(248 250 252) 0%, rgb(255 255 255) 40%);
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.04);
}
.timeline-row--grid {
  display: grid;
  align-items: stretch;
  column-gap: 0.375rem;
  margin-bottom: 0.375rem;
  font-size: 0.8125rem;
}
.timeline-row--grid:last-child {
  margin-bottom: 0;
}
.row-label {
  padding: 0.45rem 0.35rem 0.45rem 0;
  font-weight: 600;
  font-size: 0.75rem;
  letter-spacing: 0.02em;
  color: rgb(100 116 139);
  display: flex;
  align-items: center;
}
.timeline-cell {
  border-radius: 0.5rem;
  border: 1px solid rgb(226 232 240);
  padding: 0.45rem 0.35rem;
  text-align: center;
  background: rgb(255 255 255);
  min-width: 0;
  box-sizing: border-box;
  line-height: 1.25;
  word-break: break-word;
  hyphens: auto;
}
.timeline-cell--head {
  font-size: 0.6875rem;
  font-weight: 600;
  color: rgb(71 85 105);
  background: rgb(241 245 249);
  border-color: rgb(203 213 225);
}
.timeline-cell--projected {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}
.timeline-cell--projected.is-empty {
  color: rgb(148 163 184);
  background: rgb(248 250 252);
  font-weight: 400;
}
.timeline-cell--projected.cell-status-error {
  background: rgba(254 226 226 / 0.85);
  border-color: rgb(252 165 165);
  color: rgb(153 27 27);
}
.timeline-cell--projected.cell-status-warning {
  background: rgba(254 243 199 / 0.9);
  border-color: rgb(252 211 77);
  color: rgb(146 64 14);
}
.timeline-cell--projected.cell-status-ok {
  background: rgba(220 252 231 / 0.85);
  border-color: rgb(167 243 208);
  color: rgb(22 101 52);
}
.timeline-cell--inbound {
  font-size: 0.6875rem;
  font-weight: 500;
}
.timeline-cell--inbound.is-empty {
  color: rgb(148 163 184);
  background: rgb(248 250 252);
}
.timeline-cell--inbound.has-flow {
  color: rgb(30 64 175);
  background: rgba(219 234 254 / 0.65);
  border-color: rgb(147 197 253);
}
.timeline-legend {
  margin-top: 0.85rem;
  padding: 0.6rem 0.75rem;
  border-radius: 0.5rem;
  background: rgb(248 250 252);
  border: 1px solid rgb(226 232 240);
  font-size: 0.75rem;
  color: rgb(71 85 105);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.65rem 1.15rem;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}
.legend-dot {
  display: inline-block;
  width: 11px;
  height: 11px;
  border-radius: 3px;
  flex-shrink: 0;
}
.legend-dot.cell-status-ok { background: rgb(34 197 94); }
.legend-dot.cell-status-warning { background: rgb(234 179 8); }
.legend-dot.cell-status-error { background: rgb(239 68 68); }
.legend-item--inbound {
  color: rgb(51 65 85);
}
.legend-chip {
  display: inline-block;
  padding: 0.1rem 0.35rem;
  border-radius: 0.25rem;
  font-size: 0.65rem;
  font-weight: 600;
  background: rgb(219 234 254);
  color: rgb(29 78 216);
}
.legend-chip--rec {
  background: rgb(226 232 240);
  color: rgb(51 65 85);
}
</style>
