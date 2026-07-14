import { useRef, useState } from 'react'
import { usePersons, useRenamePerson, useMergePersons } from '../../../api/hooks'
import { selectJobForLibrary, useJobsStore } from '../../../stores/jobs'
import { useZoomScale } from '../../../hooks/useZoomScale'
import { ScanProgress } from '../../../components/ScanProgress'
import { FaceThumbnail } from '../../../components/FaceThumbnail'
import type { Person } from '../../../api/client'

function PersonCard({
  person,
  libraryId,
  selected,
  selectMode,
  zoom,
  onToggleSelect,
  onOpen
}: {
  person: Person
  libraryId: string
  selected: boolean
  selectMode: boolean
  zoom: number
  onToggleSelect: (id: number) => void
  onOpen: (id: number) => void
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
    if (selectMode) onToggleSelect(person.id)
    else onOpen(person.id)
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

      <div className="mb-3 flex justify-center">
        {person.sample_face_ids.length > 0 ? (
          <FaceThumbnail
            libraryId={libraryId}
            faceId={person.sample_face_ids[0]}
            size={Math.round(72 * zoom)}
            className="ring-2 ring-white ring-offset-1"
          />
        ) : (
          <div
            className="flex items-center justify-center rounded-full bg-zinc-100"
            style={{ width: 72 * zoom, height: 72 * zoom }}
          >
            <svg className="h-8 w-8 text-zinc-300" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z" />
            </svg>
          </div>
        )}
      </div>

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
            <p className={`truncate text-sm font-medium ${isNamed ? '' : 'text-zinc-400'}`}>{displayName}</p>
          </button>
        )}
        <p className="mt-0.5 text-xs text-zinc-400">{person.media_count} photos/videos</p>
      </div>
    </div>
  )
}

interface Props {
  libraryId: string
  onOpenPerson: (personId: number) => void
  onOrganize: () => void
}

/** People grid — the Faces tool's home sub-view. Round-1 scope: Pending and
 * Multi-person review entry points are intentionally omitted (deferred). */
export function PeoplePanel({ libraryId, onOpenPerson, onOrganize }: Props): React.JSX.Element {
  const jobs = useJobsStore((s) => s.jobs)
  const activeJob = selectJobForLibrary(jobs, libraryId, 'faces')

  const { data: personsData, isError, isLoading } = usePersons(libraryId)
  const mergePersons = useMergePersons(libraryId)

  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<number[]>([])
  const scrollRef = useRef<HTMLDivElement>(null)
  const [zoom] = useZoomScale(scrollRef, { min: 0.5, max: 2 })

  const toggleSelect = (id: number) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 2 ? [...prev, id] : prev))
  }

  const handleMerge = () => {
    if (selected.length !== 2) return
    const [source, target] = selected
    mergePersons.mutate(
      { sourceId: source, targetId: target },
      { onSuccess: () => { setSelectMode(false); setSelected([]) } }
    )
  }

  const persons = personsData?.persons ?? []
  const isScanning = !!activeJob

  return (
    <div ref={scrollRef} className="h-full overflow-y-auto p-6 pb-24">
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            People
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-700">
              Beta
            </span>
          </h2>
          {personsData && (
            <p className="mt-1 text-sm text-zinc-500">
              {persons.length} {persons.length === 1 ? 'person' : 'people'}
              {personsData.unassigned_faces > 0 && ` · ${personsData.unassigned_faces} unassigned faces`}
            </p>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          {persons.length > 0 && !isScanning && (
            <button
              onClick={onOrganize}
              className="rounded-lg border border-zinc-200 px-3 py-2 text-sm text-zinc-600 transition hover:bg-zinc-50"
            >
              Organize
            </button>
          )}
          {persons.length >= 2 && !isScanning && (
            <button
              onClick={() => { setSelectMode((m) => !m); setSelected([]) }}
              className={`rounded-lg border px-3 py-2 text-sm transition ${
                selectMode ? 'border-zinc-900 bg-zinc-900 text-white' : 'border-zinc-200 text-zinc-600 hover:bg-zinc-50'
              }`}
            >
              {selectMode ? 'Cancel' : 'Merge'}
            </button>
          )}
        </div>
      </div>

      {isScanning && activeJob && (
        <div className="mb-6">
          <ScanProgress libraryId={libraryId} job={activeJob} />
        </div>
      )}

      {!isScanning && isLoading && <p className="text-sm text-zinc-400">Loading…</p>}

      {!isLoading && !isScanning && persons.length === 0 && (
        <div className="rounded-2xl border border-dashed border-zinc-300 py-16 text-center">
          <p className="text-sm text-zinc-500">No people found yet.</p>
          <p className="mt-1 text-xs text-zinc-400">
            {isError ? 'Run a face scan to detect people in this folder.' : 'No faces were detected in this folder.'}
          </p>
        </div>
      )}

      {persons.length > 0 && (
        <div
          className="grid gap-3"
          style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${Math.round(130 * zoom)}px, 1fr))` }}
        >
          {persons.map((p: Person) => (
            <PersonCard
              key={p.id}
              person={p}
              libraryId={libraryId}
              selected={selected.includes(p.id)}
              selectMode={selectMode}
              zoom={zoom}
              onToggleSelect={toggleSelect}
              onOpen={onOpenPerson}
            />
          ))}
        </div>
      )}

      {personsData && !isLoading && personsData.unreadable_files > 0 && (
        <div className="mt-4 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
          <svg className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>
          <div>
            <p className="text-sm font-medium text-amber-800">
              {personsData.unreadable_files} unreadable {personsData.unreadable_files === 1 ? 'file' : 'files'}
            </p>
            <p className="mt-0.5 text-xs text-amber-700">
              These files could not be decoded (corrupt, unsupported format, or permission error). On organize
              they will be routed to <code className="rounded bg-amber-100 px-1">People/_unsorted/</code> and left
              untouched until reviewed.
            </p>
          </div>
        </div>
      )}

      {personsData && !isLoading && personsData.no_face_files > 0 && (
        <div className="mt-3 text-xs text-zinc-400">
          {personsData.no_face_files} files scanned with no faces detected (stay in place on organize)
        </div>
      )}

      {selectMode && (
        <div className="fixed bottom-6 left-1/2 z-20 -translate-x-28">
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
                className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
              >
                {mergePersons.isPending ? 'Merging…' : 'Merge'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
