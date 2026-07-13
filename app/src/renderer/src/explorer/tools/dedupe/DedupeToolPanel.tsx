import { useEffect, useRef, useState } from 'react'
import { Folder, Maximize2, RefreshCw, RotateCcw, Save, X } from 'lucide-react'
import {
  useDuplicates,
  useResolve,
  useExecute,
  useStartScan,
  useRecycleBinCheck,
  useConfirmReviewed,
  useResetDismissals
} from '../../../api/hooks'
import { selectJobForLibrary, useJobsStore } from '../../../stores/jobs'
import { Thumbnail } from '../../../components/Thumbnail'
import { ScanProgress } from '../../../components/ScanProgress'
import { DuplicateGalleryModal } from './DuplicateGalleryModal'
import { formatBytes, formatDate, subfolderOf } from './format'
import type { DuplicateFile, DuplicateGroup, ExecutionReport } from '../../../api/client'

// ---------------------------------------------------------------------------
// FileTile
// ---------------------------------------------------------------------------

function FileTile({
  file,
  libraryId,
  folderName,
  onToggle,
  onExpand
}: {
  file: DuplicateFile
  libraryId: string
  folderName: string
  onToggle: (id: number, current: DuplicateFile['resolution']) => void
  onExpand: () => void
}): React.JSX.Element {
  const res = file.resolution
  const marked = res === 'trash'
  const location = subfolderOf(file.path, folderName)

  return (
    <div
      className={`relative flex flex-col overflow-hidden rounded-xl border transition ${
        marked ? 'border-red-300 bg-red-50 opacity-60' : 'border-zinc-200 bg-white hover:border-red-200'
      }`}
    >
      <div className="relative aspect-square w-full">
        <button
          type="button"
          onClick={() => onToggle(file.id, res)}
          title={marked ? 'Marked for deletion — click to keep' : 'Click to mark for deletion'}
          className="block h-full w-full text-left"
        >
          <Thumbnail libraryId={libraryId} memberId={file.id} className="h-full w-full" />
        </button>
        {file.suggested_keep && !marked && (
          <span className="pointer-events-none absolute right-1.5 top-1.5 rounded-full bg-zinc-800/80 px-1.5 py-0.5 text-[10px] font-medium text-white">
            Best
          </span>
        )}
        <span
          className={`pointer-events-none absolute left-1.5 top-1.5 flex h-5 w-5 items-center justify-center rounded-full border-2 transition ${
            marked ? 'border-red-500 bg-red-500 text-white' : 'border-white/80 bg-black/20'
          }`}
        >
          {marked && (
            <svg className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth={3} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
            </svg>
          )}
        </span>
        <button
          type="button"
          onClick={onExpand}
          title="Compare fullscreen"
          className="absolute bottom-1.5 right-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-black/50 text-white transition hover:bg-black/70"
        >
          <Maximize2 className="h-3 w-3" />
        </button>
      </div>

      <div className="flex items-center gap-1 border-b border-zinc-100 bg-zinc-50 px-3 py-1">
        <Folder className="h-3 w-3 shrink-0 text-zinc-400" />
        <span className="truncate text-[10px] font-medium text-zinc-500" title={location}>
          {location}
        </span>
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
        <p className={`mt-1 text-[11px] font-medium ${marked ? 'text-red-600' : 'text-zinc-300'}`}>
          {marked ? 'Marked for deletion' : 'Keeping'}
        </p>
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
  folderName,
  onToggle,
  onExpand
}: {
  group: DuplicateGroup
  libraryId: string
  folderName: string
  onToggle: (fileId: number, current: DuplicateFile['resolution']) => void
  onExpand: () => void
}): React.JSX.Element {
  const allResolved = group.files.every((f) => f.resolution !== null)

  return (
    <div className={`mb-4 rounded-2xl border bg-white p-4 shadow-sm transition ${allResolved ? 'border-zinc-100 opacity-75' : 'border-zinc-200'}`}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
              group.match === 'exact' ? 'bg-zinc-900 text-white' : 'bg-amber-100 text-amber-800'
            }`}
          >
            {group.match === 'exact' ? 'Exact copy' : 'Visual match'}
          </span>
          <span className="text-xs text-zinc-400">{group.files.length} files</span>
        </div>
        <button
          type="button"
          onClick={onExpand}
          className="flex items-center gap-1.5 rounded-lg border border-zinc-200 px-2.5 py-1 text-xs text-zinc-600 hover:bg-zinc-50"
        >
          <Maximize2 className="h-3 w-3" /> Compare fullscreen
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
        {group.files.map((f) => (
          <FileTile
            key={f.id}
            file={f}
            libraryId={libraryId}
            folderName={folderName}
            onToggle={onToggle}
            onExpand={onExpand}
          />
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ConfirmTrashDialog
// ---------------------------------------------------------------------------

/** True when every failed entry is the "Recycle Bin unavailable on this
 * drive" case (network/virtual mounts) rather than a genuine per-file
 * problem — the only case where offering a permanent-delete fallback makes
 * sense, since it means retrying won't help. */
function allErrorsAreNetworkDrive(report: ExecutionReport): boolean {
  const errors = report.entries.filter((e) => e.action === 'error')
  return errors.length > 0 && errors.every((e) => e.error.includes('network or virtual drive'))
}

function ConfirmTrashDialog({
  libraryId,
  trashCount,
  permanentOnly = false,
  onClose
}: {
  libraryId: string
  trashCount: number
  /** True when a pre-check already determined this location can't use the
   * Recycle Bin — skips straight to a permanent-delete confirmation instead
   * of attempting a trash that's known to fail. */
  permanentOnly?: boolean
  onClose: () => void
}): React.JSX.Element {
  const execute = useExecute(libraryId)
  const [report, setReport] = useState<ExecutionReport | null>(null)
  const [dryRunResult, setDryRunResult] = useState<ExecutionReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmingPermanent, setConfirmingPermanent] = useState(false)

  const runDryRun = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const r = await execute.mutateAsync({
        dryRun: true,
        expectedTrashCount: trashCount,
        permanent: permanentOnly
      })
      setDryRunResult(r)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  const runExecute = async (permanent = permanentOnly): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      // A permanent-delete retry only targets files still unresolved from the
      // first pass (successfully-trashed ones were already marked consumed
      // server-side), so the expected count must match what's actually left,
      // not the original full trashCount.
      const remaining = permanent && report
        ? report.entries.filter((e) => e.action === 'error').length
        : trashCount
      const r = await execute.mutateAsync({ dryRun: false, expectedTrashCount: remaining, permanent })
      setReport(r)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setLoading(false)
      setConfirmingPermanent(false)
    }
  }

  if (!dryRunResult && !loading && !error) {
    void runDryRun()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center">
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl">
        {report ? (
          <>
            <h2 className="mb-2 text-base font-semibold">{report.ok ? 'Done' : 'Completed with errors'}</h2>
            <p className="mb-4 text-sm text-zinc-500">
              {report.handled}/{report.planned} files{' '}
              {report.entries.some((e) => e.action === 'deleted') ? 'permanently deleted' : 'moved to Recycle Bin'}.
              {report.manifest_path && (
                <> Manifest: <code className="break-all text-[11px]">{report.manifest_path}</code></>
              )}
            </p>
            {!report.ok && (
              <div className="mb-4 max-h-40 overflow-y-auto rounded-lg border border-red-100 bg-red-50 p-3 text-xs text-red-700">
                {report.entries.filter((e) => e.action === 'error').map((e, i) => (
                  <p key={i} className="mb-1">{e.source}: {e.error}</p>
                ))}
              </div>
            )}
            {!report.ok && !permanentOnly && allErrorsAreNetworkDrive(report) && !confirmingPermanent && (
              <button
                onClick={() => setConfirmingPermanent(true)}
                className="mb-3 w-full rounded-xl border border-red-200 py-2.5 text-sm font-medium text-red-700 hover:bg-red-50"
              >
                Permanently delete these files instead
              </button>
            )}
            {confirmingPermanent && (
              <div className="mb-3 rounded-lg border border-red-200 bg-red-50 p-3">
                <p className="mb-2 text-xs text-red-700">
                  This drive doesn&apos;t support the Recycle Bin, so this cannot be undone. Permanently
                  delete the {report.entries.filter((e) => e.action === 'error').length} file(s) that
                  failed?
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => setConfirmingPermanent(false)}
                    className="flex-1 rounded-lg border border-zinc-200 bg-white py-1.5 text-xs text-zinc-600 hover:bg-zinc-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => void runExecute(true)}
                    disabled={loading}
                    className="flex-1 rounded-lg bg-red-600 py-1.5 text-xs font-medium text-white hover:bg-red-500 disabled:opacity-50"
                  >
                    {loading ? 'Deleting…' : 'Permanently delete'}
                  </button>
                </div>
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
            <h2 className="mb-1 text-base font-semibold">
              {permanentOnly ? 'Permanently delete files' : 'Move to Recycle Bin'}
            </h2>
            {permanentOnly ? (
              <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                This location doesn&apos;t support the Recycle Bin — {trashCount} file
                {trashCount !== 1 ? 's' : ''} will be <strong>permanently deleted</strong> and cannot be
                recovered.
              </div>
            ) : (
              <p className="mb-4 text-sm text-zinc-500">
                {trashCount} file{trashCount !== 1 ? 's' : ''} will be moved to the Recycle Bin. You can restore
                them from there.
              </p>
            )}

            {loading && <p className="mb-4 text-sm text-zinc-400">Checking plan…</p>}

            {error && (
              <p className="mb-4 rounded-lg border border-red-100 bg-red-50 px-4 py-2 text-sm text-red-700">
                {error}
              </p>
            )}

            {dryRunResult && !error && (
              <div className="mb-4 rounded-lg border border-zinc-100 bg-zinc-50 px-4 py-3 text-xs text-zinc-600">
                <p className="font-medium">Plan preview</p>
                <p className="mt-1">
                  {dryRunResult.planned} file{dryRunResult.planned !== 1 ? 's' : ''} will be{' '}
                  {permanentOnly ? 'permanently deleted' : 'trashed'}.
                </p>
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
                onClick={() => void runExecute(permanentOnly)}
                disabled={loading || !!error || !dryRunResult}
                className="flex-1 rounded-xl bg-red-600 py-2.5 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
              >
                {loading ? 'Working…' : permanentOnly ? 'Permanently delete' : 'Confirm'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ConfirmSaveDialog
// ---------------------------------------------------------------------------

function ConfirmSaveDialog({
  libraryId,
  reviewableCount,
  onClose
}: {
  libraryId: string
  reviewableCount: number
  onClose: (result?: { confirmed: number; skippedPending: number }) => void
}): React.JSX.Element {
  const confirmReviewed = useConfirmReviewed(libraryId)
  const [error, setError] = useState<string | null>(null)

  const runConfirm = async (): Promise<void> => {
    setError(null)
    try {
      const r = await confirmReviewed.mutateAsync()
      onClose({ confirmed: r.confirmed_groups, skippedPending: r.skipped_pending })
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center">
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl">
        <h2 className="mb-1 text-base font-semibold">Save configuration</h2>
        <p className="mb-4 text-sm text-zinc-500">
          {reviewableCount} group{reviewableCount !== 1 ? 's' : ''} you&apos;ve reviewed won&apos;t be shown
          again on future scans of this folder — unless a new file is added that changes what belongs in the
          group. Groups with files still marked for deletion are skipped; delete them first, then save again.
        </p>
        {error && (
          <p className="mb-4 rounded-lg border border-red-100 bg-red-50 px-4 py-2 text-sm text-red-700">
            {error}
          </p>
        )}
        <div className="flex gap-2">
          <button
            onClick={() => onClose()}
            disabled={confirmReviewed.isPending}
            className="flex-1 rounded-xl border border-zinc-200 py-2.5 text-sm text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => void runConfirm()}
            disabled={confirmReviewed.isPending}
            className="flex-1 rounded-xl bg-zinc-900 py-2.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
          >
            {confirmReviewed.isPending ? 'Saving…' : 'Save configuration'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ConfirmResetDialog
// ---------------------------------------------------------------------------

function ConfirmResetDialog({
  libraryId,
  onClose
}: {
  libraryId: string
  onClose: (result?: { cleared: number; restored: number }) => void
}): React.JSX.Element {
  const resetDismissals = useResetDismissals(libraryId)
  const [error, setError] = useState<string | null>(null)

  const runReset = async (): Promise<void> => {
    setError(null)
    try {
      const r = await resetDismissals.mutateAsync()
      onClose({ cleared: r.cleared_dismissals, restored: r.restored_groups })
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center">
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl">
        <h2 className="mb-1 text-base font-semibold">Reset configuration</h2>
        <p className="mb-4 text-sm text-zinc-500">
          Clears every group you&apos;ve saved for this folder — they&apos;ll reappear in the review list
          immediately, no rescan needed. This only affects what&apos;s hidden here; no files on disk are
          touched.
        </p>
        {error && (
          <p className="mb-4 rounded-lg border border-red-100 bg-red-50 px-4 py-2 text-sm text-red-700">
            {error}
          </p>
        )}
        <div className="flex gap-2">
          <button
            onClick={() => onClose()}
            disabled={resetDismissals.isPending}
            className="flex-1 rounded-xl border border-zinc-200 py-2.5 text-sm text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => void runReset()}
            disabled={resetDismissals.isPending}
            className="flex-1 rounded-xl bg-zinc-900 py-2.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
          >
            {resetDismissals.isPending ? 'Resetting…' : 'Reset configuration'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// DedupeToolPanel (main panel)
// ---------------------------------------------------------------------------

interface Props {
  libraryId: string
  folderPath: string
}

type BulkRule = 'suggested' | 'newest' | 'largest'
type CategoryTab = 'all' | 'exact' | 'near'

export function DedupeToolPanel({ libraryId, folderPath }: Props): React.JSX.Element {
  const { data: dups, isLoading, isError } = useDuplicates(libraryId)
  const resolve = useResolve(libraryId)
  const startScan = useStartScan(libraryId)
  // Preloaded so the "Move to Recycle Bin" button already knows which dialog
  // to show — no failed trash attempt before the user ever sees a permanent-
  // delete warning.
  const { data: recycleBinCheck } = useRecycleBinCheck(libraryId)
  const jobs = useJobsStore((s) => s.jobs)
  const activeJob = selectJobForLibrary(jobs, libraryId, 'dedupe')
  const [dialogMode, setDialogMode] = useState<'trash' | 'permanent' | null>(null)
  const [galleryGroupId, setGalleryGroupId] = useState<number | null>(null)
  const [tab, setTab] = useState<CategoryTab>('all')
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [showResetDialog, setShowResetDialog] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const autoScanTriggered = useRef<string | null>(null)

  // First-run: a folder with no prior dedupe scan starts one automatically —
  // clicking the tool IS the action, no separate "start" click needed. Armed
  // as soon as this library reaches ANY definitive state (has groups, is
  // confirmed empty, or errors as "never scanned") — not just when a scan is
  // actually triggered — so a later transition to zero groups (e.g. "Save
  // configuration" dismissing everything) can't silently re-trigger another
  // scan behind the user's back; only an explicit Rescan click does that.
  useEffect(() => {
    if (isLoading || activeJob) return
    if (autoScanTriggered.current === libraryId) return
    if (dups && dups.groups.length > 0) {
      autoScanTriggered.current = libraryId
      return
    }
    if (!dups && !isError) return // still resolving
    autoScanTriggered.current = libraryId
    startScan.mutate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [libraryId, isLoading, dups, activeJob, isError])

  const trashCount = dups
    ? dups.groups.flatMap((g) => g.files).filter((f) => f.resolution === 'trash').length
    : 0

  const reclaimable = dups
    ? dups.groups.flatMap((g) => g.files).filter((f) => f.resolution === 'trash').reduce((sum, f) => sum + f.size, 0)
    : 0

  const exactCount = dups ? dups.groups.filter((g) => g.match === 'exact').length : 0
  const nearCount = dups ? dups.groups.filter((g) => g.match === 'near').length : 0
  const visibleGroups = dups
    ? dups.groups.filter((g) => tab === 'all' || g.match === tab)
    : []

  function handleToggle(fileId: number, current: DuplicateFile['resolution']): void {
    const action: 'keep' | 'trash' = current === 'trash' ? 'keep' : 'trash'
    resolve.mutate([{ file_id: fileId, action }])
  }

  // Bulk actions only ever touch the currently-visible (tab-scoped) groups —
  // "Keep the best" while on the Exact copy tab must not also mark files in
  // Visual match groups.
  function applyBulkRule(rule: BulkRule): void {
    const resolutions: { file_id: number; action: 'keep' | 'trash' }[] = []
    for (const group of visibleGroups) {
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

  function deselectAll(): void {
    const resolutions = visibleGroups
      .flatMap((g) => g.files)
      .filter((f) => f.resolution === 'trash')
      .map((f) => ({ file_id: f.id, action: 'keep' as const }))
    if (resolutions.length > 0) resolve.mutate(resolutions)
  }

  const folderName = folderPath.replace(/[\\/]+$/, '').split(/[\\/]/).pop() || folderPath

  return (
    <div className="h-full overflow-y-auto p-6 pb-32">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Duplicate Review</h2>
          <p className="mt-0.5 text-sm text-zinc-500">
            {folderName}
            {dups && dups.groups.length > 0 && (
              <>
                {' · '}
                {dups.summary.groups} group{dups.summary.groups !== 1 ? 's' : ''} ·{' '}
                {trashCount > 0 ? `${trashCount} marked for trash · ${formatBytes(reclaimable)} freed` : 'No files marked yet'}
              </>
            )}
          </p>
        </div>
        {!activeJob && dups && (
          <div className="flex items-center gap-2">
            {dups.groups.length > 0 && (
              <>
                <button
                  onClick={() => setGalleryGroupId(dups.groups[0].id)}
                  className="flex items-center gap-1.5 rounded-lg border border-zinc-200 px-3 py-1.5 text-sm text-zinc-600 hover:bg-zinc-50"
                >
                  <Maximize2 className="h-3.5 w-3.5" /> Fullscreen review
                </button>
                <button
                  onClick={() => setShowSaveDialog(true)}
                  className="flex items-center gap-1.5 rounded-lg border border-zinc-200 px-3 py-1.5 text-sm text-zinc-600 hover:bg-zinc-50"
                  title="Confirm reviewed groups so they don't reappear on the next rescan"
                >
                  <Save className="h-3.5 w-3.5" /> Save configuration
                </button>
              </>
            )}
            {/* Not gated on groups.length: an empty result (everything dismissed,
                or a rescan that filtered out everything already-confirmed) must
                still leave the user a way to trigger a fresh scan — otherwise
                "Reset configuration" can strand them on a permanent "No
                duplicates found" with no visible escape hatch. */}
            <button
              onClick={() => startScan.mutate()}
              disabled={startScan.isPending}
              className="flex items-center gap-1.5 rounded-lg border border-zinc-200 px-3 py-1.5 text-sm text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
            >
              <RefreshCw className="h-3.5 w-3.5" /> Rescan
            </button>
            <button
              onClick={() => setShowResetDialog(true)}
              className="flex items-center gap-1.5 rounded-lg border border-zinc-200 px-3 py-1.5 text-sm text-zinc-600 hover:bg-zinc-50"
              title="Clear every saved configuration for this folder so dismissed groups reappear"
            >
              <RotateCcw className="h-3.5 w-3.5" /> Reset configuration
            </button>
          </div>
        )}
      </div>

      {saveMessage && (
        <div className="mb-6 flex items-start justify-between gap-3 rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-600">
          <p>{saveMessage}</p>
          <button
            onClick={() => setSaveMessage(null)}
            className="shrink-0 text-zinc-400 hover:text-zinc-600"
            title="Dismiss"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {activeJob && (
        <div className="mb-6">
          <ScanProgress libraryId={libraryId} job={activeJob} />
        </div>
      )}

      {startScan.isError && (
        <p className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {startScan.error.message}
        </p>
      )}

      {!activeJob && isLoading && <p className="text-sm text-zinc-400">Loading…</p>}

      {!activeJob && isError && !isLoading && (
        <p className="text-sm text-red-600">Could not load duplicate results.</p>
      )}

      {!activeJob && dups && dups.groups.length === 0 && (
        <div className="rounded-2xl border border-dashed border-zinc-300 py-16 text-center">
          <p className="text-sm text-zinc-500">No duplicates found in this folder.</p>
        </div>
      )}

      {!activeJob && dups && dups.groups.length > 0 && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            {([
              ['all', `All (${dups.groups.length})`],
              ['exact', `Exact copy (${exactCount})`],
              ['near', `Visual match (${nearCount})`]
            ] as [CategoryTab, string][]).map(([value, label]) => (
              <button
                key={value}
                onClick={() => setTab(value)}
                className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                  tab === value
                    ? 'bg-zinc-900 text-white'
                    : 'border border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="mb-6 flex flex-wrap items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3">
            <span className="text-xs font-medium text-zinc-500">Bulk rule:</span>
            {([
              ['suggested', 'Keep best quality'],
              ['newest', 'Keep newest'],
              ['largest', 'Keep largest']
            ] as [BulkRule, string][]).map(([rule, label]) => (
              <button
                key={rule}
                onClick={() => applyBulkRule(rule)}
                disabled={resolve.isPending || visibleGroups.length === 0}
                className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-xs text-zinc-600 transition hover:border-zinc-300 hover:bg-zinc-50 disabled:opacity-50"
              >
                {label}
              </button>
            ))}
            <button
              onClick={deselectAll}
              disabled={resolve.isPending || visibleGroups.length === 0}
              className="flex items-center gap-1 rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-xs text-zinc-600 transition hover:border-zinc-300 hover:bg-zinc-50 disabled:opacity-50"
            >
              <X className="h-3 w-3" /> Deselect all
            </button>
          </div>

          {visibleGroups.length === 0 && (
            <div className="rounded-2xl border border-dashed border-zinc-300 py-16 text-center">
              <p className="text-sm text-zinc-500">No groups in this category.</p>
            </div>
          )}

          {visibleGroups.map((group) => (
            <DuplicateGroupCard
              key={group.id}
              group={group}
              libraryId={libraryId}
              folderName={folderName}
              onToggle={handleToggle}
              onExpand={() => setGalleryGroupId(group.id)}
            />
          ))}

          {trashCount > 0 && (
            <div className="fixed bottom-0 right-56 left-0 border-t border-zinc-200 bg-white/90 px-8 py-4 backdrop-blur">
              <div className="mx-auto flex max-w-4xl items-center justify-between">
                <p className="text-sm text-zinc-600">
                  {trashCount} file{trashCount !== 1 ? 's' : ''} marked ·{' '}
                  <span className="font-medium">{formatBytes(reclaimable)}</span> freed
                </p>
                <button
                  onClick={() =>
                    setDialogMode(recycleBinCheck?.recycle_bin_supported === false ? 'permanent' : 'trash')
                  }
                  className="rounded-xl bg-red-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-red-500 active:scale-[0.98]"
                >
                  {recycleBinCheck?.recycle_bin_supported === false ? 'Delete permanently' : 'Move to Recycle Bin'}
                </button>
              </div>
            </div>
          )}

          {dialogMode !== null && (
            <ConfirmTrashDialog
              libraryId={libraryId}
              trashCount={trashCount}
              permanentOnly={dialogMode === 'permanent'}
              onClose={() => setDialogMode(null)}
            />
          )}

          {showSaveDialog && (
            <ConfirmSaveDialog
              libraryId={libraryId}
              reviewableCount={dups.groups.length}
              onClose={(result) => {
                setShowSaveDialog(false)
                if (result) {
                  const parts = [`${result.confirmed} group${result.confirmed !== 1 ? 's' : ''} saved`]
                  if (result.skippedPending > 0) {
                    parts.push(
                      `${result.skippedPending} group${result.skippedPending !== 1 ? 's' : ''} still ` +
                        `${result.skippedPending !== 1 ? 'have' : 'has'} files marked for deletion — ` +
                        `delete them first, then save again`
                    )
                  }
                  setSaveMessage(parts.join(' · '))
                }
              }}
            />
          )}

          {galleryGroupId !== null && (
            <DuplicateGalleryModal
              groups={dups.groups}
              libraryId={libraryId}
              folderName={folderName}
              initialGroupId={galleryGroupId}
              onToggle={handleToggle}
              onClose={() => setGalleryGroupId(null)}
            />
          )}
        </>
      )}

      {showResetDialog && (
        <ConfirmResetDialog
          libraryId={libraryId}
          onClose={(result) => {
            setShowResetDialog(false)
            if (result) {
              setSaveMessage(
                `${result.cleared} saved group${result.cleared !== 1 ? 's' : ''} cleared · ` +
                  `${result.restored} group${result.restored !== 1 ? 's' : ''} back in the review list`
              )
            }
          }}
        />
      )}
    </div>
  )
}
