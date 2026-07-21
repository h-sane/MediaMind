import { X } from 'lucide-react'
import { useSettings, useUpdateSettings } from '../../api/hooks'

interface Props {
  open: boolean
  onClose: () => void
}

/**
 * "Folder Options" — the Explorer shell's own settings surface, reached from
 * the command bar's gear icon. Deliberately scoped to just the one Privacy
 * toggle real Explorer exposes in Folder Options > General > Privacy > "Show
 * recently used files in Quick access": turning it off both hides the Home
 * page's Recent files section and stops recording new opens (see
 * `core/settings.py`'s `SettingsStore` and the `/v1/fs/settings` route),
 * matching the Windows checkbox's actual semantics rather than just a
 * cosmetic filter. The full deferred Settings panel (CLAUDE.md's Explorer
 * clone pivot plan) covers everything else; this is intentionally narrow.
 */
export function FolderOptionsDialog({ open, onClose }: Props): React.JSX.Element | null {
  const { data: settings } = useSettings()
  const updateSettings = useUpdateSettings()

  if (!open) return null

  const recentFilesEnabled = settings?.recent_files_enabled ?? true
  const autoScanEnabled = settings?.auto_scan_enabled ?? false

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div
        className="w-[26rem] rounded-lg bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-2.5">
          <h2 className="text-sm font-semibold text-zinc-900">Folder Options</h2>
          <button type="button" onClick={onClose} className="rounded p-1 text-zinc-400 hover:bg-zinc-100">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-4 py-3">
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-400">Privacy</h3>
          <label className="flex cursor-pointer items-start gap-2.5 py-1.5">
            <input
              type="checkbox"
              checked={recentFilesEnabled}
              onChange={(e) => updateSettings.mutate({ recent_files_enabled: e.target.checked })}
              disabled={updateSettings.isPending}
              className="mt-0.5 h-4 w-4 rounded border-zinc-300"
            />
            <span className="text-sm text-zinc-700">
              Show recently used files
              <span className="mt-0.5 block text-xs text-zinc-400">
                Turning this off clears the Home page's Recent files list and stops tracking new ones.
              </span>
            </span>
          </label>

          <h3 className="mb-2 mt-4 text-xs font-medium uppercase tracking-wide text-zinc-400">
            Auto-scan
          </h3>
          <label className="flex cursor-pointer items-start gap-2.5 py-1.5">
            <input
              type="checkbox"
              checked={autoScanEnabled}
              onChange={(e) => updateSettings.mutate({ auto_scan_enabled: e.target.checked })}
              disabled={updateSettings.isPending}
              className="mt-0.5 h-4 w-4 rounded border-zinc-300"
            />
            <span className="text-sm text-zinc-700">
              Watch folders for new media
              <span className="mt-0.5 block text-xs text-zinc-400">
                When on, MediaMind re-runs duplicate and face detection automatically after new
                photos or videos land in a folder you've opened. Off by default.
              </span>
            </span>
          </label>
        </div>

        <div className="flex justify-end border-t border-zinc-200 px-4 py-2.5">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md bg-zinc-100 px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-200"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
