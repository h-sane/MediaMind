import { useEffect, useRef, useState } from 'react'
import { Star, X } from 'lucide-react'
import { useQuickAccess, useUnpinQuickAccess, usePinQuickAccess, useReorderQuickAccess } from '../../api/hooks'
import { useExplorerStore } from '../../stores/explorer'
import { makePinDropTarget } from '../dnd/entryDrag'
import { useFolderDropTarget } from '../dnd/useFolderDropTarget'
import type { QuickAccessEntry } from '../../api/client'

const PIN_REORDER_MIME = 'text/mediamind-pin'

interface PinRowProps {
  pin: QuickAccessEntry
  isCurrent: boolean
  onNavigate: (path: string) => void
  onUnpin: (path: string) => void
  onReorder: (draggedPath: string, beforePath: string) => void
}

/** One pinned folder — a drop target for moving/copying into it, same as
 * any folder in the tree or content pane, *and* a native-HTML5-drag reorder
 * source/target (a small closed set of known rows doesn't need the app's
 * richer entry-drag machinery, same idiom as `DetailsViewHeader.tsx`'s
 * column reorder). The two drag kinds don't conflict: a plain native drag
 * carries no pragmatic-drag-and-drop entry data, so the folder-drop target's
 * `canDrop` check ignores it, and vice versa a real entry drag never carries
 * the `PIN_REORDER_MIME` type this row's own reorder handlers look for. */
function PinRow({ pin, isCurrent, onNavigate, onUnpin, onReorder }: PinRowProps): React.JSX.Element {
  const { ref, isOver } = useFolderDropTarget(pin.path)
  const [reorderOver, setReorderOver] = useState(false)

  return (
    <div
      ref={ref}
      draggable
      onDragStart={(e) => e.dataTransfer.setData(PIN_REORDER_MIME, pin.path)}
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes(PIN_REORDER_MIME)) {
          e.preventDefault()
          setReorderOver(true)
        }
      }}
      onDragLeave={() => setReorderOver(false)}
      onDrop={(e) => {
        setReorderOver(false)
        const draggedPath = e.dataTransfer.getData(PIN_REORDER_MIME)
        if (draggedPath && draggedPath !== pin.path) onReorder(draggedPath, pin.path)
      }}
      className={`group flex items-center gap-1.5 py-1 pl-3 pr-2 text-sm ${
        isOver || reorderOver
          ? 'bg-blue-100 ring-1 ring-inset ring-blue-400'
          : isCurrent
            ? 'bg-blue-50 text-blue-700'
            : 'text-zinc-700 hover:bg-zinc-100'
      }`}
    >
      <button
        type="button"
        onClick={() => onNavigate(pin.path)}
        className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
      >
        <Star className="h-4 w-4 shrink-0 text-amber-400" />
        <span className="truncate">{pin.name}</span>
      </button>
      <button
        type="button"
        onClick={() => onUnpin(pin.path)}
        aria-label={`Remove ${pin.name} from Quick access`}
        title="Remove from Quick access"
        className="hidden h-4 w-4 shrink-0 items-center justify-center rounded-full text-zinc-400 hover:bg-zinc-200 hover:text-zinc-700 group-hover:flex"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  )
}

/** Manually pinned folders, above the live folder tree. Pin/unpin happens
 * from the content pane's right-click menu (see ContextMenu.tsx) or by
 * dragging a folder onto the "Quick access" header below; the list order
 * itself is drag-reorderable (Phase N) — this list otherwise only navigates
 * and offers a hover "x" to unpin, mirroring Explorer's own Quick Access
 * section (minus the auto "Frequent folders", out of scope here). */
export function QuickAccess(): React.JSX.Element | null {
  const { data } = useQuickAccess()
  const navigate = useExplorerStore((s) => s.navigate)
  const currentPath = useExplorerStore((s) => s.currentPath)
  const unpin = useUnpinQuickAccess()
  const pin = usePinQuickAccess()
  const reorder = useReorderQuickAccess()
  const headerRef = useRef<HTMLDivElement>(null)
  const [headerOver, setHeaderOver] = useState(false)

  useEffect(() => {
    const el = headerRef.current
    if (!el) return
    return makePinDropTarget(el, { onPin: (path) => pin.mutate(path), onHoverChange: setHeaderOver })
  }, [pin])

  const pins = data?.pins ?? []

  // Same before-anchored insert `detailsColumns.ts::reorder` uses for its
  // own native-drag column reorder — drop onto a row inserts the dragged pin
  // immediately before it.
  function onReorder(draggedPath: string, beforePath: string): void {
    const rest = pins.map((p) => p.path).filter((p) => p !== draggedPath)
    const idx = rest.indexOf(beforePath)
    const next = idx === -1 ? [...rest, draggedPath] : [...rest.slice(0, idx), draggedPath, ...rest.slice(idx)]
    reorder.mutate(next)
  }

  return (
    <div className="border-b border-zinc-200 py-2">
      <div
        ref={headerRef}
        className={`px-3 pb-1 text-xs font-medium text-zinc-400 ${headerOver ? 'bg-blue-100 text-blue-600' : ''}`}
      >
        Quick access
      </div>
      {pins.map((p) => (
        <PinRow
          key={p.path}
          pin={p}
          isCurrent={p.path === currentPath}
          onNavigate={navigate}
          onUnpin={(path) => unpin.mutate(path)}
          onReorder={onReorder}
        />
      ))}
    </div>
  )
}
