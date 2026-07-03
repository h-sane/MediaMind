import { useState } from 'react'
import { useAppStore } from '../stores/app'
import { usePendingMatches, useDecidePending, useFaceThumbnailUrl } from '../api/hooks'
import type { PendingMatch } from '../api/client'

interface Props {
  libraryId: string
}

function PendingRow({
  match,
  libraryId,
  onDecide,
  deciding,
}: {
  match: PendingMatch
  libraryId: string
  onDecide: (id: number, decision: 'confirmed' | 'rejected') => void
  deciding: boolean
}): React.JSX.Element {
  const thumbUrl = useFaceThumbnailUrl(libraryId, match.face_id, 96)
  const pct = Math.round(match.confidence * 100)

  return (
    <div className="flex items-center gap-4 rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
      {/* Face thumbnail */}
      <div className="h-16 w-16 flex-shrink-0 overflow-hidden rounded-full bg-zinc-100">
        {thumbUrl ? (
          <img src={thumbUrl} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <svg className="h-7 w-7 text-zinc-300" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z" />
            </svg>
          </div>
        )}
      </div>

      {/* Suggestion */}
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-zinc-800">
          Assign to <span className="text-zinc-900">{match.person_name}</span>?
        </p>
        <p className="mt-0.5 text-xs text-zinc-400">
          {pct}% confidence
        </p>
      </div>

      {/* Actions */}
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

export function PendingReview({ libraryId }: Props): React.JSX.Element {
  const back = useAppStore((s) => s.back)
  const { data: matches, isLoading } = usePendingMatches(libraryId)
  const decide = useDecidePending(libraryId)
  const [decided, setDecided] = useState<Set<number>>(new Set())

  const pending = matches?.filter((m: PendingMatch) => !decided.has(m.id)) ?? []

  const onDecide = (pendingId: number, decision: 'confirmed' | 'rejected') => {
    decide.mutate([{ pending_id: pendingId, decision }], {
      onSuccess: () => {
        setDecided((prev) => new Set([...prev, pendingId]))
      },
    })
  }

  const approveAll = () => {
    if (!pending.length) return
    const decisions = pending.map((m: PendingMatch) => ({
      pending_id: m.id,
      decision: 'confirmed' as const,
    }))
    decide.mutate(decisions, {
      onSuccess: () => {
        setDecided((prev) => new Set([...prev, ...pending.map((m: PendingMatch) => m.id)]))
      },
    })
  }

  const rejectAll = () => {
    if (!pending.length) return
    const decisions = pending.map((m: PendingMatch) => ({
      pending_id: m.id,
      decision: 'rejected' as const,
    }))
    decide.mutate(decisions, {
      onSuccess: () => {
        setDecided((prev) => new Set([...prev, ...pending.map((m: PendingMatch) => m.id)]))
      },
    })
  }

  return (
    <section className="mx-auto w-full max-w-3xl px-8 py-12">
      <button
        onClick={back}
        className="mb-6 flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600"
      >
        ← Back
      </button>

      <div className="mb-6 flex items-end justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Review pending matches</h2>
          <p className="mt-1 text-sm text-zinc-500">
            Confirm or reject suggested face assignments from the latest scan.
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
            Pending matches appear when a named person is recognised in a newly-scanned file.
          </p>
        </div>
      )}

      <div className="space-y-3">
        {pending.map((m: PendingMatch) => (
          <PendingRow
            key={m.id}
            match={m}
            libraryId={libraryId}
            onDecide={onDecide}
            deciding={decide.isPending}
          />
        ))}
      </div>
    </section>
  )
}
