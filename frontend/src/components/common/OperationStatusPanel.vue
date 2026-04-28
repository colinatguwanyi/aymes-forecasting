<template>
  <section
    v-if="operation.status !== 'idle' || showWhenIdle"
    class="card card-body operation-panel"
    :class="`operation-panel--${operation.status}`"
    role="status"
  >
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div class="flex flex-wrap items-center gap-2">
          <span class="operation-panel__badge" :class="`operation-panel__badge--${operation.status}`">
            {{ statusLabel }}
          </span>
          <h3 class="operation-panel__title">{{ operation.name }}</h3>
        </div>
        <p class="operation-panel__message">{{ operation.message }}</p>
        <p v-if="operation.code || operation.statusCode" class="operation-panel__meta">
          <span v-if="operation.statusCode">HTTP {{ operation.statusCode }}</span>
          <span v-if="operation.statusCode && operation.code"> · </span>
          <code v-if="operation.code">{{ operation.code }}</code>
        </p>
        <p v-if="operation.detail" class="operation-panel__detail">{{ operation.detail }}</p>
      </div>
      <div class="text-xs text-slate-500 text-right">
        <span v-if="isRunning && elapsedLabel">Elapsed {{ elapsedLabel }}</span>
        <span v-else-if="completedLabel">Completed {{ completedLabel }}</span>
      </div>
    </div>

    <div v-if="operation.progressPercent != null" class="operation-panel__progress" aria-label="Operation progress">
      <div class="operation-panel__progress-fill" :style="{ width: `${boundedProgress}%` }" />
    </div>

    <div v-if="operation.error" class="operation-panel__error">
      {{ operation.error }}
    </div>

    <ul v-if="operation.nextActions?.length" class="operation-panel__actions">
      <li v-for="action in operation.nextActions" :key="action">{{ action }}</li>
    </ul>

    <details v-if="operation.technicalDetails !== undefined" class="operation-panel__technical">
      <summary>Technical details</summary>
      <pre>{{ technicalDetails }}</pre>
    </details>

    <div v-if="$slots.retry" class="mt-3">
      <slot name="retry" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type { OperationState, OperationStatus } from '@/types/operation'

const props = withDefaults(
  defineProps<{
    operation: OperationState
    showWhenIdle?: boolean
  }>(),
  {
    showWhenIdle: false,
  },
)

const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | undefined

const isRunning = computed(() => props.operation.status === 'starting' || props.operation.status === 'running')

const statusLabels: Record<OperationStatus, string> = {
  idle: 'Idle',
  starting: 'Starting',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
  timed_out: 'Timed out',
}

const statusLabel = computed(() => statusLabels[props.operation.status])

const boundedProgress = computed(() => {
  const raw = props.operation.progressPercent ?? 0
  return Math.min(100, Math.max(0, raw))
})

function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes === 0) return `${seconds}s`
  return `${minutes}m ${seconds.toString().padStart(2, '0')}s`
}

const elapsedLabel = computed(() => {
  if (!props.operation.startedAt) return ''
  return formatDuration(now.value - new Date(props.operation.startedAt).getTime())
})

const completedLabel = computed(() => {
  if (!props.operation.completedAt) return ''
  return new Date(props.operation.completedAt).toLocaleTimeString()
})

const technicalDetails = computed(() => {
  const details = props.operation.technicalDetails
  if (typeof details === 'string') return details
  try {
    return JSON.stringify(details, null, 2)
  } catch {
    return String(details)
  }
})

onMounted(() => {
  timer = setInterval(() => {
    if (isRunning.value) now.value = Date.now()
  }, 1000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.operation-panel {
  border-width: 1px;
}
.operation-panel--completed {
  border-color: rgb(187 247 208);
  background: rgb(240 253 244);
}
.operation-panel--failed,
.operation-panel--timed_out {
  border-color: rgb(254 202 202);
  background: rgb(254 242 242);
}
.operation-panel--running,
.operation-panel--starting {
  border-color: rgb(191 219 254);
  background: rgb(239 246 255);
}
.operation-panel__badge {
  display: inline-flex;
  align-items: center;
  border-radius: 9999px;
  padding: 0.125rem 0.5rem;
  font-size: 0.75rem;
  font-weight: 600;
}
.operation-panel__badge--completed {
  background: rgb(220 252 231);
  color: rgb(21 128 61);
}
.operation-panel__badge--failed,
.operation-panel__badge--timed_out {
  background: rgb(254 226 226);
  color: rgb(185 28 28);
}
.operation-panel__badge--running,
.operation-panel__badge--starting {
  background: rgb(219 234 254);
  color: rgb(29 78 216);
}
.operation-panel__badge--idle,
.operation-panel__badge--cancelled {
  background: rgb(241 245 249);
  color: rgb(71 85 105);
}
.operation-panel__title {
  margin: 0;
  color: rgb(30 41 59);
  font-size: 0.95rem;
  font-weight: 600;
}
.operation-panel__message {
  margin-top: 0.5rem;
  color: rgb(51 65 85);
  font-size: 0.875rem;
}
.operation-panel__detail {
  margin-top: 0.25rem;
  color: rgb(71 85 105);
  font-size: 0.8125rem;
}
.operation-panel__meta {
  margin-top: 0.25rem;
  color: rgb(100 116 139);
  font-size: 0.75rem;
}
.operation-panel__meta code {
  border-radius: 0.25rem;
  background: rgb(226 232 240);
  padding: 0.05rem 0.25rem;
}
.operation-panel__progress {
  height: 0.5rem;
  margin-top: 0.75rem;
  overflow: hidden;
  border-radius: 9999px;
  background: rgb(226 232 240);
}
.operation-panel__progress-fill {
  height: 100%;
  border-radius: 9999px;
  background: rgb(37 99 235);
  transition: width 150ms ease;
}
.operation-panel__error {
  margin-top: 0.75rem;
  white-space: pre-wrap;
  border-radius: 0.5rem;
  border: 1px solid rgb(252 165 165);
  background: rgb(254 226 226);
  padding: 0.75rem;
  color: rgb(127 29 29);
  font-size: 0.875rem;
}
.operation-panel__actions {
  margin: 0.75rem 0 0;
  padding-left: 1.25rem;
  color: rgb(51 65 85);
  font-size: 0.875rem;
  list-style: disc;
}
.operation-panel__technical {
  margin-top: 0.75rem;
  font-size: 0.8125rem;
  color: rgb(71 85 105);
}
.operation-panel__technical summary {
  cursor: pointer;
  font-weight: 600;
}
.operation-panel__technical pre {
  max-height: 16rem;
  margin-top: 0.5rem;
  overflow: auto;
  border-radius: 0.5rem;
  background: rgb(15 23 42);
  padding: 0.75rem;
  color: rgb(220 252 231);
}
</style>
