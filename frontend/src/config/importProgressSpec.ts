/**
 * Standard contract for IngestionRun.progress_meta during imports (v1) + legacy keys.
 * Backend: see backend/app/ingestion_progress.py
 */
import api from '@/api/client'

export const IMPORT_PROGRESS_HINT_UPLOAD = `The bar tracks sending the file to the API. Staging and validation on the server can take much longer (large or historical files). Keep this tab open; check Network if the request is still pending.`

export const IMPORT_PROGRESS_HINT_EXECUTE = `The server is writing canonical planning tables. Progress updates when the job saves checkpoints (long runs). Keep this tab open until the request finishes.`

export interface ImportProgressDisplay {
  message: string
  percent: number | null
  detail: string | null
  phaseLabel: string | null
}

/** v1 + backwards-compatible display mapping for any progress_meta from GET /ingestion/runs/{id} */
export function importProgressMetaToDisplay(meta: unknown): ImportProgressDisplay {
  if (meta == null || typeof meta !== 'object') {
    return {
      message: 'Working on server…',
      percent: null,
      detail: null,
      phaseLabel: null,
    }
  }
  const m = meta as Record<string, unknown>
  const v1message = typeof m.import_message === 'string' && m.import_message.trim() ? m.import_message.trim() : null
  const phase = typeof m.import_phase === 'string' && m.import_phase ? m.import_phase : null
  const detailV1 = typeof m.import_detail === 'string' && m.import_detail ? m.import_detail : null
  let percent: number | null = null
  if (typeof m.import_percent === 'number' && !Number.isNaN(m.import_percent)) {
    percent = Math.max(0, Math.min(100, Math.round(m.import_percent)))
  }

  if (v1message) {
    return { message: v1message, percent, detail: detailV1, phaseLabel: phase }
  }

  // Legacy: SOH, Sales Out, BLP coverage, etc.
  if (typeof m.daily_batches_done === 'number' && m.daily_batches_done > 0) {
    return {
      message: `Writing daily SOH (batch ${m.daily_batches_done})…`,
      percent,
      detail: detailV1,
      phaseLabel: 'soh_daily',
    }
  }
  if (typeof m.batches_done === 'number' && m.batches_done > 0) {
    const wk = m.weeks_done
    return {
      message:
        typeof wk === 'number'
          ? `Writing weekly demand (batch ${m.batches_done}, ${wk.toLocaleString()} weeks)…`
          : `Processing batch ${m.batches_done}…`,
      percent,
      detail: null,
      phaseLabel: 'sales_out_write',
    }
  }
  if (m.pct_coverage_codes != null || m.mapped_codes != null) {
    const p = m.pct_coverage_codes
    const d =
      typeof p === 'number'
        ? `Code coverage ${p}%`
        : m.mapped_codes != null && m.total_unique_codes != null
          ? `Mapped ${String(m.mapped_codes)} / ${String(m.total_unique_codes)} codes`
          : null
    return {
      message: 'Analysing warehouse code coverage…',
      percent: null,
      detail: d,
      phaseLabel: 'blp_soh',
    }
  }
  if (m.warehouse_code) {
    return {
      message: 'Processing warehouse feed…',
      percent: null,
      detail: `Warehouse: ${String(m.warehouse_code)}`,
      phaseLabel: 'warehouse',
    }
  }
  return { message: 'Working on server…', percent, detail: detailV1, phaseLabel: phase }
}

const PROGRESS_POLL_MS = 1200

/**
 * Poll GET /ingestion/runs/{id} while a long transform runs. Stop the interval when the returned
 * disposer is called (typically when the execute HTTP request finishes).
 */
export function startImportProgressPoll(
  runId: string,
  onDisplay: (d: ImportProgressDisplay) => void,
): () => void {
  let timer: ReturnType<typeof setInterval> | null = null
  const tick = async () => {
    try {
      const { data } = await api.get<{
        status: string
        progress_meta?: unknown
      }>(`/ingestion/runs/${runId}`)
      onDisplay(importProgressMetaToDisplay(data.progress_meta))
      if (data.status === 'failed') {
        onDisplay({
          message: 'Run reported failed; see runs table for detail.',
          percent: null,
          detail: null,
          phaseLabel: 'failed',
        })
      }
    } catch {
      /* ignore transient poll errors */
    }
  }
  void tick()
  timer = setInterval(tick, PROGRESS_POLL_MS)
  return () => {
    if (timer != null) {
      clearInterval(timer)
      timer = null
    }
  }
}
