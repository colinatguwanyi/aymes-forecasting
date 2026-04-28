import { computed, reactive } from 'vue'
import { normalizeApiError } from '@/api/client'
import type { OperationState } from '@/types/operation'

const DEFAULT_TIMEOUT_MS = 120_000

interface OperationUpdate {
  id?: string
  message?: string
  code?: string
  detail?: string
  statusCode?: number
  progressPercent?: number
  error?: string
  nextActions?: string[]
  technicalDetails?: unknown
}

interface RunWithOperationOptions {
  id?: string
  timeoutMs?: number
  startMessage?: string
  runningMessage?: string
  successMessage?: string | ((result: unknown) => string)
  timeoutMessage?: string
  timeoutDetail?: string
  nextActions?: string[]
}

function nowIso(): string {
  return new Date().toISOString()
}

function applyUpdate(state: OperationState, update?: OperationUpdate): void {
  if (!update) return
  if (update.id !== undefined) state.id = update.id
  if (update.message !== undefined) state.message = update.message
  if (update.code !== undefined) state.code = update.code
  if (update.detail !== undefined) state.detail = update.detail
  if (update.statusCode !== undefined) state.statusCode = update.statusCode
  if (update.progressPercent !== undefined) state.progressPercent = update.progressPercent
  if (update.error !== undefined) state.error = update.error
  if (update.nextActions !== undefined) state.nextActions = update.nextActions
  if (update.technicalDetails !== undefined) state.technicalDetails = update.technicalDetails
}

export function useOperation(initialName = 'Operation') {
  const operation = reactive<OperationState>({
    name: initialName,
    status: 'idle',
    message: 'Ready',
  })

  const isRunning = computed(() => operation.status === 'starting' || operation.status === 'running')

  function startOperation(name = initialName, update?: OperationUpdate): void {
    operation.name = name
    operation.status = 'starting'
    operation.message = update?.message || 'Starting...'
    operation.code = update?.code
    operation.detail = update?.detail
    operation.statusCode = update?.statusCode
    operation.progressPercent = update?.progressPercent
    operation.startedAt = nowIso()
    operation.completedAt = undefined
    operation.error = undefined
    operation.nextActions = update?.nextActions
    operation.technicalDetails = update?.technicalDetails
    operation.id = update?.id
    operation.status = 'running'
    if (!update?.message) operation.message = 'Running...'
  }

  function completeOperation(update?: OperationUpdate): void {
    operation.status = 'completed'
    operation.message = update?.message || 'Completed'
    operation.completedAt = nowIso()
    operation.error = undefined
    operation.code = undefined
    operation.statusCode = undefined
    applyUpdate(operation, update)
  }

  function failOperation(error: unknown, update?: OperationUpdate): void {
    const normalized = normalizeApiError(error)
    operation.status = 'failed'
    operation.message = update?.message || normalized.message || 'Operation failed'
    operation.code = update?.code || normalized.code
    operation.detail = update?.detail || normalized.detail
    operation.statusCode = update?.statusCode || normalized.statusCode
    operation.error = update?.error || normalized.message
    operation.nextActions = update?.nextActions || normalized.nextActions
    operation.technicalDetails = update?.technicalDetails || normalized.technicalDetails
    operation.completedAt = nowIso()
    applyUpdate(operation, update)
  }

  function timeoutOperation(update?: OperationUpdate): void {
    operation.status = 'timed_out'
    operation.message = update?.message || 'The request did not return in time.'
    operation.code = update?.code || 'timeout'
    operation.statusCode = update?.statusCode
    operation.completedAt = nowIso()
    operation.nextActions = update?.nextActions || ['Refresh before retrying.']
    applyUpdate(operation, update)
  }

  function resetOperation(name = initialName): void {
    operation.name = name
    operation.status = 'idle'
    operation.message = 'Ready'
    operation.code = undefined
    operation.detail = undefined
    operation.statusCode = undefined
    operation.progressPercent = undefined
    operation.startedAt = undefined
    operation.completedAt = undefined
    operation.error = undefined
    operation.nextActions = undefined
    operation.technicalDetails = undefined
    operation.id = undefined
  }

  async function runWithOperation<T>(
    name: string,
    asyncFn: () => Promise<T>,
    options: RunWithOperationOptions = {},
  ): Promise<T | undefined> {
    const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS
    let timeoutId: ReturnType<typeof setTimeout> | undefined
    const timeoutSymbol = Symbol('operation-timeout')

    startOperation(name, { id: options.id, message: options.startMessage || 'Starting...' })
    operation.status = 'running'
    operation.message = options.runningMessage || 'Running...'

    try {
      const timeoutPromise = new Promise<typeof timeoutSymbol>((resolve) => {
        timeoutId = setTimeout(() => resolve(timeoutSymbol), timeoutMs)
      })
      const result = await Promise.race([asyncFn(), timeoutPromise])
      if (result === timeoutSymbol) {
        timeoutOperation({
          message: options.timeoutMessage || 'The request did not return in time.',
          detail: options.timeoutDetail,
          nextActions: options.nextActions || ['Refresh before retrying.'],
        })
        return undefined
      }
      const successMessage =
        typeof options.successMessage === 'function'
          ? options.successMessage(result)
          : options.successMessage || 'Completed'
      completeOperation({ message: successMessage })
      return result
    } catch (error) {
      failOperation(error, { technicalDetails: error })
      return undefined
    } finally {
      if (timeoutId) clearTimeout(timeoutId)
    }
  }

  return {
    operation,
    isRunning,
    startOperation,
    completeOperation,
    failOperation,
    timeoutOperation,
    resetOperation,
    runWithOperation,
  }
}
