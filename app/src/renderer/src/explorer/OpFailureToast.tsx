import { useOpStatusStore } from '../stores/opStatus'

/** The one moment a move/copy/delete becomes visible in the UI: silent on
 * success (the manifest is the audit trail), surfaced here only when
 * report.ok is false. */
export function OpFailureToast(): React.JSX.Element | null {
  const report = useOpStatusStore((s) => s.lastFailure)
  const message = useOpStatusStore((s) => s.lastMessage)
  const clear = useOpStatusStore((s) => s.clear)

  if (message) {
    return (
      <div className="absolute bottom-4 right-4 z-40 w-96 rounded-lg border border-red-200 bg-white p-3 text-sm shadow-lg">
        <div className="flex items-start justify-between gap-2">
          <p className="text-zinc-700">{message}</p>
          <button
            type="button"
            onClick={clear}
            className="shrink-0 text-zinc-400 hover:text-zinc-600"
            aria-label="Dismiss"
          >
            ×
          </button>
        </div>
      </div>
    )
  }

  if (!report) return null
  const failedCount = report.entries.filter((e) => e.action === 'error').length

  return (
    <div className="absolute bottom-4 right-4 z-40 w-96 rounded-lg border border-red-200 bg-white p-3 text-sm shadow-lg">
      <div className="flex items-start justify-between gap-2">
        <p className="font-medium text-zinc-900">
          {failedCount} of {report.planned} item{report.planned === 1 ? '' : 's'} could not be completed
        </p>
        <button
          type="button"
          onClick={clear}
          className="shrink-0 text-zinc-400 hover:text-zinc-600"
          aria-label="Dismiss"
        >
          ×
        </button>
      </div>
      <ul className="mt-2 max-h-32 space-y-1 overflow-y-auto text-xs text-zinc-500">
        {report.entries
          .filter((e) => e.action === 'error')
          .map((e, i) => (
            <li key={i} className="truncate" title={`${e.source}: ${e.error}`}>
              {e.source.split(/[\\/]/).pop()}: {e.error}
            </li>
          ))}
      </ul>
      {report.manifest_path && (
        <p className="mt-2 truncate text-[11px] text-zinc-400" title={report.manifest_path}>
          Details: {report.manifest_path}
        </p>
      )}
    </div>
  )
}
