import { useAppStore } from '../stores/app'
import { useOrganizeAudit } from '../api/hooks'
import type { OrganizeAction } from '../api/client'

interface Props {
  libraryId: string
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function StatusBadge({ action }: { action: OrganizeAction }): React.JSX.Element {
  if (action.undone) {
    return (
      <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-500">undone</span>
    )
  }
  if (action.dry_run) {
    return (
      <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-600">dry run</span>
    )
  }
  if (action.ok) {
    return (
      <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700">ok</span>
    )
  }
  return (
    <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs text-amber-700">partial</span>
  )
}

function KindLabel({ kind }: { kind: string }): React.JSX.Element {
  const label = kind === 'undo' ? 'Undo' : kind === 'organize-by-person' ? 'Organize' : kind
  return <span className="font-medium">{label}</span>
}

export function AuditScreen({ libraryId }: Props): React.JSX.Element {
  const back = useAppStore((s) => s.back)
  const { data: actions, isLoading, isError } = useOrganizeAudit(libraryId)

  return (
    <section className="mx-auto w-full max-w-3xl px-8 py-12">
      <div className="mb-2 flex items-center gap-2">
        <button
          onClick={back}
          className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600"
        >
          ← Back
        </button>
      </div>

      <div className="mb-6">
        <h2 className="text-lg font-semibold tracking-tight">Organize history</h2>
        <p className="mt-1 text-sm text-zinc-500">
          All organize and undo actions for this library, newest first.
        </p>
      </div>

      {isLoading && <p className="text-sm text-zinc-400">Loading…</p>}

      {isError && (
        <p className="text-sm text-red-600">Could not load audit log.</p>
      )}

      {!isLoading && actions && actions.length === 0 && (
        <div className="rounded-2xl border border-dashed border-zinc-300 py-16 text-center">
          <p className="text-sm text-zinc-500">No organize actions yet.</p>
          <p className="mt-1 text-xs text-zinc-400">
            Use the Organize screen to move files by person.
          </p>
        </div>
      )}

      {actions && actions.length > 0 && (
        <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-100 bg-zinc-50 text-left text-xs text-zinc-500">
                <th className="px-4 py-3">Action</th>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3 text-right">Planned</th>
                <th className="px-4 py-3 text-right">Handled</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {actions.map((action: OrganizeAction) => (
                <tr key={action.id} className="transition hover:bg-zinc-50">
                  <td className="px-4 py-3">
                    <KindLabel kind={action.kind} />
                  </td>
                  <td className="px-4 py-3 text-zinc-500">
                    {formatDate(action.created_at)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-zinc-600">
                    {action.planned}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-zinc-600">
                    {action.handled}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge action={action} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
