import { useState } from 'react'
import { useMergeSuggestion, useSuggestionMergePreview } from '../../../api/hooks'
import { MediaViewer } from '../../../components/MediaViewer'
import { FullscreenModalShell } from '../shared/FullscreenModalShell'
import { MatchReviewCard } from './MatchReviewCard'
import type { BindingSuggestion } from '../../../api/client'

interface Props {
  libraryId: string
  suggestion: BindingSuggestion
  onClose: () => void
  onCommitted: () => void
}

/**
 * Full-screen pre-accept review for a folder-match suggestion, reachable at
 * any match percentage. Shows both directions a merge affects:
 *  - files already in the folder that face-matching didn't attribute to
 *    this person (Confirm/Reject are local bookkeeping only — a rejected
 *    file naturally resurfaces in "Review outliers" after merge, since
 *    outliers are recomputed live from face data, not from this session).
 *  - this person's other photos elsewhere that a merge would bring in
 *    (Exclude keeps them where they are; Move elsewhere redirects them to a
 *    folder of the user's choosing instead of the default destination).
 */
export function MatchReviewModal({ libraryId, suggestion, onClose, onCommitted }: Props): React.JSX.Element {
  const { data: preview, isLoading, isError } = useSuggestionMergePreview(libraryId, suggestion.id)
  const mergeSuggestion = useMergeSuggestion(libraryId)

  const [outlierDecisions, setOutlierDecisions] = useState<Map<number, 'confirm' | 'reject'>>(new Map())
  const [moveExcluded, setMoveExcluded] = useState<Set<number>>(new Set())
  const [reassignments, setReassignments] = useState<Map<number, string>>(new Map())
  const [reassignDraftFor, setReassignDraftFor] = useState<number | null>(null)
  const [reassignDraftValue, setReassignDraftValue] = useState('')
  const [singleViewIndex, setSingleViewIndex] = useState<number | null>(null)

  const outliers = preview?.folder_outliers ?? []
  const moves = preview?.moves ?? []
  const viewerFiles = [
    ...outliers.map((o) => ({ path: o.path, kind: o.kind })),
    ...moves.map((m) => ({ path: m.source_rel, kind: m.kind }))
  ]

  function decideOutlier(fileId: number, decision: 'confirm' | 'reject'): void {
    setOutlierDecisions((prev) => new Map(prev).set(fileId, decision))
  }

  function toggleExcludeMove(fileId: number): void {
    setMoveExcluded((prev) => {
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
    setMoveExcluded((prev) => {
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

  function handleCommit(): void {
    const excluded_file_ids = Array.from(moveExcluded).filter((id) => !reassignments.has(id))
    const reassignmentsList = Array.from(reassignments.entries()).map(([file_id, dest_folder_rel]) => ({
      file_id,
      dest_folder_rel
    }))
    mergeSuggestion.mutate(
      { suggestionId: suggestion.id, body: { excluded_file_ids, reassignments: reassignmentsList } },
      { onSuccess: onCommitted }
    )
  }

  const incomingCount = moves.filter((m) => !moveExcluded.has(m.file_id) && !reassignments.has(m.file_id)).length
  const redirectedCount = reassignments.size

  return (
    <>
      <FullscreenModalShell
        onClose={onClose}
        suppressEscape={singleViewIndex !== null || reassignDraftFor !== null}
        headerLeft={
          <div>
            <h2 className="text-sm font-semibold text-white">{suggestion.folder_rel}</h2>
            <p className="text-xs text-zinc-400">
              {suggestion.person_names.join(', ')} · {Math.round(suggestion.coverage * 100)}% match
            </p>
          </div>
        }
      >
        <div className="p-6 pb-28">
          {isLoading && <p className="text-sm text-zinc-400">Loading review…</p>}
          {isError && <p className="text-sm text-red-400">Could not load this suggestion's details.</p>}

          {preview && outliers.length === 0 && moves.length === 0 && (
            <p className="text-sm text-zinc-400">
              Nothing to review — every file in this folder matches, and this person has no other photos elsewhere.
            </p>
          )}

          {outliers.length > 0 && (
            <section className="mb-8">
              <h3 className="mb-3 text-sm font-medium text-white">
                In this folder, not yet matched to {suggestion.person_names.join(', ')}
              </h3>
              <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
                {outliers.map((f, i) => {
                  const decision = outlierDecisions.get(f.file_id)
                  const reassignTo = reassignments.get(f.file_id)
                  const status = reassignTo ? 'redirected' : decision === 'confirm' ? 'positive' : decision === 'reject' ? 'negative' : 'neutral'
                  const statusLabel = reassignTo
                    ? 'Will move out of this folder'
                    : decision === 'confirm'
                      ? 'Confirmed — same person'
                      : decision === 'reject'
                        ? 'Not this person'
                        : 'Undecided'
                  return (
                    <MatchReviewCard
                      key={f.file_id}
                      libraryId={libraryId}
                      path={f.path}
                      kind={f.kind}
                      onOpenSingle={() => setSingleViewIndex(i)}
                      status={status}
                      statusLabel={statusLabel}
                      reassignTo={reassignTo}
                      actions={
                        <div className="flex flex-wrap gap-1.5">
                          <button
                            onClick={() => decideOutlier(f.file_id, 'confirm')}
                            className="rounded-lg bg-emerald-600 px-2 py-1 text-xs font-medium text-white hover:bg-emerald-500"
                          >
                            Confirm
                          </button>
                          <button
                            onClick={() => decideOutlier(f.file_id, 'reject')}
                            className="rounded-lg bg-zinc-700 px-2 py-1 text-xs text-white hover:bg-zinc-600"
                          >
                            Not this person
                          </button>
                          <button
                            onClick={() => openReassignDraft(f.file_id)}
                            className="rounded-lg border border-zinc-600 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800"
                          >
                            Move out of this folder…
                          </button>
                          {reassignTo && (
                            <button
                              onClick={() => clearReassignment(f.file_id)}
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

          {moves.length > 0 && (
            <section>
              <h3 className="mb-3 text-sm font-medium text-white">
                {suggestion.person_names.join(', ')}&apos;s other photos, not yet in this folder
              </h3>
              <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
                {moves.map((m, i) => {
                  const excluded = moveExcluded.has(m.file_id)
                  const reassignTo = reassignments.get(m.file_id)
                  const status = reassignTo ? 'redirected' : excluded ? 'negative' : 'positive'
                  const statusLabel = reassignTo
                    ? 'Redirected elsewhere'
                    : excluded
                      ? 'Will stay where it is'
                      : `Will move into ${suggestion.folder_rel}`
                  return (
                    <MatchReviewCard
                      key={m.file_id}
                      libraryId={libraryId}
                      path={m.source_rel}
                      kind={m.kind}
                      onOpenSingle={() => setSingleViewIndex(outliers.length + i)}
                      status={status}
                      statusLabel={statusLabel}
                      reassignTo={reassignTo}
                      actions={
                        <div className="flex flex-wrap gap-1.5">
                          <button
                            onClick={() => toggleExcludeMove(m.file_id)}
                            disabled={!!reassignTo}
                            className="rounded-lg bg-zinc-700 px-2 py-1 text-xs text-white hover:bg-zinc-600 disabled:opacity-40"
                          >
                            {excluded ? 'Include again' : 'Not this person'}
                          </button>
                          <button
                            onClick={() => openReassignDraft(m.file_id)}
                            className="rounded-lg border border-zinc-600 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800"
                          >
                            Move to a different folder…
                          </button>
                          {reassignTo && (
                            <button
                              onClick={() => clearReassignment(m.file_id)}
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
              {incomingCount} photo{incomingCount === 1 ? '' : 's'} will move into this folder
              {redirectedCount > 0 && ` · ${redirectedCount} redirected elsewhere`}
            </p>
            <div className="flex items-center gap-2">
              {mergeSuggestion.isError && (
                <span className="text-sm text-red-400">{mergeSuggestion.error.message}</span>
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
                disabled={mergeSuggestion.isPending || isLoading}
                className="rounded-xl bg-zinc-100 px-5 py-2 text-sm font-medium text-zinc-900 transition hover:bg-white disabled:opacity-50"
              >
                {mergeSuggestion.isPending ? 'Merging…' : 'Move & organize'}
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
