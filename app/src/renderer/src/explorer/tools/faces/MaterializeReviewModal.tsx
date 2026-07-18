import { useState } from 'react'
import { useMaterializePerson, useMaterializePreview } from '../../../api/hooks'
import { MediaViewer } from '../../../components/MediaViewer'
import { FullscreenModalShell } from '../shared/FullscreenModalShell'
import { MatchReviewCard } from './MatchReviewCard'
import type { Person } from '../../../api/client'

interface Props {
  libraryId: string
  person: Person
  onClose: () => void
  onCommitted: () => void
}

/**
 * Full-screen review for a not-yet-foldered person: no folder exists for
 * them yet, so nothing moves until the user names them and confirms. Every
 * one of their current photos, library-wide, can be excluded (stays where
 * it is — not this person) or redirected to a different folder entirely;
 * whatever's left materializes into a brand-new sibling folder at the
 * library root, exactly like the folders they already have.
 */
export function MaterializeReviewModal({ libraryId, person, onClose, onCommitted }: Props): React.JSX.Element {
  const { data: preview, isLoading, isError } = useMaterializePreview(libraryId, person.id)
  const materialize = useMaterializePerson(libraryId)

  const [name, setName] = useState(person.name ?? '')
  const [excluded, setExcluded] = useState<Set<number>>(new Set())
  const [reassignments, setReassignments] = useState<Map<number, string>>(new Map())
  const [reassignDraftFor, setReassignDraftFor] = useState<number | null>(null)
  const [reassignDraftValue, setReassignDraftValue] = useState('')
  const [singleViewIndex, setSingleViewIndex] = useState<number | null>(null)

  const candidates = preview?.candidates ?? []
  const viewerFiles = candidates.map((c) => ({ path: c.path, kind: c.kind }))

  function toggleExclude(fileId: number): void {
    setExcluded((prev) => {
      const next = new Set(prev)
      if (next.has(fileId)) next.delete(fileId)
      else next.add(fileId)
      return next
    })
    setReassignments((prev) => {
      if (!prev.has(fileId)) return prev
      const next = new Map(prev)
      next.delete(fileId)
      return next
    })
  }

  function openReassignDraft(fileId: number): void {
    setReassignDraftFor(fileId)
    setReassignDraftValue(reassignments.get(fileId) ?? '')
  }

  function saveReassignDraft(): void {
    if (reassignDraftFor === null) return
    const dest = reassignDraftValue.trim()
    if (!dest) return
    setReassignments((prev) => new Map(prev).set(reassignDraftFor, dest))
    setExcluded((prev) => {
      if (!prev.has(reassignDraftFor)) return prev
      const next = new Set(prev)
      next.delete(reassignDraftFor)
      return next
    })
    setReassignDraftFor(null)
    setReassignDraftValue('')
  }

  function clearReassignment(fileId: number): void {
    setReassignments((prev) => {
      const next = new Map(prev)
      next.delete(fileId)
      return next
    })
  }

  const trimmedName = name.trim()
  const materializingCount = candidates.filter(
    (c) => !excluded.has(c.file_id) && !reassignments.has(c.file_id)
  ).length
  const redirectedCount = reassignments.size

  function handleCommit(): void {
    if (!trimmedName) return
    const excluded_file_ids = Array.from(excluded)
    const reassignmentsList = Array.from(reassignments.entries()).map(([file_id, dest_folder_rel]) => ({
      file_id,
      dest_folder_rel
    }))
    materialize.mutate(
      { personId: person.id, body: { name: trimmedName, excluded_file_ids, reassignments: reassignmentsList } },
      { onSuccess: onCommitted }
    )
  }

  return (
    <>
      <FullscreenModalShell
        onClose={onClose}
        suppressEscape={singleViewIndex !== null || reassignDraftFor !== null}
        headerLeft={
          <div>
            <h2 className="text-sm font-semibold text-white">Review before creating a folder</h2>
            <p className="text-xs text-zinc-400">{candidates.length} photo{candidates.length === 1 ? '' : 's'} found so far</p>
          </div>
        }
      >
        <div className="p-6 pb-28">
          <div className="mb-6 max-w-sm">
            <label className="mb-1 block text-xs font-medium text-zinc-300">Name this person</label>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={person.auto_label}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-zinc-500"
            />
          </div>

          {isLoading && <p className="text-sm text-zinc-400">Loading review…</p>}
          {isError && <p className="text-sm text-red-400">Could not load this person's photos.</p>}

          {preview && candidates.length === 0 && (
            <p className="text-sm text-zinc-400">No photos found for this person.</p>
          )}

          {candidates.length > 0 && (
            <section>
              <h3 className="mb-3 text-sm font-medium text-white">Confirm these are all the same person</h3>
              <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
                {candidates.map((c, i) => {
                  const isExcluded = excluded.has(c.file_id)
                  const reassignTo = reassignments.get(c.file_id)
                  const status = reassignTo ? 'redirected' : isExcluded ? 'negative' : 'positive'
                  const statusLabel = reassignTo
                    ? `Will move into ${reassignTo}`
                    : isExcluded
                      ? 'Not this person — will stay where it is'
                      : 'Will move into the new folder'
                  return (
                    <MatchReviewCard
                      key={c.file_id}
                      libraryId={libraryId}
                      path={c.path}
                      kind={c.kind}
                      onOpenSingle={() => setSingleViewIndex(i)}
                      status={status}
                      statusLabel={statusLabel}
                      reassignTo={reassignTo}
                      actions={
                        <div className="flex flex-wrap gap-1.5">
                          <button
                            onClick={() => toggleExclude(c.file_id)}
                            disabled={!!reassignTo}
                            className="rounded-lg bg-zinc-700 px-2 py-1 text-xs text-white hover:bg-zinc-600 disabled:opacity-40"
                          >
                            {isExcluded ? 'Include again' : 'Not this person'}
                          </button>
                          <button
                            onClick={() => openReassignDraft(c.file_id)}
                            className="rounded-lg border border-zinc-600 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800"
                          >
                            Move to a different folder…
                          </button>
                          {reassignTo && (
                            <button
                              onClick={() => clearReassignment(c.file_id)}
                              className="rounded-lg border border-zinc-600 px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-800"
                            >
                              Undo
                            </button>
                          )}
                        </div>
                      }
                    />
                  )
                })}
              </div>
            </section>
          )}
        </div>

        <div className="fixed bottom-0 left-0 right-0 border-t border-zinc-800 bg-zinc-900/95 px-8 py-4 backdrop-blur">
          <div className="mx-auto flex max-w-4xl items-center justify-between">
            <p className="text-sm text-zinc-300">
              {materializingCount} photo{materializingCount === 1 ? '' : 's'} will form the new folder
              {redirectedCount > 0 && ` · ${redirectedCount} redirected elsewhere`}
            </p>
            <div className="flex items-center gap-2">
              {materialize.isError && (
                <span className="text-sm text-red-400">{materialize.error.message}</span>
              )}
              <button
                type="button"
                onClick={onClose}
                className="rounded-xl border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleCommit}
                disabled={materialize.isPending || isLoading || !trimmedName}
                title={!trimmedName ? 'Name this person first' : undefined}
                className="rounded-xl bg-zinc-100 px-5 py-2 text-sm font-medium text-zinc-900 transition hover:bg-white disabled:opacity-50"
              >
                {materialize.isPending ? 'Creating…' : 'Create folder'}
              </button>
            </div>
          </div>
        </div>
      </FullscreenModalShell>

      {reassignDraftFor !== null && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50">
          <div className="w-full max-w-sm rounded-2xl border border-zinc-700 bg-zinc-900 p-6 shadow-2xl">
            <h3 className="mb-2 text-sm font-semibold text-white">Move to a different folder</h3>
            <p className="mb-3 text-xs text-zinc-400">
              Folder path relative to the library root, e.g. <code className="rounded bg-zinc-800 px-1">Family/Bob</code>.
            </p>
            <input
              autoFocus
              value={reassignDraftValue}
              onChange={(e) => setReassignDraftValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') saveReassignDraft()
                if (e.key === 'Escape') setReassignDraftFor(null)
              }}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-zinc-500"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setReassignDraftFor(null)}
                className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800"
              >
                Cancel
              </button>
              <button
                onClick={saveReassignDraft}
                disabled={!reassignDraftValue.trim()}
                className="rounded-lg bg-zinc-100 px-4 py-2 text-sm font-medium text-zinc-900 hover:bg-white disabled:opacity-50"
              >
                Set folder
              </button>
            </div>
          </div>
        </div>
      )}

      {singleViewIndex !== null && (
        <MediaViewer
          libraryId={libraryId}
          files={viewerFiles}
          index={singleViewIndex}
          onClose={() => setSingleViewIndex(null)}
          onIndexChange={setSingleViewIndex}
        />
      )}
    </>
  )
}
