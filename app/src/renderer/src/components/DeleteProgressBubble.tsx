import { useEffect, useRef, useState } from 'react'
import { useCancelJob, useExecuteJob } from '../api/hooks'
import { selectJobsByType, useJobsStore } from '../stores/jobs'
import type { JobSnapshot } from '../api/client'

interface ExecuteJobResult {
  planned: number
  handled: number
  ok: boolean
  manifest_path: string | null
  permanent: boolean
  error_count: number
  network_errors_only: boolean
  errors: { source: string; error: string }[]
}

function resultOf(job: JobSnapshot): ExecuteJobResult | null {
  return (job.result as unknown as ExecuteJobResult | null) ?? null
}

const AUTO_DISMISS_MS = 5000

function DeleteProgressCard({
  job,
  onDismiss
}: {
  job: JobSnapshot
  onDismiss: (jobId: string) => void
}): React.JSX.Element {
  const cancelJob = useCancelJob(job.id)
  const retryPermanent = useExecuteJob(job.library_id)
  const result = resultOf(job)
  const pct = job.total > 0 ? Math.round((job.done / job.total) * 100) : 0

  // Auto-dismiss clean terminal states after a few seconds — errors/failures
  // stay until the user acknowledges them (they may need the manifest path
  // or the permanent-delete retry action).
  const cleanTerminal =
    (job.state === 'succeeded' && (result?.error_count ?? 0) === 0) || job.state === 'cancelled'
  const dismissedRef = useRef(false)
  useEffect(() => {
    if (!cleanTerminal || dismissedRef.current) return
    const id = setTimeout(() => {
      dismissedRef.current = true
      onDismiss(job.id)
    }, AUTO_DISMISS_MS)
    return () => clearTimeout(id)
  }, [cleanTerminal, job.id, onDismiss])

  const showDismiss = job.state !== 'running' && job.state !== 'queued'
  const accent =
    job.state === 'failed' || (job.state === 'succeeded' && (result?.error_count ?? 0) > 0)
      ? 'border-red-200'
      : job.state === 'succeeded'
        ? 'border-green-200'
        : 'border-zinc-200'

  return (
    <div className={`w-80 rounded-lg border ${accent} bg-white p-3 text-sm shadow-lg`}>
      <div className="flex items-start justify-between gap-2">
        <p className="font-medium text-zinc-900">
          {job.state === 'queued' && `Preparing to delete ${job.total || '…'} files…`}
          {job.state === 'running' &&
            (job.phase === 'checking'
              ? `Preparing to delete ${job.total || '…'} files…`
              : `Deleting… ${job.done}/${job.total}`)}
          {job.state === 'succeeded' &&
            ((result?.error_count ?? 0) === 0
              ? `Deleted ${result?.handled ?? job.done} file${(result?.handled ?? job.done) === 1 ? '' : 's'}`
              : `Deleted ${result?.handled ?? 0} of ${result?.planned ?? job.total}; ${result?.error_count} failed`)}
          {job.state === 'failed' && `Delete failed: ${job.error || 'unknown error'}`}
          {job.state === 'cancelled' && `Cancelled — deleted ${job.done} of ${job.total}`}
        </p>
        {showDismiss && (
          <button
            type="button"
            onClick={() => onDismiss(job.id)}
            className="shrink-0 text-zinc-400 hover:text-zinc-600"
            aria-label="Dismiss"
          >
            ×
          </button>
        )}
      </div>

      {(job.state === 'queued' || job.state === 'running') && (
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-zinc-100">
          <div
            className="h-full rounded-full bg-zinc-900 transition-all duration-300"
            style={{ width: job.total > 0 ? `${pct}%` : '10%' }}
          />
        </div>
      )}

      {job.state === 'running' && job.phase === 'deleting' && (
        <button
          type="button"
          onClick={() => cancelJob.mutate()}
          disabled={cancelJob.isPending}
          className="mt-2 rounded-md px-2 py-1 text-xs text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 disabled:opacity-50"
        >
          {cancelJob.isPending ? 'Cancelling…' : 'Cancel'}
        </button>
      )}

      {job.state === 'succeeded' && (result?.error_count ?? 0) > 0 && (
        <>
          <ul className="mt-2 max-h-32 space-y-1 overflow-y-auto text-xs text-zinc-500">
            {result?.errors.map((e, i) => (
              <li key={i} className="truncate" title={`${e.source}: ${e.error}`}>
                {e.source.split(/[\\/]/).pop()}: {e.error}
              </li>
            ))}
          </ul>
          {result?.manifest_path && (
            <p className="mt-2 truncate text-[11px] text-zinc-400" title={result.manifest_path}>
              Details: {result.manifest_path}
            </p>
          )}
          {result?.network_errors_only && !result.permanent && (
            <button
              type="button"
              onClick={() =>
                retryPermanent.mutate({ expectedTrashCount: result.error_count, permanent: true })
              }
              disabled={retryPermanent.isPending}
              className="mt-2 w-full rounded-lg border border-red-200 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
            >
              Permanently delete the {result.error_count} that failed
            </button>
          )}
        </>
      )}
    </div>
  )
}

/** Bottom-right stack of background delete jobs (see useExecuteJob) — mounted
 * once at the app root so it stays visible across every folder/tool the user
 * navigates to while a bulk delete runs in the background. */
export function DeleteProgressBubble(): React.JSX.Element | null {
  const jobs = useJobsStore((s) => s.jobs)
  const executeJobs = selectJobsByType(jobs, 'dedupe-execute')
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())

  const visible = executeJobs.filter((j) => !dismissed.has(j.id))
  if (visible.length === 0) return null

  function dismiss(jobId: string): void {
    setDismissed((prev) => new Set(prev).add(jobId))
  }

  return (
    <div className="fixed bottom-4 right-4 z-40 flex flex-col-reverse gap-2">
      {visible.map((job) => (
        <DeleteProgressCard key={job.id} job={job} onDismiss={dismiss} />
      ))}
    </div>
  )
}
