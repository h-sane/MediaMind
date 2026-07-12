import { ArrowLeft, ArrowRight, ArrowUp, RotateCw } from 'lucide-react'
import { isRealFolder, useExplorerStore } from '../../stores/explorer'

interface Props {
  onRefresh: () => void
  refreshing: boolean
}

export function NavButtons({ onRefresh, refreshing }: Props): React.JSX.Element {
  const history = useExplorerStore((s) => s.history)
  const future = useExplorerStore((s) => s.future)
  const currentPath = useExplorerStore((s) => s.currentPath)
  const back = useExplorerStore((s) => s.back)
  const forward = useExplorerStore((s) => s.forward)
  const up = useExplorerStore((s) => s.up)

  const btn =
    'flex h-7 w-7 items-center justify-center rounded-md text-zinc-600 transition hover:bg-zinc-100 disabled:pointer-events-none disabled:opacity-30'

  return (
    <div className="flex items-center gap-0.5">
      <button className={btn} disabled={history.length === 0} onClick={back} aria-label="Back">
        <ArrowLeft className="h-4 w-4" />
      </button>
      <button className={btn} disabled={future.length === 0} onClick={forward} aria-label="Forward">
        <ArrowRight className="h-4 w-4" />
      </button>
      <button className={btn} disabled={!isRealFolder(currentPath)} onClick={up} aria-label="Up one level">
        <ArrowUp className="h-4 w-4" />
      </button>
      <button className={btn} onClick={onRefresh} aria-label="Refresh">
        <RotateCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
      </button>
    </div>
  )
}
