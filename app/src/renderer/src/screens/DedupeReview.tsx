import { useState } from 'react'
import { useAppStore } from '../stores/app'
import { useDuplicates, useResolve, useExecute } from '../api/hooks'
import { Thumbnail } from '../components/Thumbnail'
import type { DuplicateFile, DuplicateGroup, ExecutionReport } from '../api/client'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  if (b < 1024 * 1024 * 1024) return `${(b / (1024 * 1024)).toFixed(1)} MB`
  return `${(b / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric'
  })
}

// ---------------------------------------------------------------------------
// FileTile
// ---------------------------------------------------------------------------

function FileTile({
  file,
  libraryId,
  onToggle
}: {
  file: DuplicateFile
  libraryId: string
  onToggle: (id: number, current: DuplicateFile['resolution']) => void
}): React.JSX.Element {
  const res = file.resolution

  return (
    <div
      className={`relative flex flex-col overflow-hidden rounded-xl border transition ${
        res === 'trash'
          ? 'border-red-200 bg-red-50 opacity-60'
          : res === 'keep'
          ? 'border-emerald-300 bg-emerald-50'
          : 'border-zinc-200 bg-white'
      }`}
    >
      <div className="relative aspect-square w-full">
        <Thumbnail libraryId={libraryId} memberId={file.id} className="h-full w-full" />
        {file.suggested_keep && !res && (
          <span className="absolute right-1.5 top-1.5 rounded-full bg-zinc-800/80 px-1.5 py-0.5 text-[10px] font-medium text-white">
            Best
          </span>
        )}
      </div>

      <div className="flex-1 px-3 py-2">
        <p className="truncate text-xs font-medium text-zinc-800" title={file.path}>
          {file.path.split('/').pop()}
        </p>
        <p className="mt-0.5 text-[10px] text-zinc-400">
          {file.width > 0 ? `${file.width}×${file.height} · ` : ''}
          {formatBytes(file.size)}
        </p>
        <p className="text-[10px] text-zinc-400">{formatDate(file.mtime)}</p>

        {/* Keep / Trash toggle */}
        <div className="mt-2 flex gap-1">
          <button
            onClick={() => onToggle(file.id, res)}
            className={`flex-1 rounded-md py-1 text-[11px] font-medium transition ${
              res === 'keep'
                ? 'bg-emerald-600 text-white'
                : 'border border-zinc-200 text-zinc-500 hover:border-emerald-300 hover:text-emerald-700'
            }`}
          >
            Keep
          </button>
          <button
            onClick={() => onToggle(file.id, res)}
            className={`flex-1 rounded-md py-1 text-[11px] font-medium transition ${
              res === 'trash'
                ? 'bg-red-500 text-white'
                : 'border border-zinc-200 text-zinc-500 hover:border-red-300 hover:text-red-600'
            }`}
          >
            Trash
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// DuplicateGroupCard
// ---------------------------------------------------------------------------

function DuplicateGroupCard({
  group,
  libraryId,
  onToggle
}: {
  group: DuplicateGroup
  libraryId: string
  onToggle: (fileId: number, current: DuplicateFile['resolution']) => void
}): React.JSX.Element {
  const allResolved = group.files.every((f) => f.resolution !== null)

  return (
    <div className={`mb-4 rounded-2xl border bg-white p-4 shadow-sm transition ${allResolved ? 'border-zinc-100 opacity-75' : 'border-zinc-200'}`}>
      <div className="mb-3 flex items-center gap-2">
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
            group.match === 'exact'
              ? 'bg-zinc-900 text-white'
              : 'bg-amber-100 text-amber-800'
          }`}
        >
          {group.match === 'exact' ? 'Exact copy' : 'Visually similar'}
        </span>
        <span className="text-xs text-zinc-400">{group.files.length} files</span>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
        {group.files.map((f) => (
          <FileTile key={f.id} file={f} libraryId={libraryId} onToggle={onToggle} />
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ConfirmTrashDialog
// ---------------------------------------------------------------------------

function ConfirmTrashDialog({
  libraryId,
  trashCount,
  onClose
}: {
  libraryId: string
  trashCount: number
  onClose: () => void
}): React.JSX.Element {
  const execute = useExecute(libraryId)
  const [report, setReport] = useState<ExecutionReport | null>(null)
  const [dryRunResult, setDryRunResult] = useState<ExecutionReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const runDryRun = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const r = await execute.mutateAsync({ dryRun: true, expectedTrashCount: trashCount })
      setDryRunResult(r)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  const runExecute = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const r = await execute.mutateAsync({ dryRun: false, expectedTrashCount: trashCount })
      setReport(r)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  // Trigger dry-run on first open
  if (!dryRunResult && !loading && !error) {
    void runDryRun()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center">
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl">
        {/* Done screen */}
        {report ? (
          <>
            <h2 className="mb-2 text-base font-semibold">
              {report.ok ? 'Done' : 'Completed with errors'}
            </h2>
            <p className="mb-4 text-sm text-zinc-500">
              {report.handled}/{report.planned} files moved to Recycle Bin.
              {report.manifest_path && (
                <> Manifest: <code className="text-[11px] break-all">{report.manifest_path}</code></>
              )}
            </p>
            {!report.ok && (
              <div className="mb-4 max-h-40 overflow-y-auto rounded-lg border border-red-100 bg-red-50 p-3 text-xs text-red-700">
                {report.entries.filter((e) => e.action === 'error').map((e, i) => (
                  <p key={i} className="truncate">{e.source}: {e.error}</p>
                ))}
              </div>
            )}
            <button
              onClick={onClose}
              className="w-full rounded-xl bg-zinc-900 py-2.5 text-sm font-medium text-white hover:bg-zinc-700"
            >
              Close
            </button>
          </>
        ) : (
          <>
            <h2 className="mb-1 text-base font-semibold">Move to Recycle Bin</h2>
            <p className="mb-4 text-sm text-zinc-500">
              {trashCount} file{trashCount !== 1 ? 's' : ''} will be moved to the Recycle Bin.
              You can restore them from there.
            </p>

            {loading && (
              <p className="mb-4 text-sm text-zinc-400">Checking plan…</p>
            )}

            {error && (
              <p className="mb-4 rounded-lg border border-red-100 bg-red-50 px-4 py-2 text-sm text-red-700">
                {error}
              </p>
            )}

            {dryRunResult && !error && (
              <div className="mb-4 rounded-lg border border-zinc-100 bg-zinc-50 px-4 py-3 text-xs text-zinc-600">
                <p className="font-medium">Plan preview</p>
                <p className="mt-1">{dryRunResult.planned} file{dryRunResult.planned !== 1 ? 's' : ''} will be trashed.</p>
              </div>
            )}

            <div className="flex gap-2">
              <button
                onClick={onClose}
                disabled={loading}
                className="flex-1 rounded-xl border border-zinc-200 py-2.5 text-sm text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={runExecute}
                disabled={loading || !!error || !dryRunResult}
                className="flex-1 rounded-xl bg-red-600 py-2.5 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
              >
                {loading ? 'Working…' : 'Confirm'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// DedupeReview (main screen)
// ---------------------------------------------------------------------------

interface Props {
  libraryId: string
}

type BulkRule = 'suggested' | 'newest' | 'largest'

export function DedupeReview({ libraryId }: Props): React.JSX.Element {
  const back = useAppStore((s) => s.back)
  const { data: dups, isLoading, isError } = useDuplicates(libraryId)
  const resolve = useResolve(libraryId)
  const [showConfirm, setShowConfirm] = useState(false)

  const trashCount = dups
    ? dups.groups.flatMap((g) => g.files).filter((f) => f.resolution === 'trash').length
    : 0

  const reclaimable = dups
    ? dups.groups
        .flatMap((g) => g.files)
        .filter((f) => f.resolution === 'trash')
        .reduce((sum, f) => sum + f.size, 0)
    : 0

  function handleToggle(fileId: number, current: DuplicateFile['resolution']): void {
    if (!dups) return
    const group = dups.groups.find((g) => g.files.some((f) => f.id === fileId))
    if (!group) return
    const file = group.files.find((f) => f.id === fileId)
    if (!file) return

    let action: 'keep' | 'trash'
    if (current === 'trash') {
      action = 'keep'
    } else if (current === 'keep') {
      action = 'trash'
    } else {
      // toggling from null: if it's the suggested_keep, mark trash; otherwise keep
      action = file.suggested_keep ? 'trash' : 'keep'
    }

    resolve.mutate([{ file_id: fileId, action }])
  }

  function applyBulkRule(rule: BulkRule): void {
    if (!dups) return
    const resolutions: { file_id: number; action: 'keep' | 'trash' }[] = []

    for (const group of dups.groups) {
      let keepFile: DuplicateFile
      if (rule === 'suggested') {
        keepFile = group.files.find((f) => f.suggested_keep) ?? group.files[0]
      } else if (rule === 'newest') {
        keepFile = group.files.reduce((a, b) => (b.mtime > a.mtime ? b : a))
      } else {
        keepFile = group.files.reduce((a, b) => (b.size > a.size ? b : a))
      }
      for (const f of group.files) {
        resolutions.push({ file_id: f.id, action: f.id === keepFile.id ? 'keep' : 'trash' })
      }
    }
    resolve.mutate(resolutions)
  }

  if (isLoading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <p className="text-sm text-zinc-400">Loading…</p>
      </div>
    )
  }

  if (isError || !dups) {
    return (
      <div className="mx-auto max-w-3xl px-8 py-12">
        <button onClick={back} className="mb-6 text-xs text-zinc-400 hover:text-zinc-600">
          ← Back
        </button>
        <p className="text-sm text-red-600">Could not load duplicate results.</p>
      </div>
    )
  }

  return (
    <div className="mx-auto w-full max-w-4xl px-8 pb-32 pt-8">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <button onClick={back} className="mb-2 text-xs text-zinc-400 hover:text-zinc-600">
            ← Back
          </button>
          <h2 className="text-lg font-semibold tracking-tight">Duplicate Review</h2>
          <p className="mt-0.5 text-sm text-zinc-500">
            {dups.summary.groups} group{dups.summary.groups !== 1 ? 's' : ''} ·{' '}
            {trashCount > 0
              ? `${trashCount} marked for trash · ${formatBytes(reclaimable)} freed`
              : 'No files marked yet'}
          </p>
        </div>
      </div>

      {/* Bulk rule bar */}
      <div className="mb-6 flex flex-wrap items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3">
        <span className="text-xs font-medium text-zinc-500">Bulk rule:</span>
        {([
          ['suggested', 'Keep best quality'],
          ['newest', 'Keep newest'],
          ['largest', 'Keep largest'],
        ] as [BulkRule, string][]).map(([rule, label]) => (
          <button
            key={rule}
            onClick={() => applyBulkRule(rule)}
            disabled={resolve.isPending}
            className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-xs text-zinc-600 transition hover:border-zinc-300 hover:bg-zinc-50 disabled:opacity-50"
          >
            {label}
          </button>
        ))}
      </div>

      {/* Group list */}
      {dups.groups.map((group) => (
        <DuplicateGroupCard
          key={group.id}
          group={group}
          libraryId={libraryId}
          onToggle={handleToggle}
        />
      ))}

      {/* Sticky execute footer */}
      {trashCount > 0 && (
        <div className="fixed bottom-0 left-0 right-0 border-t border-zinc-200 bg-white/90 px-8 py-4 backdrop-blur">
          <div className="mx-auto flex max-w-4xl items-center justify-between">
            <p className="text-sm text-zinc-600">
              {trashCount} file{trashCount !== 1 ? 's' : ''} marked ·{' '}
              <span className="font-medium">{formatBytes(reclaimable)}</span> freed
            </p>
            <button
              onClick={() => setShowConfirm(true)}
              className="rounded-xl bg-red-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-red-500 active:scale-[0.98]"
            >
              Move to Recycle Bin
            </button>
          </div>
        </div>
      )}

      {/* Confirm dialog */}
      {showConfirm && (
        <ConfirmTrashDialog
          libraryId={libraryId}
          trashCount={trashCount}
          onClose={() => setShowConfirm(false)}
        />
      )}
    </div>
  )
}
