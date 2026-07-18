import { useEffect, useRef, useState } from 'react'
import {
  usePersons,
  useMergePersons,
  useBindingSuggestions,
  useBindings,
  useRefreshBindings,
  useMergeSuggestion,
  useDismissBindingSuggestion
} from '../../../api/hooks'
import { selectJobForLibrary, useJobsStore } from '../../../stores/jobs'
import { useZoomScale } from '../../../hooks/useZoomScale'
import { PersonCard } from './PersonCard'
import { GroupSuggestionStrip } from './GroupSuggestionStrip'
import { RespectedFolders } from './RespectedFolders'
import { MatchReviewModal } from './MatchReviewModal'
import { MaterializeReviewModal } from './MaterializeReviewModal'
import type { BindingSuggestion, ExecutionReport, Person } from '../../../api/client'

interface Props {
  libraryId: string
  onOpenPerson: (personId: number) => void
  onOrganize: () => void
}

function MergeResultBanner({ report, onDismiss }: { report: ExecutionReport; onDismiss: () => void }): React.JSX.Element {
  const ok = report.ok
  return (
    <div className={`mb-6 rounded-xl border px-5 py-4 ${ok ? 'border-emerald-200 bg-emerald-50' : 'border-red-200 bg-red-50'}`}>
      <div className="flex items-start justify-between">
        <p className={`text-sm font-medium ${ok ? 'text-emerald-800' : 'text-red-800'}`}>
          {ok
            ? `Merged — ${report.handled} of ${report.planned} files moved`
            : `Partial merge — ${report.handled}/${report.planned} succeeded, ${report.entries.filter((e) => e.error).length} errors`}
        </p>
        <button onClick={onDismiss} className="text-xs text-zinc-400 hover:text-zinc-600">
          Dismiss
        </button>
      </div>
      {!ok && (
        <ul className="mt-3 space-y-1">
          {report.entries.filter((e) => e.error).slice(0, 5).map((e, i) => (
            <li key={i} className="text-xs text-red-700">{e.source}: {e.error}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** People grid — the Faces tool's home sub-view. Folder-match suggestions
 * (Phase B/C) now surface directly here as enhanced tiles instead of a
 * separate Suggestions tab. Round-1 scope: Pending and Multi-person review
 * entry points are intentionally omitted (deferred). */
export function PeoplePanel({ libraryId, onOpenPerson, onOrganize }: Props): React.JSX.Element {
  const jobs = useJobsStore((s) => s.jobs)
  const activeJob = selectJobForLibrary(jobs, libraryId, 'faces')

  const { data: personsData, isError, isLoading } = usePersons(libraryId)
  const mergePersons = useMergePersons(libraryId)
  const hasFaceScan = !!personsData

  const { data: suggestionsData } = useBindingSuggestions(libraryId)
  const { data: bindingsData } = useBindings(libraryId)
  const refreshBindings = useRefreshBindings(libraryId)
  const mergeSuggestion = useMergeSuggestion(libraryId)
  const dismissSuggestion = useDismissBindingSuggestion(libraryId)

  const [mergingSuggestionId, setMergingSuggestionId] = useState<number | null>(null)
  const [mergeResult, setMergeResult] = useState<ExecutionReport | null>(null)
  const [reviewingSuggestion, setReviewingSuggestion] = useState<BindingSuggestion | null>(null)
  const [materializingPerson, setMaterializingPerson] = useState<Person | null>(null)

  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<number[]>([])
  const scrollRef = useRef<HTMLDivElement>(null)
  const [zoom] = useZoomScale(scrollRef, { min: 0.5, max: 2 })

  // Freshness is checked on tool-open only (no filesystem watcher) — refresh
  // detection once per folder, piggybacking on whatever faces scan already ran.
  const refreshedFor = useRef<string | null>(null)
  useEffect(() => {
    if (!hasFaceScan || refreshedFor.current === libraryId) return
    refreshedFor.current = libraryId
    refreshBindings.mutate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [libraryId, hasFaceScan])

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

  const suggestions = suggestionsData?.suggestions ?? []
  const personSuggestions = new Map<number, BindingSuggestion>()
  for (const s of suggestions) {
    if (s.kind === 'person' && s.person_ids.length === 1) personSuggestions.set(s.person_ids[0], s)
  }
  const groupSuggestions = suggestions.filter((s) => s.kind === 'group')

  const boundPersonIds = new Set<number>(
    (bindingsData?.bindings ?? []).flatMap((b) => b.person_ids)
  )

  const persons = personsData?.persons ?? []
  const sortedPersons = [...persons].sort((a, b) => {
    const sa = personSuggestions.get(a.id)
    const sb = personSuggestions.get(b.id)
    if (sa && sb) return sb.coverage - sa.coverage
    if (sa) return -1
    if (sb) return 1
    return 0
  })
  const isScanning = !!activeJob

  const handleMergeIntoFolder = (suggestion: BindingSuggestion) => {
    setMergingSuggestionId(suggestion.id)
    mergeSuggestion.mutate(
      { suggestionId: suggestion.id },
      {
        onSuccess: (data) => {
          setMergeResult(data)
          setMergingSuggestionId(null)
        },
        onError: () => setMergingSuggestionId(null)
      }
    )
  }

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

      {mergeResult && <MergeResultBanner report={mergeResult} onDismiss={() => setMergeResult(null)} />}

      {!isScanning && isLoading && <p className="text-sm text-zinc-400">Loading…</p>}

      {isScanning && persons.length === 0 && (
        <p className="text-sm text-zinc-400">Scanning — see progress in the bottom-right corner.</p>
      )}

      {!isLoading && !isScanning && persons.length === 0 && (
        <div className="rounded-2xl border border-dashed border-zinc-300 py-16 text-center">
          <p className="text-sm text-zinc-500">No people found yet.</p>
          <p className="mt-1 text-xs text-zinc-400">
            {isError ? 'Run a face scan to detect people in this folder.' : 'No faces were detected in this folder.'}
          </p>
        </div>
      )}

      {!isScanning && !isLoading && persons.length > 0 && (
        <GroupSuggestionStrip
          suggestions={groupSuggestions}
          busyId={mergingSuggestionId}
          onAccept={handleMergeIntoFolder}
          onReview={setReviewingSuggestion}
          onDismiss={(s) => dismissSuggestion.mutate(s.id)}
        />
      )}

      {persons.length > 0 && (
        <div
          className="grid gap-3"
          style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${Math.round(130 * zoom)}px, 1fr))` }}
        >
          {sortedPersons.map((p: Person) => (
            <PersonCard
              key={p.id}
              person={p}
              libraryId={libraryId}
              selected={selected.includes(p.id)}
              selectMode={selectMode}
              zoom={zoom}
              suggestion={personSuggestions.get(p.id)}
              isBound={boundPersonIds.has(p.id)}
              onToggleSelect={toggleSelect}
              onOpen={onOpenPerson}
              onMergeIntoFolder={handleMergeIntoFolder}
              onOpenDetails={setReviewingSuggestion}
              onDismissSuggestion={(s) => dismissSuggestion.mutate(s.id)}
              onMaterialize={setMaterializingPerson}
              mergeBusy={mergingSuggestionId === personSuggestions.get(p.id)?.id}
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

      {!isScanning && !isLoading && persons.length > 0 && <RespectedFolders libraryId={libraryId} />}

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

      {reviewingSuggestion && (
        <MatchReviewModal
          libraryId={libraryId}
          suggestion={reviewingSuggestion}
          onClose={() => setReviewingSuggestion(null)}
          onCommitted={() => {
            setReviewingSuggestion(null)
          }}
        />
      )}

      {materializingPerson && (
        <MaterializeReviewModal
          libraryId={libraryId}
          person={materializingPerson}
          onClose={() => setMaterializingPerson(null)}
          onCommitted={() => setMaterializingPerson(null)}
        />
      )}
    </div>
  )
}
