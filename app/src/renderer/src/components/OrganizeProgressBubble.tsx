import { useEffect, useRef, useState } from 'react'
import { selectJobsByType, useJobsStore } from '../stores/jobs'
import { ScanProgress } from './ScanProgress'
import type { JobSnapshot } from '../api/client'

const AUTO_DISMISS_MS = 5000

function OrganizeBubbleCard({
  job,
  onDismiss
}: {
  job: JobSnapshot
  onDismiss: (jobId: string) => void
}): React.JSX.Element {
  const isTerminal = job.state === 'succeeded' || job.state === 'failed' || job.state === 'cancelled'
  const dismissedRef = useRef(false)
  useEffect(() => {
    if (!isTerminal || dismissedRef.current) return
    const id = setTimeout(() => {
      dismissedRef.current = true
      onDismiss(job.id)
    }, AUTO_DISMISS_MS)
    return () => clearTimeout(id)
  }, [isTerminal, job.id, onDismiss])

  return (
    <div className="relative w-80">
      <ScanProgress libraryId={job.library_id} job={job} />
      {isTerminal && (
        <button
          type="button"
          onClick={() => onDismiss(job.id)}
          aria-label="Dismiss"
          className="absolute right-2 top-2 text-zinc-400 hover:text-zinc-600"
        >
          ×
        </button>
      )}
    </div>
  )
}

/** Bottom-right stack of organize-execute jobs (mirrors FaceScanProgressBubble
 * / DeleteProgressBubble) — mounted once at the app root so a large "Organize"
 * batch's progress stays visible no matter which folder or tool the user
 * navigates to while it runs in the background (F8). */
export function OrganizeProgressBubble(): React.JSX.Element | null {
  const jobs = useJobsStore((s) => s.jobs)
  const organizeJobs = selectJobsByType(jobs, 'organize-execute')
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())

  const visible = organizeJobs.filter((j) => !dismissed.has(j.id))
  if (visible.length === 0) return null

  function dismiss(jobId: string): void {
    setDismissed((prev) => new Set(prev).add(jobId))
  }

  return (
    <div className="fixed bottom-4 right-4 z-40 flex flex-col-reverse gap-2">
      {visible.map((job) => (
        <OrganizeBubbleCard key={job.id} job={job} onDismiss={dismiss} />
      ))}
    </div>
  )
}
