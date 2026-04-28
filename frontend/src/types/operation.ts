export type OperationStatus = 'idle' | 'starting' | 'running' | 'completed' | 'failed' | 'cancelled' | 'timed_out'

export interface OperationState {
  id?: string
  name: string
  status: OperationStatus
  message: string
  code?: string
  detail?: string
  statusCode?: number
  progressPercent?: number
  startedAt?: string
  completedAt?: string
  error?: string
  nextActions?: string[]
  technicalDetails?: unknown
}
