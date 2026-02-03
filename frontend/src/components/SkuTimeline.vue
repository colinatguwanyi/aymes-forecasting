<template>
  <div class="sku-timeline">
    <div class="timeline-rows">
      <div class="timeline-row week-labels">
        <span class="row-label">Week</span>
        <div class="week-cells">
          <span
            v-for="w in weeks"
            :key="w"
            class="week-cell week-label"
          >{{ formatWeek(w) }}</span>
        </div>
      </div>
      <div class="timeline-row projected-row">
        <span class="row-label">Projected</span>
        <div class="week-cells">
          <span
            v-for="w in weeks"
            :key="w"
            :class="['week-cell', 'projected-cell', projectedCellClass(w)]"
            :title="`${projectedQty(w)} · ${projectedWoc(w)} woc`"
          >{{ projectedQty(w) }}</span>
        </div>
      </div>
      <div class="timeline-row inbound-row">
        <span class="row-label">Inbound</span>
        <div class="week-cells">
          <span
            v-for="w in weeks"
            :key="w"
            class="week-cell inbound-cell"
          >{{ inboundLabel(w) }}</span>
        </div>
      </div>
    </div>
    <p class="timeline-legend muted">
      <span class="legend-dot cell-status-ok"></span> Healthy
      <span class="legend-dot cell-status-warning"></span> Low cover
      <span class="legend-dot cell-status-error"></span> Stockout
      <span class="legend-inbound">Order</span> Planned order · Receipt = actual
    </p>
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

const weeks = computed(() => {
  const set = new Set<string>()
  props.projected.forEach((p) => set.add(p.week_start))
  props.plannedOrders.forEach((o) => set.add(o.week_start))
  props.receipts.forEach((r) => set.add(r.week_start))
  return Array.from(set).sort()
})

const projectedByWeek = computed(() => {
  const m = new Map<string, ProjectedInventory>()
  props.projected.forEach((p) => m.set(p.week_start, p))
  return m
})

const ordersByWeek = computed(() => {
  const m = new Map<string, PlannedOrder[]>()
  props.plannedOrders.forEach((o) => {
    const list = m.get(o.week_start) ?? []
    list.push(o)
    m.set(o.week_start, list)
  })
  return m
})

const receiptsByWeek = computed(() => {
  const m = new Map<string, Receipt[]>()
  props.receipts.forEach((r) => {
    const list = m.get(r.week_start) ?? []
    list.push(r)
    m.set(r.week_start, list)
  })
  return m
})

function formatWeek(week: string): string {
  if (!week) return '—'
  return week.slice(0, 10)
}

function projectedCellClass(week: string): string {
  const p = projectedByWeek.value.get(week)
  if (!p) return ''
  if (p.stockout) return 'cell-status-error'
  if (p.weeks_of_cover != null) {
    const woc = parseFloat(p.weeks_of_cover)
    if (woc < 2) return 'cell-status-warning'
  }
  return 'cell-status-ok'
}

function projectedQty(week: string): string {
  const p = projectedByWeek.value.get(week)
  return p ? p.projected_qty : '—'
}

function projectedWoc(week: string): string {
  const p = projectedByWeek.value.get(week)
  return p?.weeks_of_cover ?? '—'
}

function inboundLabel(week: string): string {
  const orders = ordersByWeek.value.get(week) ?? []
  const recs = receiptsByWeek.value.get(week) ?? []
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
  padding-bottom: 0.5rem;
}
.timeline-rows {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: max-content;
}
.timeline-row {
  display: flex;
  align-items: stretch;
  font-size: 0.8125rem;
}
.row-label {
  width: 72px;
  min-width: 72px;
  padding: 0.35rem 0.5rem;
  font-weight: 500;
  color: var(--muted);
  flex-shrink: 0;
}
.week-cells {
  display: flex;
  gap: 2px;
}
.week-cell {
  min-width: 56px;
  padding: 0.35rem 0.4rem;
  text-align: center;
  border: 1px solid var(--border);
  background: var(--main-bg);
}
.week-label {
  font-size: 0.75rem;
  color: var(--muted);
}
.projected-cell.cell-status-error {
  background: rgba(153, 27, 27, 0.15);
  color: var(--error);
}
.projected-cell.cell-status-warning {
  background: rgba(180, 83, 9, 0.12);
  color: var(--warning);
}
.projected-cell.cell-status-ok {
  background: rgba(22, 101, 52, 0.08);
  color: var(--success);
}
.inbound-cell {
  font-size: 0.75rem;
  color: var(--info);
}
.timeline-legend {
  margin-top: 0.75rem;
  font-size: 0.75rem;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
}
.legend-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 0.2rem;
}
.legend-dot.cell-status-ok { background: rgba(22, 101, 52, 0.3); }
.legend-dot.cell-status-warning { background: rgba(180, 83, 9, 0.3); }
.legend-dot.cell-status-error { background: rgba(153, 27, 27, 0.3); }
.legend-inbound { color: var(--accent); }
</style>
