import { useAppStore } from '../stores/app'
import { useJobsStore, selectJobForLibrary } from '../stores/jobs'
import { useStartScan, useDuplicates } from '../api/hooks'
import { ScanProgress } from '../components/ScanProgress'
import type { Library } from '../api/client'

interface Props {
  library: Library
}

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  if (b < 1024 * 1024 * 1024) return `${(b / (1024 * 1024)).toFixed(1)} MB`
  return `${(b / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

export function LibraryDetail({ library }: Props): React.JSX.Element {
  const navigate = useAppStore((s) => s.navigate)
  const back = useAppStore((s) => s.back)
  const jobs = useJobsStore((s) => s.jobs)
  const activeJob = selectJobForLibrary(jobs, library.id)

  const startScan = useStartScan(library.id)
  const { data: dups, isError: dupsError } = useDuplicates(library.id)

  const hasResults = !!dups && dups.groups.length > 0
  const isScanning = !!activeJob && activeJob.state !== 'succeeded'

  return (
    <section className="mx-auto w-full max-w-3xl px-8 py-12">
      {/* Back nav */}
      <button
        onClick={back}
        className="mb-6 flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600"
      >
        ← All folders
      </button>

      {/* Header */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold tracking-tight">{library.name}</h2>
        <p className="mt-1 text-xs text-zinc-400 truncate">{library.path}</p>
      </div>

      {/* Duplicates action card */}
      <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h3 className="text-sm font-semibold">Duplicates</h3>
            <p className="mt-0.5 text-xs text-zinc-500">
              Find exact copies and visually similar images or videos.
            </p>
          </div>
        </div>

        {/* Scan states */}
        {isScanning && activeJob ? (
          <ScanProgress libraryId={library.id} job={activeJob} />
        ) : hasResults && dups ? (
          <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-5 py-4">
            <p className="text-sm font-medium">
              {dups.summary.groups.toLocaleString()} groups ·{' '}
              {dups.summary.files.toLocaleString()} files ·{' '}
              {formatBytes(dups.summary.reclaimable_bytes)} reclaimable
            </p>
            <div className="mt-3 flex gap-2">
              <button
                onClick={() => navigate({ name: 'dedupe-review', libraryId: library.id })}
                className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-700 active:scale-[0.98]"
              >
                Review duplicates
              </button>
              <button
                onClick={() => startScan.mutate()}
                disabled={startScan.isPending}
                className="rounded-lg border border-zinc-200 px-4 py-2 text-sm text-zinc-600 transition hover:bg-zinc-50 disabled:opacity-50"
              >
                Rescan
              </button>
            </div>
          </div>
        ) : (
          <div>
            {dupsError && !hasResults && (
              <p className="mb-3 text-xs text-zinc-400">No previous scan found.</p>
            )}
            {startScan.isError && (
              <p className="mb-3 text-sm text-red-600">{startScan.error.message}</p>
            )}
            <button
              onClick={() => startScan.mutate()}
              disabled={startScan.isPending}
              className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-700 active:scale-[0.98] disabled:opacity-50"
            >
              {startScan.isPending ? 'Starting…' : 'Find duplicates'}
            </button>
          </div>
        )}
      </div>

      {/* People — placeholder for M5 */}
      <div className="mt-4 rounded-2xl border border-dashed border-zinc-200 p-6">
        <h3 className="text-sm font-semibold text-zinc-400">People</h3>
        <p className="mt-0.5 text-xs text-zinc-400">Face recognition coming soon.</p>
      </div>
    </section>
  )
}
