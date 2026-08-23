import { useRef, useState } from 'react'
import {
  useAcceptGlobalLinkSuggestion,
  useCreateGlobalPerson,
  useDeleteGlobalPerson,
  useDismissGlobalLinkSuggestion,
  useGlobalLinkSuggestions,
  useGlobalPeople,
  useRenameGlobalPerson,
  useSetGlobalPrimaryLocation,
  useUnlinkGlobalPerson
} from '../../../api/hooks'
import { FaceThumbnail } from '../../../components/FaceThumbnail'
import { personPath, useExplorerStore } from '../../../stores/explorer'
import type { GlobalLinkSuggestion, GlobalPerson, GlobalPersonMember } from '../../../api/client'

/** A person identity that can span multiple registered libraries (drives,
 * mounts) — every media location it's linked to is listed as a "member".
 * This is the aggregation view: `core/global_people.py`'s `list_aggregated`
 * opens every registered library's own per-library index and groups local
 * persons by their global link, so nothing here is a physical move — see
 * Phase 6/7 (Suggestions tab) for that. */

function GlobalPersonTile({
  person,
  selected,
  onOpen
}: {
  person: GlobalPerson
  selected: boolean
  onOpen: () => void
}): React.JSX.Element {
  const rename = useRenameGlobalPerson()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const thumbMember = person.members.find((m) => m.sample_face_ids.length > 0)

  const startEdit = (): void => {
    setDraft(person.name)
    setEditing(true)
    setTimeout(() => inputRef.current?.focus(), 0)
  }

  const commitEdit = (): void => {
    const trimmed = draft.trim()
    if (trimmed) rename.mutate({ id: person.id, name: trimmed })
    setEditing(false)
  }

  return (
    <div
      onClick={onOpen}
      className={`flex cursor-pointer flex-col items-center gap-2 rounded-xl border p-3 text-center transition-colors ${
        selected ? 'border-blue-400 bg-blue-50' : 'border-transparent hover:bg-zinc-50'
      }`}
    >
      <div className="relative h-20 w-20 overflow-hidden rounded-full bg-zinc-100">
        {thumbMember ? (
          <FaceThumbnail
            libraryId={thumbMember.library_id}
            faceId={thumbMember.sample_face_ids[0]}
            size={80}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-zinc-300">
            <svg className="h-1/2 w-1/2" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z" />
            </svg>
          </div>
        )}
      </div>

      {editing ? (
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onClick={(e) => e.stopPropagation()}
          onBlur={commitEdit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commitEdit()
            if (e.key === 'Escape') setEditing(false)
          }}
          className="w-full rounded border border-zinc-300 px-1 py-0.5 text-center text-sm"
        />
      ) : (
        <button
          onClick={(e) => {
            e.stopPropagation()
            startEdit()
          }}
          className="max-w-full truncate text-sm font-medium text-zinc-800 hover:underline"
          title="Rename"
        >
          {person.name}
        </button>
      )}

      <span className="text-xs text-zinc-500">
        {person.media_count} photo{person.media_count === 1 ? '' : 's'}/video
        {person.media_count === 1 ? '' : 's'}
      </span>
      <span className="text-[11px] text-zinc-400">
        {person.members.length} librar{person.members.length === 1 ? 'y' : 'ies'}
      </span>
    </div>
  )
}

function MemberRow({ person, member }: { person: GlobalPerson; member: GlobalPersonMember }): React.JSX.Element {
  const navigate = useExplorerStore((s) => s.navigate)
  const setToolMode = useExplorerStore((s) => s.setToolMode)
  const unlink = useUnlinkGlobalPerson()

  return (
    <div className="flex items-center justify-between gap-2 rounded-lg border border-zinc-200 px-3 py-2">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-zinc-800">{member.library_name}</p>
        <p className="text-xs text-zinc-500">
          {member.name ?? '(unnamed locally)'} · {member.media_count} item
          {member.media_count === 1 ? '' : 's'}
        </p>
      </div>
      <div className="flex shrink-0 gap-1.5">
        <button
          onClick={() => {
            setToolMode('none')
            navigate(personPath(member.library_path, member.local_person_id, member.name ?? person.name))
          }}
          className="rounded border border-zinc-200 bg-white px-2 py-1 text-xs text-zinc-600 hover:bg-zinc-50"
        >
          Open
        </button>
        <button
          onClick={() => unlink.mutate({ libraryId: member.library_id, localPersonId: member.local_person_id })}
          disabled={unlink.isPending}
          className="rounded border border-zinc-200 bg-white px-2 py-1 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50"
        >
          Unlink
        </button>
      </div>
    </div>
  )
}

function GlobalPersonDetail({ person }: { person: GlobalPerson }): React.JSX.Element {
  const setPrimaryLocation = useSetGlobalPrimaryLocation()
  const deletePerson = useDeleteGlobalPerson()

  const handlePickFolder = async (): Promise<void> => {
    const path = await window.mediamind.pickFolder()
    if (path) setPrimaryLocation.mutate({ id: person.id, path })
  }

  const handleClear = (): void => {
    setPrimaryLocation.mutate({ id: person.id, path: null })
  }

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div>
        <h3 className="text-sm font-semibold text-zinc-800">{person.name}</h3>
        <p className="text-xs text-zinc-500">
          {person.media_count} item{person.media_count === 1 ? '' : 's'} across {person.members.length} librar
          {person.members.length === 1 ? 'y' : 'ies'}
        </p>
      </div>

      <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
        <p className="mb-2 text-xs font-medium text-zinc-600">Primary physical location</p>
        {person.primary_location ? (
          <p className="mb-2 break-all text-xs text-zinc-800">{person.primary_location}</p>
        ) : (
          <p className="mb-2 text-xs text-zinc-400">
            Not set — future matches to {person.name} will just be tagged, never moved.
          </p>
        )}
        <div className="flex gap-2">
          <button
            onClick={handlePickFolder}
            disabled={setPrimaryLocation.isPending}
            className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-xs font-medium text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
          >
            {person.primary_location ? 'Change folder…' : 'Set primary location…'}
          </button>
          {person.primary_location && (
            <button
              onClick={handleClear}
              disabled={setPrimaryLocation.isPending}
              className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-xs text-zinc-500 hover:bg-zinc-50 disabled:opacity-50"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      <div>
        <p className="mb-2 text-xs font-medium text-zinc-600">Linked libraries</p>
        <div className="flex flex-col gap-1.5">
          {person.members.map((m) => (
            <MemberRow key={`${m.library_id}:${m.local_person_id}`} person={person} member={m} />
          ))}
        </div>
      </div>

      <button
        onClick={() => {
          if (confirm(`Remove the "${person.name}" global identity? Local persons stay named — only the cross-library link is removed.`)) {
            deletePerson.mutate(person.id)
          }
        }}
        className="mt-auto self-start text-xs text-red-600 hover:underline"
      >
        Remove this global identity
      </button>
    </div>
  )
}

/** Finds a member tile's display info (name, thumbnail) for a suggestion's
 * side from the already-loaded aggregation — every named local person is
 * guaranteed a member entry somewhere (see `sync_named_persons`), so no
 * extra fetch is needed just to render the suggestion strip. */
function findMember(
  people: GlobalPerson[] | undefined,
  libraryId: string,
  localPersonId: number
): GlobalPersonMember | undefined {
  for (const p of people ?? []) {
    const m = p.members.find((m) => m.library_id === libraryId && m.local_person_id === localPersonId)
    if (m) return m
  }
  return undefined
}

function LinkSuggestionsStrip({ people }: { people: GlobalPerson[] | undefined }): React.JSX.Element | null {
  const { data: suggestions } = useGlobalLinkSuggestions()
  const accept = useAcceptGlobalLinkSuggestion()
  const dismiss = useDismissGlobalLinkSuggestion()

  if (!suggestions || suggestions.length === 0) return null

  return (
    <div className="border-b border-zinc-200 bg-amber-50 px-4 py-3">
      <p className="mb-2 text-xs font-medium text-zinc-600">
        Same person, different library? Never linked automatically — you decide.
      </p>
      <div className="flex flex-wrap gap-2">
        {suggestions.map((s: GlobalLinkSuggestion) => {
          const a = findMember(people, s.library_id_a, s.local_person_id_a)
          const b = findMember(people, s.library_id_b, s.local_person_id_b)
          const key = `${s.library_id_a}:${s.local_person_id_a}|${s.library_id_b}:${s.local_person_id_b}`
          return (
            <div
              key={key}
              className="flex items-center gap-2 rounded-xl border border-amber-200 bg-white px-3 py-2 shadow-sm"
            >
              <div className="flex -space-x-2">
                {a?.sample_face_ids[0] != null && (
                  <FaceThumbnail libraryId={a.library_id} faceId={a.sample_face_ids[0]} size={36} className="ring-2 ring-white" />
                )}
                {b?.sample_face_ids[0] != null && (
                  <FaceThumbnail libraryId={b.library_id} faceId={b.sample_face_ids[0]} size={36} className="ring-2 ring-white" />
                )}
              </div>
              <div className="text-xs">
                <p className="font-medium text-zinc-800">
                  {a?.name ?? '?'} ({a?.library_name}) ↔ {b?.name ?? '?'} ({b?.library_name})
                </p>
                <p className="text-zinc-500">{Math.round(s.similarity * 100)}% alike</p>
              </div>
              <button
                onClick={() => accept.mutate(s)}
                disabled={accept.isPending}
                className="rounded-lg bg-zinc-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
              >
                Link
              </button>
              <button
                onClick={() => dismiss.mutate(s)}
                disabled={dismiss.isPending}
                className="rounded-lg border border-zinc-200 bg-white px-2 py-1 text-xs text-zinc-500 hover:bg-zinc-50 disabled:opacity-50"
              >
                Not the same
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function GlobalPeoplePanel(): React.JSX.Element {
  const { data: people, isPending, isError } = useGlobalPeople()
  const createPerson = useCreateGlobalPerson()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [newName, setNewName] = useState('')

  const selected = people?.find((p) => p.id === selectedId) ?? null

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-zinc-800">People (All Libraries)</h2>
          <p className="text-xs text-zinc-500">
            Named people from every registered library, aggregated by explicit link.
          </p>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            const trimmed = newName.trim()
            if (trimmed) {
              createPerson.mutate(trimmed)
              setNewName('')
            }
          }}
          className="flex gap-1.5"
        >
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="New person…"
            className="rounded-lg border border-zinc-200 px-2 py-1 text-xs"
          />
          <button
            type="submit"
            disabled={!newName.trim() || createPerson.isPending}
            className="rounded-lg bg-zinc-900 px-3 py-1 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
          >
            Add
          </button>
        </form>
      </div>

      <LinkSuggestionsStrip people={people} />

      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-y-auto p-4">
          {isPending ? (
            <p className="text-sm text-zinc-400">Loading people from every library…</p>
          ) : isError ? (
            <p className="text-sm text-red-600">Could not load global people.</p>
          ) : !people || people.length === 0 ? (
            <p className="text-sm text-zinc-400">
              No named people yet. Name a face cluster in any library's People tab, or add one here.
            </p>
          ) : (
            <div
              className="grid gap-3"
              style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))' }}
            >
              {people.map((p) => (
                <GlobalPersonTile
                  key={p.id}
                  person={p}
                  selected={p.id === selectedId}
                  onOpen={() => setSelectedId(p.id)}
                />
              ))}
            </div>
          )}
        </div>

        {selected && (
          <div className="w-80 shrink-0 border-l border-zinc-200">
            <GlobalPersonDetail person={selected} />
          </div>
        )}
      </div>
    </div>
  )
}
