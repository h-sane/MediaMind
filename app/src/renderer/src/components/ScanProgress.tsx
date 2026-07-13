import { useEffect, useRef, useState } from 'react'
import type { JobSnapshot } from '../api/client'
import { useCancelScan } from '../api/hooks'

interface Props {
  libraryId: string
  job: JobSnapshot
}

// Backend phase names (see core/jobs.py's report_progress callers) are short
// single words meant for logs, not the UI — map them to something a user
// reads without translating.
const PHASE_LABELS: Record<string, string> = {
  scanning: 'Scanning folders',
  reading: 'Reading file details',
  hashing: 'Comparing files',
  detecting: 'Detecting faces',
  clustering: 'Grouping people',
  saving: 'Saving results'
}

function phaseLabel(phase: string): string {
  if (!phase) return 'Starting'
  return PHASE_LABELS[phase] ?? phase.charAt(0).toUpperCase() + phase.slice(1)
}

// How long a phase can go without a progress update before the UI stops
// assuming it's just "between ticks" and instead tells the user this could
// be a stalled read (e.g. a slow network or cloud-sync path) rather than
// leaving them staring at frozen numbers with no explanation.
const STALL_WARNING_SECONDS = 20

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

  // Tracks when (phase, done, total) last actually changed — independent of
  // the 1s re-render above, which only drives the ETA clock. This is what
  // lets the UI tell a live-but-quiet scan apart from a genuinely stalled
  // one instead of just sitting on the same frozen numbers with no signal
  // either way (the exact complaint: "no way to confirm if this is actually
  // running or its stuck").
  const changeKey = `${job.phase}:${job.done}:${job.total}`
  const lastChangeRef = useRef<{ key: string; at: number }>({ key: changeKey, at: Date.now() })
  if (lastChangeRef.current.key !== changeKey) {
    lastChangeRef.current = { key: changeKey, at: Date.now() }
  }
  const sinceUpdate = Math.max(0, (now - lastChangeRef.current.at) / 1000)
  const stalled = job.state === 'running' && sinceUpdate > STALL_WARNING_SECONDS

  return (
    <div className="rounded-xl border border-zinc-200 bg-white px-5 py-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">{phaseLabel(phase)}</p>
          {job.total > 0 && (
            <p className="mt-0.5 text-xs text-zinc-400">
              {job.done.toLocaleString()} / {job.total.toLocaleString()} files
              {eta && ` · ~${eta} left`}
              {finishedIn && ` · finished in ${finishedIn}`}
            </p>
          )}
          {job.total === 0 && job.done > 0 && (
            <p className="mt-0.5 text-xs text-zinc-400">{job.done.toLocaleString()} files found…</p>
          )}
          {job.state === 'running' && (
            <p className={`mt-0.5 text-xs ${stalled ? 'font-medium text-amber-600' : 'text-zinc-300'}`}>
              {stalled
                ? `No update in ${Math.round(sinceUpdate)}s — this can happen on a slow network or ` +
                  `cloud-sync folder. It will resume or time out on its own; Cancel is safe if you'd ` +
                  `rather stop now.`
                : `Updated ${Math.round(sinceUpdate)}s ago`}
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
