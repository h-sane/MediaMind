import { useEffect, useState } from 'react'
import { AlertTriangle, HardDriveDownload, Loader2, X } from 'lucide-react'
import type { DataLocation, PurgeResult } from '../../../../shared/types'

interface Props {
  open: boolean
  onClose: () => void
}

type Phase = 'confirm' | 'working' | 'blocked' | 'done'

/**
 * "Remove all MediaMind data" — the complete, opt-in wipe. Deletes every
 * library's `.mediamind/` folder plus the central app-data store (recognized
 * people, indexes, settings). The actual deletion runs in the main process
 * (see index.ts `appdata:purge`), which stops the backend first so nothing is
 * locked; this component only drives the confirm → retry-on-offline-drive →
 * done flow. Never touches the user's media — only MediaMind's own folders.
 */
export function RemoveDataDialog({ open, onClose }: Props): React.JSX.Element | null {
  const [phase, setPhase] = useState<Phase>('confirm')
  const [locations, setLocations] = useState<DataLocation[] | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [result, setResult] = useState<PurgeResult | null>(null)

  useEffect(() => {
    if (!open) return
    setPhase('confirm')
    setConfirmed(false)
    setResult(null)
    setLocations(null)
    void window.mediamind.dataLocations().then(setLocations)
  }, [open])

  if (!open) return null

  const unreachable = (locations ?? []).filter((l) => l.kind === 'library' && !l.reachable)

  async function purge(skipUnreachable: boolean): Promise<void> {
    setPhase('working')
    const r = await window.mediamind.purgeData(skipUnreachable)
    setResult(r)
    setPhase(r.done ? 'done' : 'blocked')
  }

  async function recheck(): Promise<void> {
    setLocations(await window.mediamind.dataLocations())
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40" onClick={phase === 'working' ? undefined : onClose}>
      <div
        className="w-[30rem] rounded-lg bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-2.5">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-red-700">
            <AlertTriangle className="h-4 w-4" /> Remove all MediaMind data
          </h2>
          {phase !== 'working' && (
            <button type="button" onClick={onClose} className="rounded p-1 text-zinc-400 hover:bg-zinc-100">
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        <div className="px-4 py-3 text-sm text-zinc-700">
          {phase === 'confirm' && (
            <>
              <p className="mb-2">
                This permanently deletes everything MediaMind has stored — recognized people, face and
                duplicate indexes, thumbnails, and settings. <span className="font-medium">Your photos and
                videos are never touched.</span> This cannot be undone.
              </p>
              <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-zinc-400">Will be removed</p>
              {locations === null ? (
                <p className="text-zinc-400">Checking…</p>
              ) : (
                <ul className="mb-3 max-h-40 space-y-1 overflow-y-auto">
                  {locations.map((l) => (
                    <li key={l.path} className="flex items-center justify-between gap-2">
                      <span className="truncate" title={l.path}>{l.label}</span>
                      {l.kind === 'library' && !l.reachable && (
                        <span className="shrink-0 text-xs text-amber-600">drive not connected</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {unreachable.length > 0 && (
                <p className="mb-3 rounded bg-amber-50 px-2.5 py-2 text-xs text-amber-700">
                  {unreachable.length} librar{unreachable.length === 1 ? 'y is' : 'ies are'} on drives that aren't
                  connected. Connect them first to wipe their data too, or you can skip them.
                </p>
              )}
              <label className="flex cursor-pointer items-start gap-2 py-1">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-zinc-300"
                />
                <span>I understand this permanently removes all MediaMind data.</span>
              </label>
            </>
          )}

          {phase === 'working' && (
            <p className="flex items-center gap-2 py-4 text-zinc-600">
              <Loader2 className="h-4 w-4 animate-spin" /> Removing data…
            </p>
          )}

          {phase === 'blocked' && result && (
            <>
              <p className="mb-2">These libraries are on drives that aren't connected, so their data wasn't removed:</p>
              <ul className="mb-3 max-h-32 list-disc space-y-0.5 overflow-y-auto pl-5 text-zinc-600">
                {result.unreachable.map((u) => (
                  <li key={u}>{u}</li>
                ))}
              </ul>
              <p className="text-xs text-zinc-500">
                Connect those drives and retry to delete everything, or skip them and remove the rest now.
              </p>
            </>
          )}

          {phase === 'done' && result && (
            <>
              <p className="mb-2">
                Removed {result.deleted.length} item{result.deleted.length === 1 ? '' : 's'}.
                {result.unreachable.length > 0 &&
                  ` ${result.unreachable.length} on disconnected drives were left in place.`}
              </p>
              {result.failed.length > 0 && (
                <div className="mb-2 rounded bg-amber-50 px-2.5 py-2 text-xs text-amber-700">
                  {result.failed.length} item{result.failed.length === 1 ? '' : 's'} could not be deleted:
                  <ul className="mt-1 list-disc pl-4">
                    {result.failed.map((f) => (
                      <li key={f.path} className="truncate" title={`${f.path}: ${f.error}`}>{f.path}</li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="text-zinc-600">MediaMind needs to restart to finish.</p>
            </>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-zinc-200 px-4 py-2.5">
          {phase === 'confirm' && (
            <>
              <button
                type="button"
                onClick={onClose}
                className="rounded-md bg-zinc-100 px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-200"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!confirmed || locations === null}
                onClick={() => purge(false)}
                className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Delete all data
              </button>
            </>
          )}

          {phase === 'blocked' && (
            <>
              <button
                type="button"
                onClick={() => purge(true)}
                className="rounded-md bg-zinc-100 px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-200"
              >
                Skip &amp; delete the rest
              </button>
              <button
                type="button"
                onClick={async () => {
                  await recheck()
                  void purge(false)
                }}
                className="flex items-center gap-1.5 rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700"
              >
                <HardDriveDownload className="h-4 w-4" /> Connect drives &amp; retry
              </button>
            </>
          )}

          {phase === 'done' && (
            <button
              type="button"
              onClick={() => window.mediamind.relaunchApp()}
              className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700"
            >
              Restart MediaMind
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
