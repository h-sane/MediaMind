import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, ChevronDown, ChevronRight } from 'lucide-react'
import {
  useOrganizePreview,
  useOrganizeExecute,
  useOrganizeExecuteJob,
  useOrganizeUndo,
  useOrganizeAudit
} from '../../../api/hooks'
import { useJobsStore } from '../../../stores/jobs'
import type { ExecutionReport, PlannedMove } from '../../../api/client'

interface Props {
  libraryId: string
  onBack: () => void
}

// Backend action kinds (see store/audit.py) shown in plain language — F9:
// the undo card used to say "Previous organize action" regardless of which
// kind it actually was, which was misleading once merge/materialize actions
// also became undoable here.
const ACTION_KIND_LABELS: Record<string, string> = {
  'organize-by-person': 'organize',
  'export-by-person': 'export',
  'faces-merge-into-folder': 'merge into folder',
  'faces-materialize': 'create folder',
  'faces-prep-create-unsorted': 'create Unsorted folder'
}

function ConfirmOrganizeDialog({
  planned,
  isExport,
  onConfirm,
  onCancel,
  isPending
}: {
  planned: number
  isExport: boolean
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
}): React.JSX.Element {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-sm rounded-2xl border border-zinc-200 bg-white p-6 shadow-2xl">
        <h3 className="mb-2 text-sm font-semibold">
          {isExport ? `Export ${planned} files?` : `Organize ${planned} files?`}
        </h3>
        <p className="mb-5 text-xs text-zinc-500">
          {isExport ? (
            <>
              Copies will be placed into <code>People/</code> subfolders. Your original files stay exactly
              where they are — nothing is moved. You can undo this afterwards.
            </>
          ) : (
            <>
              Files will be moved into <code>People/</code> subfolders inside this folder. This operation is
              reversible — you can undo it afterwards.
            </>
          )}
        </p>
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-lg border border-zinc-200 px-4 py-2 text-sm text-zinc-600 hover:bg-zinc-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isPending}
            className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
          >
            {isPending ? (isExport ? 'Exporting…' : 'Organizing…') : isExport ? 'Export' : 'Organize'}
          </button>
        </div>
      </div>
    </div>
  )
}

function ResultBanner({ report, isExport, onDismiss }: { report: ExecutionReport; isExport: boolean; onDismiss: () => void }): React.JSX.Element {
  const ok = report.ok
  const verb = isExport ? 'copied' : 'moved'
  return (
    <div className={`mb-6 rounded-xl border px-5 py-4 ${ok ? 'border-emerald-200 bg-emerald-50' : 'border-red-200 bg-red-50'}`}>
      <div className="flex items-start justify-between">
        <div>
          <p className={`text-sm font-medium ${ok ? 'text-emerald-800' : 'text-red-800'}`}>
            {ok
              ? `Done — ${report.handled} of ${report.planned} files ${verb}`
              : `Partial — ${report.handled}/${report.planned} succeeded, ${report.entries.filter((e) => e.error).length} errors`}
          </p>
          {report.dry_run && <p className="mt-1 text-xs text-zinc-500">Dry run — nothing was {verb}</p>}
        </div>
        <button onClick={onDismiss} className="text-xs text-zinc-400 hover:text-zinc-600">
          Dismiss
        </button>
      </div>
      {!ok && (
        <ul className="mt-3 space-y-1">
          {report.entries.filter((e) => e.error).slice(0, 5).map((e, i) => (
            <li key={i} className="text-xs text-red-700">{e.source}: {e.error}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

interface Group {
  key: string
  label: string
  moves: PlannedMove[]
}

function groupMoves(moves: PlannedMove[]): Group[] {
  const byFolder = new Map<string, Group>()
  for (const m of moves) {
    const key = m.dest_folder_rel
    const label = m.person_name || key.split('/').pop() || key
    let g = byFolder.get(key)
    if (!g) {
      g = { key, label, moves: [] }
      byFolder.set(key, g)
    }
    g.moves.push(m)
  }
  return [...byFolder.values()].sort((a, b) => b.moves.length - a.moves.length)
}

function PersonGroup({
  group,
  excluded,
  onToggleFile,
  onToggleGroup
}: {
  group: Group
  excluded: Set<string>
  onToggleFile: (sourceRel: string) => void
  onToggleGroup: (moves: PlannedMove[], include: boolean) => void
}): React.JSX.Element {
  const [expanded, setExpanded] = useState(false)
  const isHolding = group.label.startsWith('_')
  const displayLabel = isHolding ? group.label.slice(1) : group.label
  const includedCount = group.moves.filter((m) => !excluded.has(m.source_rel)).length
  const allIncluded = includedCount === group.moves.length
  const noneIncluded = includedCount === 0

  return (
    <div className="rounded-xl border border-zinc-100">
      <div className="flex items-center gap-2 px-3 py-2">
        <input
          type="checkbox"
          checked={allIncluded}
          ref={(el) => {
            if (el) el.indeterminate = !allIncluded && !noneIncluded
          }}
          onChange={() => onToggleGroup(group.moves, noneIncluded || !allIncluded)}
          className="h-4 w-4 rounded border-zinc-300"
        />
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex flex-1 items-center gap-1.5 text-left"
        >
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5 text-zinc-400" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-zinc-400" />
          )}
          <span className={`text-sm ${isHolding ? 'text-zinc-400' : 'text-zinc-700'}`}>
            {isHolding ? displayLabel : `People/${displayLabel}`}
          </span>
        </button>
        <span className="text-xs text-zinc-400">
          {includedCount}/{group.moves.length} file{group.moves.length !== 1 ? 's' : ''}
        </span>
      </div>
      {expanded && (
        <div className="max-h-56 overflow-y-auto border-t border-zinc-100 bg-zinc-50 px-3 py-2">
          {group.moves.map((m) => (
            <label
              key={m.source_rel}
              title={m.reason}
              className="flex items-center gap-2 py-1 text-xs text-zinc-600"
            >
              <input
                type="checkbox"
                checked={!excluded.has(m.source_rel)}
                onChange={() => onToggleFile(m.source_rel)}
                className="h-3.5 w-3.5 rounded border-zinc-300"
              />
              <span className="truncate">{m.source_rel.split('/').pop()}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

/** Organize-by-people panel — plan preview, dry run, execute, undo, and a
 * link to the full history. Round-1: the history list itself renders inline
 * at the bottom rather than a separate Audit sub-view (deferred). */
export function OrganizePanel({ libraryId, onBack }: Props): React.JSX.Element {
  // Export (copy) is the V3 default — the virtual person view is where you
  // browse; export produces real, sendable per-person folders without
  // touching your originals. "Move" is the older, destructive alternative.
  const [mode, setMode] = useState<'copy' | 'move'>('copy')
  const [groupScope, setGroupScope] = useState<'prominent' | 'all'>('all')
  const isExport = mode === 'copy'
  // A move can't fan one file into several folders, so it's always "prominent".
  const effectiveScope = isExport ? groupScope : 'prominent'

  const { data: preview, isLoading, isError } = useOrganizePreview(libraryId, effectiveScope)
  const { data: audit } = useOrganizeAudit(libraryId)
  const execute = useOrganizeExecute(libraryId)
  const executeJob = useOrganizeExecuteJob(libraryId)
  const undo = useOrganizeUndo(libraryId)

  const [showConfirm, setShowConfirm] = useState(false)
  const [result, setResult] = useState<ExecutionReport | null>(null)
  const [showRescanNotice, setShowRescanNotice] = useState(false)
  const [pendingJobId, setPendingJobId] = useState<string | null>(null)
  const [excluded, setExcluded] = useState<Set<string>>(new Set())

  const lastAction = audit?.find((a) => !a.dry_run && !a.undone && a.ok)

  const groups = useMemo(() => groupMoves(preview?.moves ?? []), [preview])
  const includedCount = (preview?.moves.length ?? 0) - excluded.size

  const jobs = useJobsStore((s) => s.jobs)
  useEffect(() => {
    if (!pendingJobId) return
    const job = jobs[pendingJobId]
    if (!job) return
    if (job.state === 'succeeded') {
      // Only a move invalidates the DB paths (originals relocated). Export
      // copies leave originals in place, so no rescan is needed.
      if (job.result?.ok && !isExport) setShowRescanNotice(true)
      setPendingJobId(null)
    } else if (job.state === 'failed' || job.state === 'cancelled') {
      setPendingJobId(null)
    }
  }, [jobs, pendingJobId])

  const toggleFile = (sourceRel: string) => {
    setExcluded((prev) => {
      const next = new Set(prev)
      if (next.has(sourceRel)) next.delete(sourceRel)
      else next.add(sourceRel)
      return next
    })
  }

  const toggleGroup = (moves: PlannedMove[], include: boolean) => {
    setExcluded((prev) => {
      const next = new Set(prev)
      for (const m of moves) {
        if (include) next.delete(m.source_rel)
        else next.add(m.source_rel)
      }
      return next
    })
  }

  const handleDryRun = () => {
    execute.mutate(
      {
        dryRun: true,
        expectedPlanned: preview?.planned,
        expectedPlanHash: preview?.plan_hash,
        excludedSources: [...excluded],
        mode,
        groupScope: effectiveScope
      },
      { onSuccess: (data) => setResult(data) }
    )
  }

  // Real execution runs as a background job (see JobProgressBubble) so
  // a large batch shows progress and can be cancelled instead of blocking
  // this dialog — the confirm dialog closes immediately, mirroring the
  // dedupe bulk-delete flow. Completion/errors surface on the bubble itself;
  // pendingJobId above just watches for the rescan-notice trigger.
  const handleExecute = () => {
    executeJob.mutate(
      {
        expectedPlanned: preview?.planned,
        expectedPlanHash: preview?.plan_hash,
        excludedSources: [...excluded],
        mode,
        groupScope: effectiveScope
      },
      {
        onSuccess: (snap) => {
          setPendingJobId(snap.id)
          setShowConfirm(false)
        }
      }
    )
  }

  const handleUndo = () => {
    undo.mutate(undefined, { onSuccess: () => setResult(null) })
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      {showConfirm && preview && (
        <ConfirmOrganizeDialog
          planned={includedCount}
          isExport={isExport}
          onConfirm={handleExecute}
          onCancel={() => setShowConfirm(false)}
          isPending={executeJob.isPending}
        />
      )}

      <button onClick={onBack} className="mb-6 flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to people
      </button>

      <div className="mb-6">
        <h2 className="text-lg font-semibold tracking-tight">
          {isExport ? 'Export to folders' : 'Organize by people'}
        </h2>
        <p className="mt-1 text-sm text-zinc-500">
          {isExport ? (
            <>
              Copy your media into <code className="rounded bg-zinc-100 px-1 text-xs">People/</code> subfolders,
              one folder per person — real, sendable copies. Your originals stay put. Uncheck anything you don't
              want exported; hover a file for why it's routed there.
            </>
          ) : (
            <>
              Move your media into <code className="rounded bg-zinc-100 px-1 text-xs">People/</code> subfolders,
              one folder per person. Uncheck anything you don't want moved yet — hover a file for why it's routed
              there.
            </>
          )}
        </p>
      </div>

      {/* Copy (export, non-destructive) vs Move (organize, changes originals) */}
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <div className="inline-flex rounded-lg border border-zinc-200 p-0.5">
          <button
            onClick={() => setMode('copy')}
            className={`rounded-md px-3 py-1.5 text-xs font-medium ${isExport ? 'bg-zinc-900 text-white' : 'text-zinc-600 hover:bg-zinc-50'}`}
          >
            Copy for export
          </button>
          <button
            onClick={() => setMode('move')}
            className={`rounded-md px-3 py-1.5 text-xs font-medium ${!isExport ? 'bg-zinc-900 text-white' : 'text-zinc-600 hover:bg-zinc-50'}`}
          >
            Move originals
          </button>
        </div>

        {isExport && (
          <label className="flex items-center gap-2 text-xs text-zinc-600">
            Group photos:
            <select
              value={groupScope}
              onChange={(e) => setGroupScope(e.target.value as 'prominent' | 'all')}
              className="rounded-md border border-zinc-200 px-2 py-1 text-xs"
            >
              <option value="all">Copy into everyone&apos;s folder</option>
              <option value="prominent">Only the main person</option>
            </select>
          </label>
        )}
      </div>

      {result && <ResultBanner report={result} isExport={isExport} onDismiss={() => { setResult(null); setShowRescanNotice(false) }} />}

      {showRescanNotice && (
        <div className="mb-4 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
          <svg className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>
          <div className="flex-1">
            <p className="text-sm font-medium text-amber-800">Run a face scan to update file locations</p>
            <p className="mt-0.5 text-xs text-amber-700">
              Files were moved on disk. The database still points to old paths — organizing again before
              rescanning will fail for already-moved files.
            </p>
          </div>
          <button onClick={() => setShowRescanNotice(false)} className="text-amber-400 hover:text-amber-600">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {execute.isError && (
        <p className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {execute.error.message}
        </p>
      )}
      {executeJob.isError && (
        <p className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {executeJob.error.message}
        </p>
      )}
      {undo.isError && (
        <p className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {undo.error.message}
        </p>
      )}

      <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
        <h3 className="mb-4 text-sm font-semibold">Plan</h3>

        {isLoading && <p className="text-sm text-zinc-400">Loading plan…</p>}
        {isError && <p className="text-sm text-zinc-400">No face scan found. Run a face scan first to organize by people.</p>}

        {preview && preview.planned === 0 && (
          <div className="rounded-xl border border-dashed border-zinc-200 bg-zinc-50 px-4 py-6 text-center">
            <p className="text-sm font-medium text-zinc-600">Nothing to organize right now</p>
            <p className="mx-auto mt-1 max-w-sm text-xs text-zinc-400">
              Every detected person&apos;s photos are already in place, sitting in a respected folder, or nobody
              has been named or matched to a folder yet. Name people or accept a folder match on the People
              tab, then come back.
            </p>
          </div>
        )}

        {preview && preview.planned > 0 && (
          <>
            <p className="mb-4 text-sm text-zinc-700">
              <span className="font-medium">{includedCount}</span> of{' '}
              <span className="font-medium">{preview.planned}</span> files selected, into{' '}
              <span className="font-medium">{groups.length}</span> folders.
            </p>

            <div className="mb-4 space-y-2">
              {groups.map((g) => (
                <PersonGroup key={g.key} group={g} excluded={excluded} onToggleFile={toggleFile} onToggleGroup={toggleGroup} />
              ))}
            </div>

            {preview.stayed_unrecognized > 0 && (
              <p className="mb-4 text-xs text-zinc-400">
                {preview.stayed_unrecognized} file{preview.stayed_unrecognized !== 1 ? 's' : ''} stay in place
                (unrecognized) — nobody in {preview.stayed_unrecognized !== 1 ? 'them' : 'it'} has been named yet.
              </p>
            )}

            <div className="flex flex-wrap gap-2">
              <button
                onClick={handleDryRun}
                disabled={execute.isPending || includedCount === 0}
                className="rounded-lg border border-zinc-200 px-4 py-2 text-sm text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
              >
                {execute.isPending ? 'Running…' : 'Dry run'}
              </button>
              <button
                onClick={() => setShowConfirm(true)}
                disabled={executeJob.isPending || includedCount === 0}
                className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
              >
                {isExport ? 'Export' : 'Organize'} {includedCount} files
              </button>
            </div>
          </>
        )}
      </div>

      {lastAction && (
        <div className="mt-4 rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">
                Previous action: {ACTION_KIND_LABELS[lastAction.kind] ?? lastAction.kind}
              </p>
              <p className="mt-0.5 text-xs text-zinc-500">
                {lastAction.handled} files {lastAction.kind === 'export-by-person' ? 'copied' : 'moved'} on{' '}
                {new Date(lastAction.created_at * 1000).toLocaleDateString()}
              </p>
            </div>
            <button
              onClick={handleUndo}
              disabled={undo.isPending}
              className="rounded-lg border border-zinc-200 px-3 py-2 text-sm text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
            >
              {undo.isPending ? 'Undoing…' : 'Undo'}
            </button>
          </div>
          {undo.isError && <p className="mt-2 text-xs text-red-600">{undo.error.message}</p>}
        </div>
      )}
    </div>
  )
}
