import { useUpdateStore } from '../stores/update'

// Top-right, non-blocking "a new version is available" card. Persists until the
// user dismisses it; the sidebar button (see NavigationPane) remains as a
// persistent entry point after dismissal. The user drives every step — nothing
// downloads until Update, nothing installs until Restart. Only ever appears in
// a packaged build (the main process only checks for updates when isPackaged).

export function UpdateBubble(): React.JSX.Element | null {
  const { phase, version, percent, error, bubbleDismissed, dismissBubble, download, install } =
    useUpdateStore()

  if (phase === null || bubbleDismissed) return null

  return (
    <div className="fixed top-4 right-4 z-40 w-80 rounded-lg border border-zinc-200 bg-white p-3 text-sm shadow-lg">
      <div className="flex items-start justify-between gap-2">
        <p className="font-medium text-zinc-900">
          {phase === 'available' && `MediaMind ${version} is available`}
          {phase === 'downloading' && `Downloading ${version}…`}
          {phase === 'downloaded' && `MediaMind ${version} is ready to install`}
          {phase === 'error' && 'Update failed'}
        </p>
        {phase !== 'downloading' && (
          <button
            type="button"
            onClick={dismissBubble}
            className="shrink-0 text-zinc-400 hover:text-zinc-600"
            aria-label="Dismiss"
          >
            ×
          </button>
        )}
      </div>

      {phase === 'downloading' && (
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-zinc-100">
          <div
            className="h-full rounded-full bg-zinc-900 transition-all duration-300"
            style={{ width: `${percent}%` }}
          />
        </div>
      )}

      {phase === 'error' && (
        <p className="mt-1 text-xs text-red-600" title={error}>
          {error || 'Could not download the update. Try again later.'}
        </p>
      )}

      {phase === 'available' && (
        <button
          type="button"
          onClick={download}
          className="mt-2 w-full rounded-lg bg-zinc-900 py-1.5 text-xs font-medium text-white hover:bg-zinc-700"
        >
          Update now
        </button>
      )}

      {phase === 'downloaded' && (
        <button
          type="button"
          onClick={install}
          className="mt-2 w-full rounded-lg bg-zinc-900 py-1.5 text-xs font-medium text-white hover:bg-zinc-700"
        >
          Restart & install
        </button>
      )}
    </div>
  )
}
