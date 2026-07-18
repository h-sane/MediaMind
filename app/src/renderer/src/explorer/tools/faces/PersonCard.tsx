import { useRef, useState } from 'react'
import { useRenamePerson } from '../../../api/hooks'
import { FaceThumbnail } from '../../../components/FaceThumbnail'
import type { BindingSuggestion, Person } from '../../../api/client'

interface Props {
  person: Person
  libraryId: string
  selected: boolean
  selectMode: boolean
  zoom: number
  suggestion?: BindingSuggestion
  isBound?: boolean
  onToggleSelect: (id: number) => void
  onOpen: (id: number) => void
  onMergeIntoFolder?: (suggestion: BindingSuggestion) => void
  onLockFolder?: (suggestion: BindingSuggestion) => void
  onOpenDetails?: (suggestion: BindingSuggestion) => void
  onDismissSuggestion?: (suggestion: BindingSuggestion) => void
  onMaterialize?: (person: Person) => void
  mergeBusy?: boolean
}

/** A single person tile. When `suggestion` is present (a pending, pending
 * folder-match for this exact person), the tile also surfaces the match —
 * this is the primary way folder-organization suggestions now show up,
 * instead of a separate Suggestions tab. */
export function PersonCard({
  person,
  libraryId,
  selected,
  selectMode,
  zoom,
  suggestion,
  isBound,
  onToggleSelect,
  onOpen,
  onMergeIntoFolder,
  onLockFolder,
  onOpenDetails,
  onDismissSuggestion,
  onMaterialize,
  mergeBusy
}: Props): React.JSX.Element {
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
          : suggestion
            ? 'border-emerald-200 bg-emerald-50/40 hover:border-emerald-300 hover:shadow-sm'
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

      {suggestion && !selectMode && (
        <div className="mt-3 border-t border-emerald-100 pt-3" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center justify-between gap-1">
            <p className="truncate text-xs font-medium text-emerald-700" title={suggestion.folder_rel}>
              {Math.round(suggestion.coverage * 100)}% match &rarr; {suggestion.folder_rel}
            </p>
            {onDismissSuggestion && (
              <button
                onClick={() => onDismissSuggestion(suggestion)}
                title="Not a match — dismiss this suggestion"
                className="shrink-0 rounded p-0.5 text-emerald-400 hover:bg-emerald-100 hover:text-emerald-600"
              >
                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
          {suggestion.outlier_file_ids.length === 0 && suggestion.move_count === 0 ? (
            // Every file already matches and this person has no stray
            // photos elsewhere — nothing to review or move. The only real
            // action left is locking this folder in as theirs, so a later
            // Organize run respects it instead of recreating it under
            // People/<name>.
            <div className="mt-2">
              <button
                onClick={() => onLockFolder?.(suggestion)}
                disabled={mergeBusy}
                className="w-full rounded-lg bg-emerald-600 px-2 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-500 disabled:opacity-50"
              >
                {mergeBusy ? 'Locking…' : 'Lock this folder'}
              </button>
            </div>
          ) : (
            <div className="mt-2 flex gap-1.5">
              <button
                onClick={() => onMergeIntoFolder?.(suggestion)}
                disabled={mergeBusy}
                className="flex-1 rounded-lg bg-emerald-600 px-2 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-500 disabled:opacity-50"
              >
                {mergeBusy ? 'Merging…' : 'Merge into folder'}
              </button>
              <button
                onClick={() => onOpenDetails?.(suggestion)}
                className="rounded-lg border border-emerald-200 px-2 py-1.5 text-xs text-emerald-700 transition hover:bg-emerald-100"
              >
                Open details
              </button>
            </div>
          )}
        </div>
      )}

      {!suggestion && !isBound && !selectMode && onMaterialize && (
        <div className="mt-3 border-t border-zinc-100 pt-3" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => onMaterialize(person)}
            className="w-full rounded-lg border border-zinc-200 px-2 py-1.5 text-xs text-zinc-500 transition hover:border-zinc-300 hover:bg-zinc-50 hover:text-zinc-700"
          >
            Review &amp; create folder
          </button>
        </div>
      )}
    </div>
  )
}
