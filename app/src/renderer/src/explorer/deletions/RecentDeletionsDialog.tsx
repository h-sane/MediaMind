import { ExternalLink, Trash2, X } from 'lucide-react'
import { useRecentDeletions } from '../../api/useDeletions'
import { formatDate } from '../format'

interface Props {
  open: boolean
  onClose: () => void
}

function baseName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path
}

/**
 * Read-only history of files this app has deleted (Phase P item 4) —
 * "promote the undo/redo stack into a persisted Recent deletions panel"
 * from the Explorer-parity plan's borderline-items list. Deliberately does
 * *not* attempt to restore anything itself: a permanent delete has nothing
 * left to restore, and a trashed item's restore-by-path via Windows Shell
 * automation is exactly the kind of fragile, hard-to-verify OS automation
 * this project's safety rules (CLAUDE.md: "never break user media",
 * "safety before performance") steer away from for an irreversible-if-wrong
 * action. Instead, "Restore" hands off to the real, trusted Windows Recycle
 * Bin window (`shell:open-recycle-bin`, Phase F's IPC bridge) where the user
 * completes the restore themselves. Permanent deletions show as history only
 * — greyed out, no action — since the file is genuinely gone.
 */
export function RecentDeletionsDialog({ open, onClose }: Props): React.JSX.Element | null {
  const { data, isPending } = useRecentDeletions(open)

  if (!open) return null

  const deletions = data?.deletions ?? []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div
        className="flex max-h-[70vh] w-[26rem] flex-col rounded-lg bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-2.5">
          <h2 className="text-sm font-semibold text-zinc-900">Recent deletions</h2>
          <button type="button" onClick={onClose} className="rounded p-1 text-zinc-400 hover:bg-zinc-100">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3">
          {isPending ? (
            <p className="py-6 text-center text-sm text-zinc-400">Loading…</p>
          ) : deletions.length === 0 ? (
            <p className="py-6 text-center text-sm text-zinc-400">Nothing deleted yet this session.</p>
          ) : (
            <ul className="divide-y divide-zinc-100">
              {deletions.map((d, i) => (
                <li key={`${d.path}-${d.ts}-${i}`} className="flex items-center gap-2.5 py-2">
                  <Trash2 className={`h-4 w-4 shrink-0 ${d.permanent ? 'text-zinc-300' : 'text-zinc-400'}`} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-zinc-700" title={d.path}>
                      {baseName(d.path)}
                    </p>
                    <p className="truncate text-xs text-zinc-400">
                      {formatDate(d.ts)} · {d.permanent ? 'Permanently deleted' : 'Sent to Recycle Bin'}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-zinc-200 px-4 py-2.5">
          <p className="text-xs text-zinc-400">Restoring a trashed file happens in the real Recycle Bin.</p>
          <button
            type="button"
            onClick={() => void window.mediamind.shellOpenRecycleBin()}
            className="flex items-center gap-1.5 rounded-md bg-zinc-100 px-2.5 py-1.5 text-sm text-zinc-700 hover:bg-zinc-200"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Open Recycle Bin
          </button>
        </div>
      </div>
    </div>
  )
}
