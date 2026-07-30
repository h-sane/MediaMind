import { useState } from 'react'
import { ArrowLeft, Trash2 } from 'lucide-react'
import { useDuplicateLocations, usePruneDuplicateLocations } from '../../../api/hooks'
import { FileThumbnail } from '../../../components/FileThumbnail'
import type { DuplicateLocationGroup } from '../../../api/client'

interface Props {
  libraryId: string
  onBack: () => void
}

function basename(path: string): string {
  return path.slice(path.lastIndexOf('/') + 1)
}

function ConfirmPruneDialog({
  count,
  onConfirm,
  onCancel,
  isPending
}: {
  count: number
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
}): React.JSX.Element {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-sm rounded-2xl border border-zinc-200 bg-white p-6 shadow-2xl">
        <h3 className="mb-2 text-sm font-semibold">
          Delete {count} {count === 1 ? 'copy' : 'copies'}?
        </h3>
        <p className="mb-5 text-xs text-zinc-500">
          Sent to the Recycle Bin, not permanently deleted — you can restore them from there. The
          original files these were exported from are never touched here.
        </p>
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={isPending}
            className="rounded-lg border border-zinc-200 px-3 py-2 text-sm text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isPending}
            className="rounded-lg bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
          >
            {isPending ? 'Deleting…' : `Delete ${count}`}
          </button>
        </div>
      </div>
    </div>
  )
}

function GroupCard({
  libraryId,
  group,
  selected,
  onToggle,
  onPruneOne
}: {
  libraryId: string
  group: DuplicateLocationGroup
  selected: Set<string>
  onToggle: (path: string) => void
  onPruneOne: (path: string) => void
}): React.JSX.Element {
  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm">
      <p className="mb-3 truncate text-sm font-medium text-zinc-700" title={group.source}>
        {basename(group.source)}
        <span className="ml-2 text-xs font-normal text-zinc-400">
          lives in {group.locations.length} folders
        </span>
      </p>
      <div className="flex flex-wrap gap-3">
        {group.locations.map((loc) => (
          <div key={loc.path} className="relative w-28">
            <FileThumbnail
              libraryId={libraryId}
              path={loc.path}
              kind={loc.kind}
              size={128}
              className="aspect-square w-28"
            />
            {loc.is_source ? (
              <span className="absolute left-1 top-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-medium text-white">
                Original
              </span>
            ) : (
              <>
                <button
                  onClick={() => onToggle(loc.path)}
                  className={`absolute left-1 top-1 flex h-5 w-5 items-center justify-center rounded-full border-2 transition ${
                    selected.has(loc.path)
                      ? 'border-indigo-600 bg-indigo-600'
                      : 'border-white bg-black/30 hover:bg-black/50'
                  }`}
                  title="Select for deletion"
                >
                  {selected.has(loc.path) && (
                    <svg className="h-3 w-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                    </svg>
                  )}
                </button>
                <button
                  onClick={() => onPruneOne(loc.path)}
                  className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-black/30 text-white hover:bg-red-600"
                  title="Delete this copy"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </>
            )}
            <p className="mt-1 truncate text-[10px] text-zinc-400" title={loc.path}>
              {loc.path}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Phase 6B: photos exported (Phase 6A) into more than one person's folder,
 * so the user can prune down to a single copy. Driven by the export
 * manifest + a live filesystem check (see organize.py's
 * list_duplicate_locations) — never offers the original for deletion, only
 * the copies. */
export function DuplicateLocationsPanel({ libraryId, onBack }: Props): React.JSX.Element {
  const { data: groups, isLoading } = useDuplicateLocations(libraryId)
  const prune = usePruneDuplicateLocations(libraryId)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [confirming, setConfirming] = useState<string[] | null>(null)

  const toggle = (path: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  const runPrune = (paths: string[]) => {
    prune.mutate(
      { paths, dryRun: false },
      {
        onSuccess: () => {
          setSelected((prev) => {
            const next = new Set(prev)
            for (const p of paths) next.delete(p)
            return next
          })
          setConfirming(null)
        }
      }
    )
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      {confirming && (
        <ConfirmPruneDialog
          count={confirming.length}
          onConfirm={() => runPrune(confirming)}
          onCancel={() => setConfirming(null)}
          isPending={prune.isPending}
        />
      )}

      <div className="mb-6 flex items-center justify-between">
        <button onClick={onBack} className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to export
        </button>
        {selected.size > 0 && (
          <button
            onClick={() => setConfirming([...selected])}
            className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-500"
          >
            Delete {selected.size} selected
          </button>
        )}
      </div>

      <div className="mb-6">
        <h2 className="text-lg font-semibold tracking-tight">Duplicate locations</h2>
        <p className="mt-1 text-sm text-zinc-500">
          Photos that a previous export copied into more than one person's folder. Select copies to
          prune — the original is never listed as removable here.
        </p>
      </div>

      {isLoading && <p className="text-sm text-zinc-400">Loading…</p>}

      {!isLoading && (groups ?? []).length === 0 && (
        <p className="text-sm text-zinc-400">
          No exported photo currently lives in more than one folder.
        </p>
      )}

      {prune.isError && <p className="mb-4 text-xs text-red-600">{prune.error.message}</p>}

      <div className="space-y-4">
        {(groups ?? []).map((g) => (
          <GroupCard
            key={g.source}
            libraryId={libraryId}
            group={g}
            selected={selected}
            onToggle={toggle}
            onPruneOne={(path) => setConfirming([path])}
          />
        ))}
      </div>
    </div>
  )
}
