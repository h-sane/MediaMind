import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { FaceThumbnail } from '../../../components/FaceThumbnail'
import { FullscreenModalShell } from '../shared/FullscreenModalShell'
import type { MergeSuggestion, Person } from '../../../api/client'

export const pairKey = (a: number, b: number): string =>
  a < b ? `${a}-${b}` : `${b}-${a}`

// The person that survives a merge keeps the folder identity: prefer a named
// person over an unnamed one, then the one with more photos, then higher id.
// (Kept identical to the old inline strip so merge direction is unchanged.)
export function survivor(a: Person, b: Person): [Person, Person] {
  const aScore = (a.name ? 1_000_000 : 0) + a.media_count
  const bScore = (b.name ? 1_000_000 : 0) + b.media_count
  if (aScore !== bScore) return aScore > bScore ? [a, b] : [b, a]
  return a.id > b.id ? [a, b] : [b, a]
}

interface Pair {
  s: MergeSuggestion
  a: Person
  b: Person
}

export function visibleMergePairs(
  suggestions: MergeSuggestion[],
  persons: Person[],
  dismissed: Set<string>
): Pair[] {
  const byId = new Map(persons.map((p) => [p.id, p]))
  return suggestions
    .map((s) => ({ s, a: byId.get(s.person_a), b: byId.get(s.person_b) }))
    .filter((x): x is Pair => !!x.a && !!x.b)
    .filter((x) => !dismissed.has(pairKey(x.a.id, x.b.id)))
}

interface Props {
  libraryId: string
  suggestions: MergeSuggestion[]
  persons: Person[]
  dismissed: Set<string>
  onMerge: (sourceId: number, targetId: number) => void
  onDismiss: (personAId: number, personBId: number) => void
  onClose: () => void
}

function personLabel(p: Person): string {
  return p.name ?? p.auto_label
}

/** Full-screen, one-at-a-time "are these the same person?" review — replaces
 * the cramped tile strip whose faces were too small to judge. Both faces are
 * shown large; deciding advances to the next pair, so the user sweeps the whole
 * queue (Google-Photos style) without hunting tiny buttons. The queue is frozen
 * on open and walked by index, so a merge/dismiss that reshapes the underlying
 * data doesn't shift the cards under the user. */
export function MergeReviewModal({
  libraryId,
  suggestions,
  persons,
  dismissed,
  onMerge,
  onDismiss,
  onClose
}: Props): React.JSX.Element {
  // Snapshot the queue once — later merges/dismissals mutate `persons`/
  // `dismissed`, but we walk our own frozen list by index.
  const [queue] = useState<Pair[]>(() => visibleMergePairs(suggestions, persons, dismissed))
  const [index, setIndex] = useState(0)

  const done = index >= queue.length
  const current = done ? null : queue[index]

  const advance = (): void => setIndex((i) => i + 1)

  const decideMerge = (): void => {
    if (!current) return
    const [keep, absorb] = survivor(current.a, current.b)
    onMerge(absorb.id, keep.id)
    advance()
  }

  const decideNotSame = (): void => {
    if (!current) return
    onDismiss(current.a.id, current.b.id)
    advance()
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent): void {
      if (done) return
      if (e.key === 'ArrowRight') advance()
      else if (e.key === 'ArrowLeft') setIndex((i) => Math.max(0, i - 1))
      else if (e.key === 'y' || e.key === 'Y' || e.key === 'Enter') decideMerge()
      else if (e.key === 'n' || e.key === 'N') decideNotSame()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, done])

  const keep = current ? survivor(current.a, current.b)[0] : null

  return (
    <FullscreenModalShell
      onClose={onClose}
      headerLeft={
        <div>
          <h2 className="text-sm font-semibold text-white">Are these the same person?</h2>
          <p className="text-xs text-zinc-400">
            {done ? 'All reviewed' : `${index + 1} of ${queue.length}`}
          </p>
        </div>
      }
    >
      {current ? (
        <div className="mx-auto flex h-full max-w-4xl flex-col items-center justify-center gap-10 px-6 py-10">
          <div className="flex items-center gap-8 sm:gap-16">
            {[current.a, current.b].map((p) => (
              <div key={p.id} className="flex flex-col items-center gap-3">
                <FaceThumbnail
                  libraryId={libraryId}
                  faceId={p.sample_face_ids[0] ?? 0}
                  size={220}
                  className="ring-2 ring-zinc-700"
                />
                <p className="max-w-[220px] truncate text-sm font-medium text-white" title={personLabel(p)}>
                  {personLabel(p)}
                </p>
                <p className="text-xs text-zinc-400">
                  {p.media_count} photo{p.media_count === 1 ? '' : 's'}
                </p>
              </div>
            ))}
          </div>

          <p className="text-sm text-zinc-400">
            {Math.round(current.s.similarity * 100)}% alike
          </p>

          <div className="flex items-center gap-3">
            <button
              onClick={decideNotSame}
              className="rounded-xl border border-zinc-600 px-6 py-3 text-sm font-medium text-zinc-200 transition hover:bg-zinc-800"
            >
              Not the same
            </button>
            <button
              onClick={advance}
              className="rounded-xl border border-zinc-700 px-4 py-3 text-sm text-zinc-400 transition hover:bg-zinc-800"
              title="Decide later (→)"
            >
              Skip
            </button>
            <button
              onClick={decideMerge}
              className="rounded-xl bg-indigo-600 px-6 py-3 text-sm font-medium text-white transition hover:bg-indigo-500"
            >
              Same person → merge into {keep ? personLabel(keep) : ''}
            </button>
          </div>

          <div className="flex items-center gap-6 text-zinc-500">
            <button
              onClick={() => setIndex((i) => Math.max(0, i - 1))}
              disabled={index === 0}
              className="rounded-full p-2 hover:bg-zinc-800 disabled:opacity-30"
              title="Previous (←)"
            >
              <ChevronLeft className="h-6 w-6" />
            </button>
            <button
              onClick={advance}
              className="rounded-full p-2 hover:bg-zinc-800"
              title="Next (→)"
            >
              <ChevronRight className="h-6 w-6" />
            </button>
          </div>
        </div>
      ) : (
        <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
          <p className="text-lg font-medium text-white">All caught up</p>
          <p className="text-sm text-zinc-400">You&apos;ve reviewed every suggestion.</p>
          <button
            onClick={onClose}
            className="mt-2 rounded-xl bg-zinc-100 px-6 py-2.5 text-sm font-medium text-zinc-900 hover:bg-white"
          >
            Done
          </button>
        </div>
      )}
    </FullscreenModalShell>
  )
}
