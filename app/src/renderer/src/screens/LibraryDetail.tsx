import { useAppStore } from '../stores/app'
import { useJobsStore, selectJobForLibrary, selectFailedJobForLibrary } from '../stores/jobs'
import { useStartScan, useDuplicates, usePersons, useProviders } from '../api/hooks'
import { ScanProgress } from '../components/ScanProgress'
import { formatBytes } from '../lib/format'
import type { Library } from '../api/client'

interface Props {
  library: Library
}

export function LibraryDetail({ library }: Props): React.JSX.Element {
  const navigate = useAppStore((s) => s.navigate)
  const back = useAppStore((s) => s.back)
  const jobs = useJobsStore((s) => s.jobs)

  // Dedupe job and data
  const dedupeJob = selectJobForLibrary(jobs, library.id, 'dedupe')
  const facesJob = selectJobForLibrary(jobs, library.id, 'faces')
  const activeJob = dedupeJob ?? facesJob  // any active job for this library
  const failedDedupeJob = selectFailedJobForLibrary(jobs, library.id, 'dedupe')
  const failedFacesJob = selectFailedJobForLibrary(jobs, library.id, 'faces')

  const startScan = useStartScan(library.id)
  const { data: dups, isError: dupsError } = useDuplicates(library.id)
  const { data: providers } = useProviders()
  const { data: personsData, isError: personsError } = usePersons(library.id)

  const hasDedupeResults = !!dups && dups.groups.length > 0
  const isDedupeScanning = !!dedupeJob
  const isFaceScanning = !!facesJob

  const anyProviderInstalled = providers?.some((p) => p.installed) ?? false
  const hasPeopleResults = !!personsData && personsData.persons.length > 0

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

        {isDedupeScanning && dedupeJob ? (
          <ScanProgress libraryId={library.id} job={dedupeJob} />
        ) : hasDedupeResults && dups ? (
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
            {dupsError && !hasDedupeResults && !failedDedupeJob && (
              <p className="mb-3 text-xs text-zinc-400">No previous scan found.</p>
            )}
            {failedDedupeJob && (
              <p className="mb-3 text-sm text-red-600">
                Last scan failed: {failedDedupeJob.error || 'unknown error'}
              </p>
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

      {/* People card */}
      <div className="mt-4 rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
        <div className="mb-4">
          <h3 className="text-sm font-semibold">People</h3>
          <p className="mt-0.5 text-xs text-zinc-500">
            Cluster your media by the people in it using AI face recognition.
          </p>
        </div>

        {!anyProviderInstalled ? (
          /* No model installed yet */
          <div>
            <p className="mb-3 text-xs text-zinc-400">
              Face recognition needs a model. Download one to get started.
            </p>
            <button
              onClick={() => navigate({ name: 'providers', libraryId: library.id })}
              className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-700 active:scale-[0.98]"
            >
              Set up face recognition →
            </button>
          </div>
        ) : isFaceScanning && facesJob ? (
          /* Face scan in progress */
          <ScanProgress libraryId={library.id} job={facesJob} />
        ) : hasPeopleResults && personsData ? (
          /* Has results */
          <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-5 py-4">
            <p className="text-sm font-medium">
              {personsData.persons.length} {personsData.persons.length === 1 ? 'person' : 'people'} found
            </p>
            <div className="mt-3 flex gap-2">
              <button
                onClick={() => navigate({ name: 'people', libraryId: library.id })}
                className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-700 active:scale-[0.98]"
              >
                View people
              </button>
              <button
                onClick={() => navigate({ name: 'people', libraryId: library.id })}
                className="rounded-lg border border-zinc-200 px-4 py-2 text-sm text-zinc-600 transition hover:bg-zinc-50"
              >
                Rescan
              </button>
            </div>
          </div>
        ) : (
          /* Installed, no scan yet */
          <div>
            {personsError && !hasPeopleResults && !failedFacesJob && (
              <p className="mb-3 text-xs text-zinc-400">No previous scan found.</p>
            )}
            {failedFacesJob && (
              <p className="mb-3 text-sm text-red-600">
                Last scan failed: {failedFacesJob.error || 'unknown error'}
              </p>
            )}
            <button
              onClick={() => navigate({ name: 'people', libraryId: library.id })}
              className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-700 active:scale-[0.98]"
            >
              Find people
            </button>
          </div>
        )}
      </div>
    </section>
  )
}
