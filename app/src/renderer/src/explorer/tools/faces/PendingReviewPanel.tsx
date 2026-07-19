import { useState } from 'react'
import { ArrowLeft } from 'lucide-react'
import { usePendingMatches, useDecidePending } from '../../../api/hooks'
import { FaceThumbnail } from '../../../components/FaceThumbnail'
import type { PendingMatch } from '../../../api/client'

interface Props {
  libraryId: string
  onBack: () => void
}

function PendingRow({
  match,
  libraryId,
  onDecide,
  deciding
}: {
  match: PendingMatch
  libraryId: string
  onDecide: (id: number, decision: 'confirmed' | 'rejected') => void
  deciding: boolean
}): React.JSX.Element {
  const pct = Math.round(match.confidence * 100)

  return (
    <div className="flex items-center gap-4 rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
      <FaceThumbnail libraryId={libraryId} faceId={match.face_id} size={64} />

      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-zinc-800">
          Assign to <span className="text-zinc-900">{match.person_name}</span>?
        </p>
        <p className="mt-0.5 text-xs text-zinc-400">{pct}% confidence</p>
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => onDecide(match.id, 'rejected')}
          disabled={deciding}
          className="rounded-lg border border-zinc-200 px-3 py-1.5 text-sm text-zinc-600 transition hover:bg-zinc-50 disabled:opacity-50"
        >
          Reject
        </button>
        <button
          onClick={() => onDecide(match.id, 'confirmed')}
          disabled={deciding}
          className="rounded-lg bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-zinc-700 disabled:opacity-50"
        >
          Confirm
        </button>
      </div>
    </div>
  )
}

/** New-photos-to-confirm review — every new file matched to a named person
 * lands here first (`organize_plan.py` excludes undecided pending matches
 * from the plan entirely), so this is what keeps F1's "silently moved to
 * _noise" scenario from happening: nothing routes anywhere until reviewed
 * here. */
export function PendingReviewPanel({ libraryId, onBack }: Props): React.JSX.Element {
  const { data: matches, isLoading } = usePendingMatches(libraryId)
  const decide = useDecidePending(libraryId)
  const [decided, setDecided] = useState<Set<number>>(new Set())

  const pending = matches?.filter((m) => !decided.has(m.id)) ?? []

  const onDecide = (pendingId: number, decision: 'confirmed' | 'rejected') => {
    decide.mutate([{ pending_id: pendingId, decision }], {
      onSuccess: () => setDecided((prev) => new Set([...prev, pendingId]))
    })
  }

  const approveAll = () => {
    if (!pending.length) return
    const decisions = pending.map((m) => ({ pending_id: m.id, decision: 'confirmed' as const }))
    decide.mutate(decisions, {
      onSuccess: () => setDecided((prev) => new Set([...prev, ...pending.map((m) => m.id)]))
    })
  }

  const rejectAll = () => {
    if (!pending.length) return
    const decisions = pending.map((m) => ({ pending_id: m.id, decision: 'rejected' as const }))
    decide.mutate(decisions, {
      onSuccess: () => setDecided((prev) => new Set([...prev, ...pending.map((m) => m.id)]))
    })
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <button onClick={onBack} className="mb-6 flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to people
      </button>

      <div className="mb-6 flex items-end justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">New photos to confirm</h2>
          <p className="mt-1 text-sm text-zinc-500">
            Confirm or reject suggested face matches from the latest scan before they're organized.
          </p>
        </div>
        {pending.length > 1 && (
          <div className="flex gap-2">
            <button
              onClick={rejectAll}
              disabled={decide.isPending}
              className="rounded-lg border border-zinc-200 px-3 py-2 text-sm text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
            >
              Reject all
            </button>
            <button
              onClick={approveAll}
              disabled={decide.isPending}
              className="rounded-lg bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
            >
              Approve all
            </button>
          </div>
        )}
      </div>

      {decide.isError && (
        <p className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {decide.error.message}
        </p>
      )}

      {isLoading && <p className="text-sm text-zinc-400">Loading…</p>}

      {!isLoading && pending.length === 0 && (
        <div className="rounded-2xl border border-dashed border-zinc-300 py-16 text-center">
          <p className="text-sm text-zinc-500">No pending matches.</p>
          <p className="mt-1 text-xs text-zinc-400">
            Pending matches appear when a named person is recognized in a newly-scanned file.
          </p>
        </div>
      )}

      <div className="space-y-3">
        {pending.map((m) => (
          <PendingRow key={m.id} match={m} libraryId={libraryId} onDecide={onDecide} deciding={decide.isPending} />
        ))}
      </div>
    </div>
  )
}
