import { useEffect, useState } from 'react'
import type { JobSnapshot } from '../api/client'
import { useCancelScan } from '../api/hooks'

interface Props {
  libraryId: string
  job: JobSnapshot
}

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  if (b < 1024 * 1024 * 1024) return `${(b / (1024 * 1024)).toFixed(1)} MB`
  return `${(b / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${s % 60}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

export function ScanProgress({ libraryId, job }: Props): React.JSX.Element {
  const cancel = useCancelScan(libraryId, job.id)
  const isCancelling = cancel.isPending || job.state === 'cancelled'

  const pct = job.total > 0 ? Math.round((job.done / job.total) * 100) : 0
  const phase = job.phase || 'starting'

  // Re-render every second while running so the ETA keeps counting down
  // between the backend's throttled progress events (~5/sec at most).
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (job.state !== 'running') return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [job.state])

  const elapsed = now / 1000 - job.created_at
  const rate = job.done > 0 && elapsed > 0 ? job.done / elapsed : 0
  const remaining = job.total > 0 && rate > 0 ? (job.total - job.done) / rate : null
  const eta = job.state === 'running' && remaining !== null ? formatDuration(remaining) : null
  const finishedIn =
    job.state !== 'running' && job.finished_at ? formatDuration(job.finished_at - job.created_at) : null

  return (
    <div className="rounded-xl border border-zinc-200 bg-white px-5 py-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-sm font-medium capitalize">{phase}</p>
          {job.total > 0 && (
            <p className="mt-0.5 text-xs text-zinc-400">
              {job.done.toLocaleString()} / {job.total.toLocaleString()} files
              {eta && ` · ~${eta} left`}
              {finishedIn && ` · finished in ${finishedIn}`}
            </p>
          )}
        </div>
        <button
          onClick={() => cancel.mutate()}
          disabled={isCancelling}
          className="rounded-md px-3 py-1.5 text-xs text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 disabled:opacity-50"
        >
          {isCancelling ? 'Cancelling…' : 'Cancel'}
        </button>
      </div>

      <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-100">
        <div
          className="h-full rounded-full bg-zinc-900 transition-all duration-300"
          style={{ width: job.total > 0 ? `${pct}%` : '100%' }}
        />
      </div>

      {job.state === 'succeeded' && job.result && job.type === 'dedupe' && (
        <p className="mt-2 text-xs text-zinc-500">
          Found {(job.result.groups as number).toLocaleString()} groups ·{' '}
          {formatBytes(job.result.reclaimable_bytes as number)} reclaimable
        </p>
      )}
      {job.state === 'succeeded' && job.result && job.type === 'faces' && (
        <p className="mt-2 text-xs text-zinc-500">
          {(job.result.people as number).toLocaleString()} people ·{' '}
          {(job.result.faces as number).toLocaleString()} faces detected
        </p>
      )}
    </div>
  )
}
