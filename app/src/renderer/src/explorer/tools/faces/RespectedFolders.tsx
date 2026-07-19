import { useState } from 'react'
import { Users } from 'lucide-react'
import { useBindings, useReleaseBinding } from '../../../api/hooks'
import { OutlierReviewModal } from '../suggestions/OutlierReviewModal'
import type { FolderBinding } from '../../../api/client'

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
          title="Stop respecting this folder — Organize may move its files again"
        >
          Stop respecting
        </button>
      </div>
    </div>
  )
}

/** Folders the user has already merged/accepted — a lone person's photos
 * were folded into them, or (for groups) the folder was respected in place.
 * "Review outliers" reopens the same post-accept review used since Phase B. */
export function RespectedFolders({ libraryId }: { libraryId: string }): React.JSX.Element | null {
  const { data: bindingsData } = useBindings(libraryId)
  const release = useReleaseBinding(libraryId)
  const [reviewingBindingId, setReviewingBindingId] = useState<number | null>(null)

  const bindings = bindingsData?.bindings ?? []
  const reviewingBinding = bindings.find((b) => b.id === reviewingBindingId) ?? null

  if (bindings.length === 0) return null

  return (
    <div className="mt-8">
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

      {reviewingBinding && (
        <OutlierReviewModal
          libraryId={libraryId}
          binding={reviewingBinding}
          onClose={() => setReviewingBindingId(null)}
        />
      )}
    </div>
  )
}
