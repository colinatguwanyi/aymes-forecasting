<template>
  <div class="timeline-bar">
    <div class="mb-4 flex flex-wrap items-center gap-4 text-sm">
      <span class="font-medium text-neutral-700">Legend</span>
      <template v-for="seg in segments" :key="seg.key">
        <span class="flex items-center gap-2">
          <span
            class="inline-block h-4 rounded min-w-[12px]"
            :style="{ backgroundColor: segmentColor(seg.key) }"
          />
          <span class="text-neutral-600">{{ seg.label }}</span>
        </span>
      </template>
      <span class="flex items-center gap-2">
        <span class="inline-block h-0.5 w-4 border-t-2 border-red-600" />
        <span class="text-neutral-600">Stockout</span>
      </span>
      <span class="flex items-center gap-2">
        <span class="inline-block h-0.5 w-4 border-t-2 border-emerald-600" />
        <span class="text-neutral-600">Receipt</span>
      </span>
      <span class="flex items-center gap-2">
        <span class="inline-block h-0.5 w-4 border-t-2 border-amber-600" />
        <span class="text-neutral-600">Need by</span>
      </span>
    </div>

    <div class="relative overflow-x-auto rounded-lg border border-neutral-200 bg-white">
      <div
        ref="gridEl"
        class="timeline-grid"
        :style="gridStyle"
      >
        <!-- Row 1: Week column headers -->
        <template v-for="(label, i) in weekLabels" :key="'h-' + i">
          <div
            class="timeline-cell border-r border-neutral-200 py-2 text-center text-xs font-medium text-neutral-500"
            :style="{ gridColumn: `${i + 1}`, gridRow: 1 }"
            :title="label"
          >
            {{ formatWeekLabel(label) }}
          </div>
        </template>

        <!-- Row 2: Segment bars (each spans columns) -->
        <div
          v-for="seg in segments"
          :key="seg.key"
          class="timeline-segment col-span-1 rounded py-2 text-center text-xs font-medium text-white"
          :style="segmentCellStyle(seg)"
          :title="seg.tooltip"
        >
          {{ seg.label }}
        </div>
      </div>

      <!-- SVG overlay for markers (vertical lines) -->
      <svg
        v-if="markers.length"
        class="pointer-events-none absolute left-0 top-0 h-16 w-full"
        style="min-height: 4rem"
        preserveAspectRatio="none"
      >
        <line
          v-for="m in markers"
          :key="m.key"
          :x1="markerX(m.week_index) + '%'"
          :y1="0"
          :x2="markerX(m.week_index) + '%'"
          :y2="100"
          :stroke="markerColor(m.type)"
          stroke-width="2"
          stroke-dasharray="4 2"
        />
      </svg>

      <!-- Marker labels row -->
      <div class="relative flex border-t border-neutral-200 bg-neutral-50 py-2" :style="{ minHeight: '2.5rem' }">
        <template v-for="m in markers" :key="m.key">
          <div
            class="absolute flex flex-col items-center text-xs"
            :style="{ left: markerX(m.week_index) + '%', transform: 'translateX(-50%)' }"
          >
            <span
              class="font-medium whitespace-nowrap"
              :class="{
                'text-red-600': m.type === 'stockout',
                'text-emerald-600': m.type === 'receipt',
                'text-amber-600': m.type === 'need_by',
              }"
              :title="m.tooltip"
            >
              {{ m.label }}{{ m.qty ? ` (${m.qty})` : '' }}
            </span>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

export interface TimelineSegment {
  key: string
  label: string
  start_week_index: number
  duration_weeks: number
  tooltip: string
}

export interface TimelineMarker {
  key: string
  label: string
  week_index: number
  type: 'stockout' | 'receipt' | 'need_by'
  tooltip: string
  qty?: string
}

const props = withDefaults(
  defineProps<{
    horizonWeeks?: number
    weekLabels: string[]
    segments: TimelineSegment[]
    markers: TimelineMarker[]
  }>(),
  { horizonWeeks: 26 }
)

const gridEl = ref<HTMLElement | null>(null)

const weekLabels = computed(() => props.weekLabels.length ? props.weekLabels : Array.from({ length: props.horizonWeeks }, (_, i) => `W${i + 1}`))

const gridStyle = computed(() => ({
  display: 'grid',
  gridTemplateColumns: `repeat(${weekLabels.value.length}, minmax(0, 1fr))`,
  gridTemplateRows: 'auto auto',
  minWidth: `${weekLabels.value.length * 24}px`,
}))

function segmentColor(key: string): string {
  const colors: Record<string, string> = {
    production: '#64748b',
    slot_wait: '#475569',
    haulage: '#334155',
    putaway: '#1e293b',
    padding: '#0f172a',
  }
  return colors[key] ?? '#94a3b8'
}

function markerColor(type: string): string {
  if (type === 'stockout') return '#dc2626'
  if (type === 'receipt') return '#059669'
  if (type === 'need_by') return '#d97706'
  return '#6b7280'
}

function formatWeekLabel(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso + 'T00:00:00')
  const m = d.getMonth() + 1
  const day = d.getDate()
  return `${m}/${day}`
}

function segmentCellStyle(seg: TimelineSegment): Record<string, string> {
  const start = seg.start_week_index + 1
  const span = Math.max(1, Math.round(seg.duration_weeks))
  const end = start + span
  return {
    gridColumn: `${start} / ${end}`,
    gridRow: '2',
    backgroundColor: segmentColor(seg.key),
  }
}

function markerX(weekIndex: number): number {
  const n = weekLabels.value.length
  if (n <= 0) return 0
  const i = Math.max(0, Math.min(weekIndex, n - 1))
  return ((i + 0.5) / n) * 100
}
</script>

<style scoped>
.timeline-grid {
  gap: 0;
}
.timeline-cell {
  min-width: 0;
}
.timeline-segment {
  min-height: 2rem;
}
</style>
