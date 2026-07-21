import { FaceThumbnail } from '../../../components/FaceThumbnail'
import type { MergeSuggestion, Person } from '../../../api/client'

interface Props {
  libraryId: string
  suggestions: MergeSuggestion[]
  persons: Person[]
  dismissed: Set<string>
  busyKey: string | null
  onMerge: (sourceId: number, targetId: number) => void
  onDismiss: (key: string) => void
}

export const pairKey = (a: number, b: number): string =>
  a < b ? `${a}-${b}` : `${b}-${a}`

// The person that survives a merge keeps the folder identity: prefer a named
// person over an unnamed one, then the one with more photos, then higher id.
function survivor(a: Person, b: Person): [Person, Person] {
  const aScore = (a.name ? 1_000_000 : 0) + a.media_count
  const bScore = (b.name ? 1_000_000 : 0) + b.media_count
  if (aScore !== bScore) return aScore > bScore ? [a, b] : [b, a]
  return a.id > b.id ? [a, b] : [b, a]
}

/** Proactive "are these the same person?" suggestions (Phase 5): pairs the
 * split-biased clustering left separate but whose faces look alike. One-click
 * merge makes over-splitting cheap to fix; "Not the same" hides the pair for
 * this session. */
export function MergeSuggestionStrip({
  libraryId,
  suggestions,
  persons,
  dismissed,
  busyKey,
  onMerge,
  onDismiss
}: Props): React.JSX.Element | null {
  const byId = new Map(persons.map((p) => [p.id, p]))
  const visible = suggestions
    .map((s) => ({ s, a: byId.get(s.person_a), b: byId.get(s.person_b) }))
    .filter((x): x is { s: MergeSuggestion; a: Person; b: Person } => !!x.a && !!x.b)
    .filter((x) => !dismissed.has(pairKey(x.a.id, x.b.id)))

  if (visible.length === 0) return null

  return (
    <div className="mb-6">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-400">
        Are these the same person?
      </p>
      <div className="flex flex-wrap gap-3">
        {visible.map(({ s, a, b }) => {
          const key = pairKey(a.id, b.id)
          const [keep, absorb] = survivor(a, b)
          const busy = busyKey === key
          const name = (p: Person): string => p.name ?? p.auto_label
          return (
            <div
              key={key}
              className="flex items-center gap-3 rounded-xl border border-indigo-200 bg-indigo-50/40 px-3 py-2"
            >
              <div className="flex items-center gap-1.5">
                {[a, b].map((p) =>
                  p.sample_face_ids.length > 0 ? (
                    <FaceThumbnail
                      key={p.id}
                      libraryId={libraryId}
                      faceId={p.sample_face_ids[0]}
                      size={44}
                      className="ring-1 ring-white"
                    />
                  ) : (
                    <div key={p.id} className="h-11 w-11 rounded-full bg-zinc-100" />
                  )
                )}
              </div>
              <span className="text-xs text-zinc-500">
                {Math.round(s.similarity * 100)}% alike
              </span>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => onMerge(absorb.id, keep.id)}
                  disabled={busy}
                  title={`Merge into ${name(keep)}`}
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-indigo-500 disabled:opacity-50"
                >
                  {busy ? 'Merging…' : `Merge → ${name(keep)}`}
                </button>
                <button
                  onClick={() => onDismiss(key)}
                  disabled={busy}
                  title="Not the same person"
                  className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 disabled:opacity-50"
                >
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
