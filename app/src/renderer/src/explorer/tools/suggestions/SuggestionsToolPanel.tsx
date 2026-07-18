import { CopyCheck, Sparkles } from 'lucide-react'
import { useDuplicates } from '../../../api/hooks'
import { useExplorerStore } from '../../../stores/explorer'

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
// Root panel
// ---------------------------------------------------------------------------

/**
 * Duplicates surface — shell-level, scoped to the currently open folder like
 * the dedupe/faces tools. Folder-organization suggestions (person/group
 * folder matches) moved to the Facial Recognition tab, where they now
 * surface directly as tiles on the person they match instead of a separate
 * accept/dismiss queue here.
 */
export function SuggestionsToolPanel({ libraryId, folderPath: _folderPath }: Props): React.JSX.Element {
  return (
    <div className="h-full overflow-y-auto p-6 pb-24">
      <div className="mb-6">
        <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <Sparkles className="h-5 w-5 text-zinc-400" />
          Suggestions
        </h2>
        <p className="mt-1 text-sm text-zinc-500">Duplicates MediaMind noticed in this folder.</p>
      </div>

      <div className="space-y-8">
        <DuplicatesSection libraryId={libraryId} />
      </div>
    </div>
  )
}
