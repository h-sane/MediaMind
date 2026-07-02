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

export function ScanProgress({ libraryId, job }: Props): React.JSX.Element {
  const cancel = useCancelScan(libraryId, job.id)
  const isCancelling = cancel.isPending || job.state === 'cancelled'

  const pct = job.total > 0 ? Math.round((job.done / job.total) * 100) : 0
  const phase = job.phase || 'starting'

  return (
    <div className="rounded-xl border border-zinc-200 bg-white px-5 py-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-sm font-medium capitalize">{phase}</p>
          {job.total > 0 && (
            <p className="mt-0.5 text-xs text-zinc-400">
              {job.done.toLocaleString()} / {job.total.toLocaleString()} files
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

      {job.state === 'succeeded' && job.result && (
        <p className="mt-2 text-xs text-zinc-500">
          Found {(job.result.groups as number).toLocaleString()} groups ·{' '}
          {formatBytes(job.result.reclaimable_bytes as number)} reclaimable
        </p>
      )}
    </div>
  )
}
