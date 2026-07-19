import { Users } from 'lucide-react'
import type { BindingSuggestion } from '../../../api/client'

interface Props {
  suggestions: BindingSuggestion[]
  onReview: (suggestion: BindingSuggestion) => void
  onDismiss: (suggestion: BindingSuggestion) => void
}

/** Group-of-people folder matches (e.g. a family photo folder) — these don't
 * map to a single person tile, so they get their own compact strip above the
 * grid instead of living in the (now person-tile-driven) suggestion flow.
 * Accepting always goes through the review modal (onReview) — there is no
 * one-click accept, so a merge is never applied without the user seeing
 * what will move. */
export function GroupSuggestionStrip({ suggestions, onReview, onDismiss }: Props): React.JSX.Element | null {
  if (suggestions.length === 0) return null

  return (
    <div className="mb-6">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-zinc-400">
        <Users className="h-3 w-3" /> Group folders
      </p>
      <div className="space-y-2">
        {suggestions.map((s) => {
          const outlierCount = s.outlier_file_ids.length
          return (
            <div key={s.id} className="rounded-2xl border border-emerald-200 bg-emerald-50/40 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-zinc-800">{s.folder_rel}</p>
                  <p className="mt-1 text-xs text-zinc-500">
                    {s.person_names.join(', ')} · {Math.round(s.coverage * 100)}% match
                    {outlierCount > 0 &&
                      ` · ${outlierCount} outlier ${outlierCount === 1 ? 'file' : 'files'}`}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <button
                    onClick={() => onDismiss(s)}
                    className="rounded-lg border border-zinc-200 px-3 py-1.5 text-xs text-zinc-600 transition hover:bg-zinc-50"
                  >
                    Dismiss
                  </button>
                  <button
                    onClick={() => onReview(s)}
                    className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-500"
                  >
                    Review
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
