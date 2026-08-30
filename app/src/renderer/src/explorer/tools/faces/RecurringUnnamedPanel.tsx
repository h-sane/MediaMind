import { useRef, useState } from 'react'
import { ArrowLeft } from 'lucide-react'
import { useRecurringUnnamed, useRenamePerson } from '../../../api/hooks'
import { FaceThumbnail } from '../../../components/FaceThumbnail'
import type { Person } from '../../../api/client'

interface Props {
  libraryId: string
  onBack: () => void
  onOpenPerson: (personId: number) => void
}

/** ADR-0001 recurring-unnamed browse surface: the unnamed clusters that keep
 * showing up (above the recurrence floor), ranked by how many media they
 * appear in, so the user can name the recurring strangers without hunting for
 * them in the full People grid. A "show all" hatch drops the floor to 1. */
function ClusterTile({
  person,
  libraryId,
  onOpen,
  onNamed
}: {
  person: Person
  libraryId: string
  onOpen: (id: number) => void
  onNamed: (id: number) => void
}): React.JSX.Element {
  const rename = useRenamePerson(libraryId)
  const [draft, setDraft] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const commit = () => {
    const trimmed = draft.trim()
    if (!trimmed) return
    rename.mutate({ personId: person.id, name: trimmed })
    onNamed(person.id)
  }

  return (
    <div className="flex flex-col rounded-2xl border border-zinc-200 bg-white p-4">
      <button
        onClick={() => onOpen(person.id)}
        className="mb-3 flex justify-center"
        title="Open this person's photos"
      >
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
      </button>
      <p className="mb-2 text-center text-xs text-zinc-400">
        Seen in {person.media_count} {person.media_count === 1 ? 'photo/video' : 'photos/videos'}
      </p>
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit()
          if (e.key === 'Escape') setDraft('')
        }}
        placeholder="Name this person…"
        className="w-full rounded-lg border border-zinc-300 px-2 py-1 text-center text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900"
      />
    </div>
  )
}

export function RecurringUnnamedPanel({ libraryId, onBack, onOpenPerson }: Props): React.JSX.Element {
  // `showAll` drops the recurrence floor to 1 (the endpoint's escape hatch),
  // surfacing one-off strangers too — off by default so only the people who
  // actually recur are shown first.
  const [showAll, setShowAll] = useState(false)
  const { data, isLoading, isError } = useRecurringUnnamed(libraryId, showAll ? 1 : undefined)
  // Named-this-session ids drop out immediately; a reopen refetches anyway.
  const [named, setNamed] = useState<Set<number>>(new Set())

  const persons = (data?.persons ?? []).filter((p) => !named.has(p.id))
  const belowFloor = data ? data.total_unnamed - data.persons.length : 0

  return (
    <div className="h-full overflow-y-auto p-6 pb-24">
      <div className="mb-6 flex items-center gap-3">
        <button
          onClick={onBack}
          className="flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-zinc-500 hover:bg-zinc-100"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </button>
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Recurring faces to name</h2>
          <p className="mt-0.5 text-sm text-zinc-500">
            Unnamed people who keep showing up across your media.
          </p>
        </div>
      </div>

      {isLoading && <p className="text-sm text-zinc-400">Loading…</p>}
      {isError && (
        <p className="text-sm text-zinc-400">Run a face scan first to find recurring faces.</p>
      )}

      {!isLoading && !isError && persons.length === 0 && (
        <div className="rounded-2xl border border-dashed border-zinc-300 py-16 text-center">
          <p className="text-sm text-zinc-500">
            {showAll ? 'No unnamed people left — everyone is named.' : 'No recurring unnamed people.'}
          </p>
          {!showAll && belowFloor > 0 && (
            <p className="mt-1 text-xs text-zinc-400">
              {belowFloor} one-off {belowFloor === 1 ? 'face' : 'faces'} below the recurrence threshold.
            </p>
          )}
        </div>
      )}

      {persons.length > 0 && (
        <div
          className="grid gap-3"
          style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))' }}
        >
          {persons.map((p) => (
            <ClusterTile
              key={p.id}
              person={p}
              libraryId={libraryId}
              onOpen={onOpenPerson}
              onNamed={(id) => setNamed((prev) => new Set(prev).add(id))}
            />
          ))}
        </div>
      )}

      {!showAll && belowFloor > 0 && persons.length > 0 && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-6 rounded-lg border border-zinc-200 px-3 py-2 text-sm text-zinc-600 transition hover:bg-zinc-50"
        >
          Show all unnamed ({belowFloor} more)
        </button>
      )}
    </div>
  )
}
