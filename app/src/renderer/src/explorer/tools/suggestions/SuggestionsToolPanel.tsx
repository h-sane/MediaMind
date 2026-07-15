import { useEffect, useRef, useState } from 'react'
import { CopyCheck, FolderCog, Sparkles, Users } from 'lucide-react'
import {
  useAcceptBindingSuggestion,
  useBindings,
  useBindingSuggestions,
  useDismissBindingSuggestion,
  useDuplicates,
  usePersons,
  useReleaseBinding,
  useRefreshBindings
} from '../../../api/hooks'
import { useExplorerStore } from '../../../stores/explorer'
import { OutlierReviewModal } from './OutlierReviewModal'
import type { BindingSuggestion, FolderBinding } from '../../../api/client'

interface Props {
  libraryId: string
  folderPath: string
}

// ---------------------------------------------------------------------------
// Duplicates section — a lean projection of the dedupe tool's own state.
// No separate scan/queue here; it just reads whatever the last dedupe scan
// produced and links over to the full review surface.
// ---------------------------------------------------------------------------

function DuplicatesSection({ libraryId }: { libraryId: string }): React.JSX.Element {
  const setToolMode = useExplorerStore((s) => s.setToolMode)
  const { data, isError, isLoading } = useDuplicates(libraryId)

  return (
    <section>
      <div className="mb-3 flex items-center gap-2">
        <CopyCheck className="h-4 w-4 text-zinc-400" />
        <h3 className="text-sm font-semibold text-zinc-800">Duplicates</h3>
      </div>

      {isLoading && <p className="text-sm text-zinc-400">Checking…</p>}

      {!isLoading && isError && (
        <div className="rounded-2xl border border-dashed border-zinc-300 p-4">
          <p className="text-sm text-zinc-500">No duplicate scan yet.</p>
          <button
            onClick={() => setToolMode('dedupe')}
            className="mt-2 rounded-lg border border-zinc-200 px-3 py-1.5 text-sm text-zinc-600 transition hover:bg-zinc-50"
          >
            Run duplicate detection
          </button>
        </div>
      )}

      {!isLoading && !isError && data && data.summary.groups === 0 && (
        <div className="rounded-2xl border border-zinc-200 bg-white p-4">
          <p className="text-sm text-zinc-500">No duplicates found in this folder.</p>
        </div>
      )}

      {!isLoading && !isError && data && data.summary.groups > 0 && (
        <div className="flex items-center justify-between rounded-2xl border border-zinc-200 bg-white p-4">
          <div>
            <p className="text-sm font-medium text-zinc-800">
              {data.summary.groups} duplicate {data.summary.groups === 1 ? 'group' : 'groups'}
            </p>
            <p className="mt-0.5 text-xs text-zinc-500">
              {data.summary.files} files · {formatBytes(data.summary.reclaimable_bytes)} reclaimable
            </p>
          </div>
          <button
            onClick={() => setToolMode('dedupe')}
            className="rounded-lg bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-zinc-700"
          >
            Review
          </button>
        </div>
      )}
    </section>
  )
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let n = bytes
  let i = 0
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024
    i++
  }
  return `${n.toFixed(n >= 10 || i === 0 ? 0 : 1)} ${units[i]}`
}

// ---------------------------------------------------------------------------
// Folder organization section — Phase B binding suggestions
// ---------------------------------------------------------------------------

function SuggestionCard({
  suggestion,
  onAccept,
  onDismiss,
  busy
}: {
  suggestion: BindingSuggestion
  onAccept: () => void
  onDismiss: () => void
  busy: boolean
}): React.JSX.Element {
  const outlierCount = suggestion.outlier_file_ids.length
  const kindLabel = suggestion.kind === 'person' ? 'Person folder' : 'Group folder'
  const names = suggestion.person_names.join(', ')

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-medium text-zinc-800">{suggestion.folder_rel}</span>
            <span className="shrink-0 rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-blue-600">
              {kindLabel}
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-500">
            {names} · {suggestion.file_count} files · {Math.round(suggestion.coverage * 100)}% match
            {outlierCount > 0 &&
              ` · ${outlierCount} outlier ${outlierCount === 1 ? 'file' : 'files'} will stay in place`}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            onClick={onDismiss}
            disabled={busy}
            className="rounded-lg border border-zinc-200 px-3 py-1.5 text-xs text-zinc-600 transition hover:bg-zinc-50 disabled:opacity-50"
          >
            Dismiss
          </button>
          <button
            onClick={onAccept}
            disabled={busy}
            className="rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-zinc-700 disabled:opacity-50"
          >
            Respect this folder
          </button>
        </div>
      </div>
    </div>
  )
}

function BindingRow({
  binding,
  onRelease,
  onReviewOutliers,
  busy
}: {
  binding: FolderBinding
  onRelease: () => void
  onReviewOutliers: () => void
  busy: boolean
}): React.JSX.Element {
  const outlierCount = binding.outliers.length
  const approvedCount = binding.outliers.filter((o) => o.accepted).length

  return (
    <div className="flex items-center justify-between rounded-xl border border-zinc-100 bg-zinc-50 px-3 py-2">
      <div className="min-w-0">
        <p className="truncate text-xs font-medium text-zinc-700">{binding.folder_rel}</p>
        <p className="text-[11px] text-zinc-400">
          {binding.person_names.join(', ')}
          {outlierCount > 0 &&
            ` · ${outlierCount} outlier ${outlierCount === 1 ? 'file' : 'files'}` +
              (approvedCount > 0 ? ` (${approvedCount} approved to move)` : '')}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {outlierCount > 0 && (
          <button
            onClick={onReviewOutliers}
            className="rounded-md px-2 py-1 text-[11px] text-zinc-500 transition hover:bg-zinc-200 hover:text-zinc-800"
          >
            Review outliers
          </button>
        )}
        <button
          onClick={onRelease}
          disabled={busy}
          className="rounded-md px-2 py-1 text-[11px] text-zinc-400 transition hover:bg-zinc-200 hover:text-zinc-700 disabled:opacity-50"
        >
          Unfreeze
        </button>
      </div>
    </div>
  )
}

function FolderOrganizationSection({ libraryId }: { libraryId: string }): React.JSX.Element {
  const setToolMode = useExplorerStore((s) => s.setToolMode)
  const { data: personsData } = usePersons(libraryId)
  const hasFaceScan = !!personsData

  const refresh = useRefreshBindings(libraryId)
  const accept = useAcceptBindingSuggestion(libraryId)
  const dismiss = useDismissBindingSuggestion(libraryId)
  const release = useReleaseBinding(libraryId)
  const [reviewingBindingId, setReviewingBindingId] = useState<number | null>(null)

  const { data: suggestionsData, isLoading: suggestionsLoading } = useBindingSuggestions(libraryId)
  const { data: bindingsData } = useBindings(libraryId)

  // Freshness is checked on tool-open only (no filesystem watcher) — refresh
  // detection once per folder, piggybacking on whatever faces scan already ran.
  const refreshedFor = useRef<string | null>(null)
  useEffect(() => {
    if (!hasFaceScan || refreshedFor.current === libraryId) return
    refreshedFor.current = libraryId
    refresh.mutate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [libraryId, hasFaceScan])

  const suggestions = suggestionsData?.suggestions ?? []
  const bindings = bindingsData?.bindings ?? []
  const reviewingBinding = bindings.find((b) => b.id === reviewingBindingId) ?? null

  return (
    <section>
      <div className="mb-3 flex items-center gap-2">
        <FolderCog className="h-4 w-4 text-zinc-400" />
        <h3 className="text-sm font-semibold text-zinc-800">Folder Organization</h3>
      </div>

      {!hasFaceScan && (
        <div className="rounded-2xl border border-dashed border-zinc-300 p-4">
          <p className="text-sm text-zinc-500">Run facial recognition to detect existing folder organization.</p>
          <button
            onClick={() => setToolMode('faces')}
            className="mt-2 rounded-lg border border-zinc-200 px-3 py-1.5 text-sm text-zinc-600 transition hover:bg-zinc-50"
          >
            Run facial recognition
          </button>
        </div>
      )}

      {hasFaceScan && suggestionsLoading && <p className="text-sm text-zinc-400">Checking folders…</p>}

      {hasFaceScan && !suggestionsLoading && suggestions.length === 0 && bindings.length === 0 && (
        <div className="rounded-2xl border border-zinc-200 bg-white p-4">
          <p className="text-sm text-zinc-500">No pre-existing person/group folders detected here.</p>
        </div>
      )}

      {suggestions.length > 0 && (
        <div className="space-y-2">
          {suggestions.map((s) => (
            <SuggestionCard
              key={s.id}
              suggestion={s}
              busy={accept.isPending || dismiss.isPending}
              onAccept={() => accept.mutate(s.id)}
              onDismiss={() => dismiss.mutate(s.id)}
            />
          ))}
        </div>
      )}

      {bindings.length > 0 && (
        <div className="mt-4">
          <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-zinc-400">
            <Users className="h-3 w-3" /> Respected folders
          </p>
          <div className="space-y-1.5">
            {bindings.map((b) => (
              <BindingRow
                key={b.id}
                binding={b}
                busy={release.isPending}
                onRelease={() => release.mutate(b.id)}
                onReviewOutliers={() => setReviewingBindingId(b.id)}
              />
            ))}
          </div>
        </div>
      )}

      {reviewingBinding && (
        <OutlierReviewModal
          libraryId={libraryId}
          binding={reviewingBinding}
          onClose={() => setReviewingBindingId(null)}
        />
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Root panel
// ---------------------------------------------------------------------------

/**
 * Unified Suggestions surface (Phase C) — shell-level, scoped to the
 * currently open folder like the dedupe/faces tools, spanning both. Not a
 * global cross-library panel: every data source here lives in this folder's
 * per-library SQLite DB.
 */
export function SuggestionsToolPanel({ libraryId, folderPath: _folderPath }: Props): React.JSX.Element {
  return (
    <div className="h-full overflow-y-auto p-6 pb-24">
      <div className="mb-6">
        <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <Sparkles className="h-5 w-5 text-zinc-400" />
          Suggestions
        </h2>
        <p className="mt-1 text-sm text-zinc-500">
          Everything MediaMind noticed about this folder — duplicates to review and pre-existing
          organization worth keeping.
        </p>
      </div>

      <div className="space-y-8">
        <DuplicatesSection libraryId={libraryId} />
        <FolderOrganizationSection libraryId={libraryId} />
      </div>
    </div>
  )
}
