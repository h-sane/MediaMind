import { useState } from 'react'
import { useAppStore } from '../stores/app'
import {
  useOrganizePreview,
  useOrganizeExecute,
  useOrganizeUndo,
  useOrganizeAudit,
} from '../api/hooks'
import type { ExecutionReport } from '../api/client'
import type { View } from '../stores/app'

interface Props {
  libraryId: string
}

function ConfirmOrganizeDialog({
  planned,
  onConfirm,
  onCancel,
  isPending,
}: {
  planned: number
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
}): React.JSX.Element {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-sm rounded-2xl border border-zinc-200 bg-white p-6 shadow-2xl">
        <h3 className="mb-2 text-sm font-semibold">Organize {planned} files?</h3>
        <p className="mb-5 text-xs text-zinc-500">
          Files will be moved into <code>People/</code> subfolders inside your library. This
          operation is reversible — you can undo it afterwards.
        </p>
        <div className="flex gap-2 justify-end">
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
            {isPending ? 'Organizing…' : 'Organize'}
          </button>
        </div>
      </div>
    </div>
  )
}

function ResultBanner({ report, onDismiss }: { report: ExecutionReport; onDismiss: () => void }): React.JSX.Element {
  const ok = report.ok
  return (
    <div
      className={`mb-6 rounded-xl border px-5 py-4 ${
        ok ? 'border-emerald-200 bg-emerald-50' : 'border-red-200 bg-red-50'
      }`}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className={`text-sm font-medium ${ok ? 'text-emerald-800' : 'text-red-800'}`}>
            {ok
              ? `Done — ${report.handled} of ${report.planned} files moved`
              : `Partial — ${report.handled}/${report.planned} succeeded, ${report.entries.filter((e) => e.error).length} errors`}
          </p>
          {report.dry_run && (
            <p className="mt-1 text-xs text-zinc-500">Dry run — nothing was moved</p>
          )}
        </div>
        <button onClick={onDismiss} className="text-xs text-zinc-400 hover:text-zinc-600">
          Dismiss
        </button>
      </div>
      {!ok && (
        <ul className="mt-3 space-y-1">
          {report.entries
            .filter((e) => e.error)
            .slice(0, 5)
            .map((e, i) => (
              <li key={i} className="text-xs text-red-700">
                {e.source}: {e.error}
              </li>
            ))}
        </ul>
      )}
    </div>
  )
}

export function OrganizeScreen({ libraryId }: Props): React.JSX.Element {
  const back = useAppStore((s) => s.back)
  const navigate = useAppStore((s) => s.navigate)

  const { data: preview, isLoading, isError } = useOrganizePreview(libraryId)
  const { data: audit } = useOrganizeAudit(libraryId)
  const execute = useOrganizeExecute(libraryId)
  const undo = useOrganizeUndo(libraryId)

  const [showConfirm, setShowConfirm] = useState(false)
  const [result, setResult] = useState<ExecutionReport | null>(null)
  const [showMoves, setShowMoves] = useState(false)
  const [showRescanNotice, setShowRescanNotice] = useState(false)

  const lastAction = audit?.find((a) => !a.dry_run && !a.undone && a.ok)

  const handleDryRun = () => {
    execute.mutate({ dryRun: true }, {
      onSuccess: (data) => setResult(data),
    })
  }

  const handleExecute = () => {
    execute.mutate(
      { dryRun: false, expectedPlanned: preview?.planned },
      {
        onSuccess: (data) => {
          setResult(data)
          setShowConfirm(false)
          if (data.ok && !data.dry_run) setShowRescanNotice(true)
        },
      }
    )
  }

  const handleUndo = () => {
    undo.mutate(undefined, {
      onSuccess: () => setResult(null),
    })
  }

  return (
    <section className="mx-auto w-full max-w-3xl px-8 py-12">
      {showConfirm && preview && (
        <ConfirmOrganizeDialog
          planned={preview.planned}
          onConfirm={handleExecute}
          onCancel={() => setShowConfirm(false)}
          isPending={execute.isPending}
        />
      )}

      <button
        onClick={back}
        className="mb-6 flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600"
      >
        ← Back
      </button>

      <div className="mb-6">
        <h2 className="text-lg font-semibold tracking-tight">Organize by people</h2>
        <p className="mt-1 text-sm text-zinc-500">
          Move your media into <code className="rounded bg-zinc-100 px-1 text-xs">People/</code>{' '}
          subfolders, one folder per person.
        </p>
      </div>

      {result && (
        <ResultBanner report={result} onDismiss={() => { setResult(null); setShowRescanNotice(false) }} />
      )}

      {showRescanNotice && (
        <div className="mb-4 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
          <svg className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>
          <div className="flex-1">
            <p className="text-sm font-medium text-amber-800">Run a face scan to update file locations</p>
            <p className="mt-0.5 text-xs text-amber-700">
              Files were moved on disk. The database still points to old paths — organizing again before rescanning will fail for already-moved files.
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

      {undo.isError && (
        <p className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {undo.error.message}
        </p>
      )}

      {/* Plan summary */}
      <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
        <h3 className="mb-4 text-sm font-semibold">Plan</h3>

        {isLoading && <p className="text-sm text-zinc-400">Loading plan…</p>}

        {isError && (
          <p className="text-sm text-zinc-400">
            No face scan found. Run a face scan first to organize by people.
          </p>
        )}

        {preview && (
          <>
            <p className="mb-4 text-sm text-zinc-700">
              <span className="font-medium">{preview.planned}</span> files will be organized
              into <span className="font-medium">{Object.keys(preview.by_person).length}</span>{' '}
              folders.
            </p>

            {/* Per-person breakdown */}
            <div className="mb-4 space-y-1.5">
              {Object.entries(preview.by_person)
                .sort(([, a], [, b]) => b - a)
                .map(([name, count]) => (
                  <div key={name} className="flex items-center justify-between">
                    <span
                      className={`text-sm ${
                        name.startsWith('_') ? 'text-zinc-400' : 'text-zinc-700'
                      }`}
                    >
                      {name.startsWith('_') ? name : `People/${name}`}
                    </span>
                    <span className="text-xs text-zinc-400">{count} file{count !== 1 ? 's' : ''}</span>
                  </div>
                ))}
            </div>

            {/* Toggle file list */}
            <button
              onClick={() => setShowMoves((v) => !v)}
              className="mb-4 text-xs text-zinc-400 underline hover:text-zinc-600"
            >
              {showMoves ? 'Hide file list' : `Show all ${preview.planned} files`}
            </button>

            {showMoves && (
              <div className="mb-4 max-h-64 overflow-y-auto rounded-xl border border-zinc-100 bg-zinc-50 p-3">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-zinc-400">
                      <th className="pb-1 pr-4 font-normal">Source</th>
                      <th className="pb-1 font-normal">Destination folder</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.moves.map((m, i) => (
                      <tr key={i} className="border-t border-zinc-100">
                        <td className="py-1 pr-4 text-zinc-600 truncate max-w-[200px]">
                          {m.source_rel.split('/').pop()}
                        </td>
                        <td className="py-1 text-zinc-500">{m.dest_folder_rel}/</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Actions */}
            <div className="flex flex-wrap gap-2">
              <button
                onClick={handleDryRun}
                disabled={execute.isPending}
                className="rounded-lg border border-zinc-200 px-4 py-2 text-sm text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
              >
                {execute.isPending && execute.variables?.dryRun === true ? 'Running…' : 'Dry run'}
              </button>
              <button
                onClick={() => setShowConfirm(true)}
                disabled={execute.isPending || preview.planned === 0}
                className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
              >
                Organize {preview.planned} files
              </button>
            </div>
          </>
        )}
      </div>

      {/* Undo section */}
      {lastAction && (
        <div className="mt-4 rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Previous organize action</p>
              <p className="mt-0.5 text-xs text-zinc-500">
                {lastAction.handled} files moved on{' '}
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
          {undo.isError && (
            <p className="mt-2 text-xs text-red-600">{undo.error.message}</p>
          )}
        </div>
      )}

      {/* Audit log link */}
      {audit && audit.length > 0 && (
        <div className="mt-3 text-right">
          <button
            onClick={() => navigate({ name: 'audit', libraryId } as View)}
            className="text-xs text-zinc-400 underline hover:text-zinc-600"
          >
            View full organize history ({audit.length} action{audit.length !== 1 ? 's' : ''}) →
          </button>
        </div>
      )}
    </section>
  )
}
