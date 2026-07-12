import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useHealth } from './api/hooks'
import { useProgressSocket } from './api/progress'
import { useJobsStore } from './stores/jobs'
import { ExplorerShell } from './explorer/ExplorerShell'

// ---------------------------------------------------------------------------
// Invalidate TanStack queries when jobs complete
// ---------------------------------------------------------------------------

function JobInvalidator(): null {
  const jobs = useJobsStore((s) => s.jobs)
  const qc = useQueryClient()

  useEffect(() => {
    for (const job of Object.values(jobs)) {
      if (job.state === 'succeeded') {
        if (job.type === 'dedupe') {
          qc.invalidateQueries({ queryKey: ['duplicates', job.library_id] })
        } else if (job.type === 'faces') {
          qc.invalidateQueries({ queryKey: ['persons', job.library_id] })
          qc.invalidateQueries({ queryKey: ['pending', job.library_id] })
          qc.invalidateQueries({ queryKey: ['organize-preview', job.library_id] })
          qc.invalidateQueries({ queryKey: ['multi-person', job.library_id] })
        } else if (job.type === 'provider-download') {
          qc.invalidateQueries({ queryKey: ['providers'] })
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobs])

  return null
}

// ---------------------------------------------------------------------------
// Engine status — silent once ready; a real Explorer window has no branded
// header, so this only shows itself during the brief backend startup window.
// ---------------------------------------------------------------------------

function EngineStatusBanner(): React.JSX.Element | null {
  const { isError, isPending } = useHealth()
  if (!isPending && !isError) return null
  return (
    <div className="border-b border-amber-200 bg-amber-50 px-3 py-1 text-xs text-amber-700">
      {isPending ? 'Starting engine…' : 'Engine offline — retrying…'}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Root app
// ---------------------------------------------------------------------------

export default function App(): React.JSX.Element {
  // Mount the WS progress socket once for the app's lifetime.
  useProgressSocket()

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <JobInvalidator />
      <EngineStatusBanner />
      <ExplorerShell />
    </div>
  )
}
