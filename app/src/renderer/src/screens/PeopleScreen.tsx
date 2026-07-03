import { useState, useRef } from 'react'
import { useAppStore } from '../stores/app'
import { useJobsStore, selectJobForLibrary } from '../stores/jobs'
import { usePersons, useStartFaceScan, useCancelScan, useRenamePerson, useMergePersons } from '../api/hooks'
import { ScanProgress } from '../components/ScanProgress'
import { FaceThumbnail } from '../components/FaceThumbnail'
import type { Person } from '../api/client'

interface Props {
  libraryId: string
}

function PersonCard({
  person,
  libraryId,
  selected,
  selectMode,
  onToggleSelect,
}: {
  person: Person
  libraryId: string
  selected: boolean
  selectMode: boolean
  onToggleSelect: (id: number) => void
}): React.JSX.Element {
  const rename = useRenamePerson(libraryId)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const displayName = person.name ?? person.auto_label
  const isNamed = person.name !== null

  const startEdit = () => {
    setDraft(person.name ?? '')
    setEditing(true)
    setTimeout(() => inputRef.current?.focus(), 0)
  }

  const commitEdit = () => {
    const trimmed = draft.trim()
    rename.mutate({ personId: person.id, name: trimmed || null })
    setEditing(false)
  }

  const handleClick = () => {
    if (selectMode) {
      onToggleSelect(person.id)
    }
  }

  return (
    <div
      onClick={handleClick}
      className={`group relative cursor-pointer rounded-2xl border p-4 transition ${
        selectMode
          ? selected
            ? 'border-zinc-900 bg-zinc-50 shadow-md'
            : 'border-zinc-200 bg-white hover:border-zinc-300'
          : 'border-zinc-200 bg-white hover:border-zinc-300 hover:shadow-sm'
      }`}
    >
      {selectMode && (
        <div
          className={`absolute right-3 top-3 h-5 w-5 rounded-full border-2 transition ${
            selected ? 'border-zinc-900 bg-zinc-900' : 'border-zinc-300 bg-white'
          }`}
        />
      )}

      {/* Face thumbnail collage */}
      <div className="mb-3 flex justify-center">
        {person.sample_face_ids.length > 0 ? (
          <FaceThumbnail
            libraryId={libraryId}
            faceId={person.sample_face_ids[0]}
            size={72}
            className="ring-2 ring-white ring-offset-1"
          />
        ) : (
          <div className="flex h-[72px] w-[72px] items-center justify-center rounded-full bg-zinc-100">
            <svg className="h-8 w-8 text-zinc-300" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z" />
            </svg>
          </div>
        )}
      </div>

      {/* Name */}
      <div className="text-center">
        {editing ? (
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commitEdit}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitEdit()
              if (e.key === 'Escape') setEditing(false)
            }}
            placeholder={person.auto_label}
            className="w-full rounded-lg border border-zinc-300 px-2 py-1 text-center text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900"
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <button
            onClick={(e) => {
              e.stopPropagation()
              if (!selectMode) startEdit()
            }}
            className="w-full text-center"
            title="Click to rename"
          >
            <p className={`truncate text-sm font-medium ${isNamed ? '' : 'text-zinc-400'}`}>
              {displayName}
            </p>
          </button>
        )}
        <p className="mt-0.5 text-xs text-zinc-400">{person.media_count} photos/videos</p>
      </div>
    </div>
  )
}

export function PeopleScreen({ libraryId }: Props): React.JSX.Element {
  const back = useAppStore((s) => s.back)
  const navigate = useAppStore((s) => s.navigate)
  const jobs = useJobsStore((s) => s.jobs)
  const activeJob = selectJobForLibrary(jobs, libraryId, 'faces')

  const { data: personsData, isError, isLoading } = usePersons(libraryId)
  const startFaceScan = useStartFaceScan(libraryId)
  const cancelScan = useCancelScan(
    libraryId,
    activeJob?.id ?? ''
  )
  const mergePersons = useMergePersons(libraryId)

  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<number[]>([])

  const toggleSelect = (id: number) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 2 ? [...prev, id] : prev
    )
  }

  const handleMerge = () => {
    if (selected.length !== 2) return
    const [source, target] = selected
    mergePersons.mutate(
      { sourceId: source, targetId: target },
      {
        onSuccess: () => {
          setSelectMode(false)
          setSelected([])
        }
      }
    )
  }

  const persons = personsData?.persons ?? []
  const isScanning = !!activeJob

  return (
    <section className="mx-auto w-full max-w-5xl px-8 py-12">
      <div className="mb-2 flex items-center gap-2">
        <button
          onClick={back}
          className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600"
        >
          ← Back
        </button>
      </div>

      <div className="mb-6 flex items-end justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">People</h2>
          {personsData && (
            <p className="mt-1 text-sm text-zinc-500">
              {persons.length} {persons.length === 1 ? 'person' : 'people'}
              {personsData.unassigned_faces > 0 && ` · ${personsData.unassigned_faces} unassigned faces`}
            </p>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          {personsData && personsData.multi_person_count > 0 && !isScanning && (
            <button
              onClick={() => navigate({ name: 'multi-person-review', libraryId })}
              className="rounded-lg border border-violet-300 bg-violet-50 px-3 py-2 text-sm text-violet-800 transition hover:bg-violet-100"
            >
              {personsData.multi_person_count} multi-person
            </button>
          )}
          {personsData && personsData.pending_count > 0 && !isScanning && (
            <button
              onClick={() => navigate({ name: 'pending-review', libraryId })}
              className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 transition hover:bg-amber-100"
            >
              {personsData.pending_count} pending
            </button>
          )}
          {persons.length > 0 && !isScanning && (
            <button
              onClick={() => navigate({ name: 'organize', libraryId })}
              className="rounded-lg border border-zinc-200 px-3 py-2 text-sm text-zinc-600 transition hover:bg-zinc-50"
            >
              Organize
            </button>
          )}
          {persons.length >= 2 && !isScanning && (
            <button
              onClick={() => {
                setSelectMode((m) => !m)
                setSelected([])
              }}
              className={`rounded-lg border px-3 py-2 text-sm transition ${
                selectMode
                  ? 'border-zinc-900 bg-zinc-900 text-white'
                  : 'border-zinc-200 text-zinc-600 hover:bg-zinc-50'
              }`}
            >
              {selectMode ? 'Cancel' : 'Merge'}
            </button>
          )}
          {!isScanning && (
            <button
              onClick={() => startFaceScan.mutate(undefined)}
              disabled={startFaceScan.isPending}
              className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-700 disabled:opacity-50"
            >
              {persons.length > 0 ? 'Rescan faces' : 'Scan for faces'}
            </button>
          )}
        </div>
      </div>

      {/* Scan progress */}
      {isScanning && activeJob && (
        <div className="mb-6 rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
          <ScanProgress libraryId={libraryId} job={activeJob} />
        </div>
      )}

      {startFaceScan.isError && (
        <p className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {startFaceScan.error.message}
        </p>
      )}

      {/* Person grid */}
      {isLoading && <p className="text-sm text-zinc-400">Loading…</p>}

      {!isLoading && persons.length === 0 && !isScanning && (
        <div className="rounded-2xl border border-dashed border-zinc-300 py-16 text-center">
          <p className="text-sm text-zinc-500">No people found yet.</p>
          <p className="mt-1 text-xs text-zinc-400">Run a face scan to detect people in your media.</p>
        </div>
      )}

      {persons.length > 0 && (
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6">
          {persons.map((p: Person) => (
            <PersonCard
              key={p.id}
              person={p}
              libraryId={libraryId}
              selected={selected.includes(p.id)}
              selectMode={selectMode}
              onToggleSelect={toggleSelect}
            />
          ))}
        </div>
      )}

      {/* Stats footer */}
      {personsData && !isLoading && (
        <div className="mt-6 flex gap-4 text-xs text-zinc-400">
          {personsData.no_face_files > 0 && (
            <span>{personsData.no_face_files} files with no faces</span>
          )}
          {personsData.unreadable_files > 0 && (
            <span>{personsData.unreadable_files} unreadable files (routed to _unsorted on organize)</span>
          )}
        </div>
      )}

      {/* Merge floating bar */}
      {selectMode && (
        <div className="fixed bottom-6 left-1/2 z-20 -translate-x-1/2">
          <div className="flex items-center gap-3 rounded-2xl border border-zinc-200 bg-white px-5 py-3 shadow-xl">
            <span className="text-sm text-zinc-600">
              {selected.length === 0
                ? 'Select 2 people to merge'
                : selected.length === 1
                ? 'Select 1 more person'
                : 'Merge these 2 people?'}
            </span>
            {selected.length === 2 && (
              <button
                onClick={handleMerge}
                disabled={mergePersons.isPending}
                className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-700 disabled:opacity-50"
              >
                {mergePersons.isPending ? 'Merging…' : 'Merge'}
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
