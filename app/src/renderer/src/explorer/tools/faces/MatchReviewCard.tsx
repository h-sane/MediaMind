import { Check, X } from 'lucide-react'
import { FileThumbnail } from '../../../components/FileThumbnail'

function fileName(path: string): string {
  const idx = path.lastIndexOf('/')
  return idx === -1 ? path : path.slice(idx + 1)
}

interface Props {
  libraryId: string
  path: string
  kind: string
  onOpenSingle: () => void
  /** Highlight color for the card border/badge — green for a positive
   * outcome (confirmed / will move), red for a negative one (rejected /
   * excluded), amber for "redirected elsewhere", grey for untouched. */
  status: 'positive' | 'negative' | 'redirected' | 'neutral'
  statusLabel: string
  reassignTo?: string
  actions: React.ReactNode
}

const STATUS_STYLES: Record<Props['status'], string> = {
  positive: 'border-emerald-500/70 bg-emerald-950/20',
  negative: 'border-red-500/60 bg-red-950/20',
  redirected: 'border-amber-500/60 bg-amber-950/20',
  neutral: 'border-zinc-700 bg-zinc-900'
}

/** One file tile in the pre-accept match review modal — used for both "in
 * the folder, not yet matched" and "this person's other photos" sections. */
export function MatchReviewCard({
  libraryId,
  path,
  kind,
  onOpenSingle,
  status,
  statusLabel,
  reassignTo,
  actions
}: Props): React.JSX.Element {
  return (
    <div className={`flex flex-col overflow-hidden rounded-2xl border-2 transition ${STATUS_STYLES[status]}`}>
      <button
        type="button"
        onDoubleClick={onOpenSingle}
        title="Double-click for full screen"
        className="relative aspect-video w-full cursor-pointer bg-black"
      >
        <FileThumbnail libraryId={libraryId} path={path} kind={kind} size={1024} fit="contain" className="h-full w-full" />
        {status === 'positive' && (
          <span className="absolute left-2 top-2 flex h-6 w-6 items-center justify-center rounded-full border-2 border-emerald-500 bg-emerald-500 text-white">
            <Check className="h-3.5 w-3.5" />
          </span>
        )}
        {status === 'negative' && (
          <span className="absolute left-2 top-2 flex h-6 w-6 items-center justify-center rounded-full border-2 border-red-500 bg-red-500 text-white">
            <X className="h-3.5 w-3.5" />
          </span>
        )}
      </button>

      <div className="px-3 py-2">
        <p className="truncate text-sm font-medium text-zinc-100" title={path}>
          {fileName(path)}
        </p>
        <p className="text-[11px] text-zinc-400">
          {statusLabel}
          {reassignTo && <span className="text-amber-400"> &rarr; {reassignTo}</span>}
        </p>
      </div>

      <div className="border-t border-zinc-800 p-3">{actions}</div>
    </div>
  )
}
