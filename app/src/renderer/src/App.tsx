import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useHealth, useLibraries, useAddLibrary, useRemoveLibrary } from './api/hooks'
import { useProgressSocket } from './api/progress'
import { useAppStore } from './stores/app'
import { useJobsStore } from './stores/jobs'
import { LibraryDetail } from './screens/LibraryDetail'
import { DedupeReview } from './screens/DedupeReview'
import { ProvidersScreen } from './screens/ProvidersScreen'
import { PeopleScreen } from './screens/PeopleScreen'
import { OrganizeScreen } from './screens/OrganizeScreen'
import { PendingReview } from './screens/PendingReview'
import type { Library } from './api/client'

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
// Engine status indicator
// ---------------------------------------------------------------------------

function EngineStatus(): React.JSX.Element {
  const { data, isError, isPending } = useHealth()
  const state = isPending ? 'starting' : isError ? 'offline' : 'ready'
  const dot =
    state === 'ready' ? 'bg-emerald-500' : state === 'starting' ? 'bg-amber-400' : 'bg-red-500'
  return (
    <span className="flex items-center gap-2 text-xs text-zinc-500">
      <span className={`h-2 w-2 rounded-full ${dot}`} />
      {state === 'ready' ? `Engine v${data!.version}` : `Engine ${state}…`}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Libraries list
// ---------------------------------------------------------------------------

function Libraries(): React.JSX.Element {
  const { data: libraries, isPending } = useLibraries()
  const addLibrary = useAddLibrary()
  const removeLibrary = useRemoveLibrary()
  const navigate = useAppStore((s) => s.navigate)

  const onAddFolder = async (): Promise<void> => {
    const folder = await window.mediamind.pickFolder()
    if (folder) addLibrary.mutate(folder)
  }

  return (
    <section className="mx-auto w-full max-w-3xl px-8 py-12">
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Your folders</h2>
          <p className="mt-1 text-sm text-zinc-500">
            MediaMind works directly on folders you choose. Nothing is imported or copied.
          </p>
        </div>
        <button
          onClick={onAddFolder}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-700 active:scale-[0.98]"
        >
          Add folder
        </button>
      </div>

      {addLibrary.isError && (
        <p className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {addLibrary.error.message}
        </p>
      )}

      {isPending ? (
        <p className="text-sm text-zinc-400">Loading…</p>
      ) : !libraries || libraries.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-300 py-16 text-center">
          <p className="text-sm text-zinc-500">No folders yet.</p>
          <p className="mt-1 text-xs text-zinc-400">
            Add a folder to start finding duplicates and people in your media.
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {libraries.map((lib: Library) => (
            <li
              key={lib.id}
              onClick={() => navigate({ name: 'library', libraryId: lib.id })}
              className="group flex cursor-pointer items-center justify-between rounded-xl border border-zinc-200 bg-white px-5 py-4 shadow-sm transition hover:border-zinc-300 hover:shadow-md"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{lib.name}</p>
                <p className="truncate text-xs text-zinc-400">{lib.path}</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={(e) => { e.stopPropagation(); removeLibrary.mutate(lib.id) }}
                  title="Remove from MediaMind (files are not touched)"
                  className="invisible rounded-md px-2 py-1 text-xs text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-600 group-hover:visible"
                >
                  Remove
                </button>
                <span className="text-zinc-300">›</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Root app
// ---------------------------------------------------------------------------

export default function App(): React.JSX.Element {
  // Mount the WS progress socket once for the app's lifetime.
  useProgressSocket()

  const view = useAppStore((s) => s.view)
  const { data: libraries } = useLibraries()

  const currentLibraryId =
    view.name !== 'libraries' ? (view as { libraryId?: string }).libraryId : undefined

  const currentLibrary = currentLibraryId
    ? libraries?.find((l: Library) => l.id === currentLibraryId)
    : undefined

  return (
    <div className="flex min-h-screen flex-col">
      <JobInvalidator />
      <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-8 py-4">
        <h1
          className="cursor-pointer text-base font-semibold tracking-tight"
          onClick={() => useAppStore.getState().navigate({ name: 'libraries' })}
        >
          MediaMind
        </h1>
        <EngineStatus />
      </header>
      <main className="flex-1">
        {view.name === 'libraries' && <Libraries />}
        {view.name === 'library' && currentLibrary && (
          <LibraryDetail library={currentLibrary} />
        )}
        {view.name === 'dedupe-review' && (
          <DedupeReview libraryId={(view as { libraryId: string }).libraryId} />
        )}
        {view.name === 'providers' && (
          <ProvidersScreen libraryId={(view as { libraryId: string }).libraryId} />
        )}
        {view.name === 'people' && (
          <PeopleScreen libraryId={(view as { libraryId: string }).libraryId} />
        )}
        {view.name === 'organize' && (
          <OrganizeScreen libraryId={(view as { libraryId: string }).libraryId} />
        )}
        {view.name === 'pending-review' && (
          <PendingReview libraryId={(view as { libraryId: string }).libraryId} />
        )}
      </main>
    </div>
  )
}
