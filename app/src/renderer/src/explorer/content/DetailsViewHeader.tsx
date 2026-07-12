import { useCallback, useState } from 'react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { Check, Columns3 } from 'lucide-react'
import { COLUMN_LABELS, useDetailsColumnsStore, type DetailsColumnId } from '../../stores/detailsColumns'
import type { SortDir, SortKey } from '../../stores/explorer'
import { ChooseColumnsDialog } from './ChooseColumnsDialog'

/** Pulled out of `DetailsView.tsx` (column-header concerns only — resize,
 * reorder, sort, the column chooser) to keep that file's own row-rendering,
 * grouping and marquee-select logic from growing past the project's
 * ~300-400-line smell threshold. */

const COLUMN_SORT_KEY: Record<DetailsColumnId, SortKey> = {
  date: 'date',
  type: 'type',
  size: 'size',
  created: 'created',
  accessed: 'accessed',
  attributes: 'attributes'
}
const separatorClass = 'my-1 h-px bg-zinc-200'

/** Drag-to-resize the column to the left of this handle. Raw mousemove
 * tracking (not native HTML5 DnD, which doesn't give smooth positional
 * updates) — same idiom as the content views' marquee-select drag. */
function ResizeHandle({ columnId }: { columnId: 'name' | DetailsColumnId }): React.JSX.Element {
  const widths = useDetailsColumnsStore((s) => s.widths)
  const setWidth = useDetailsColumnsStore((s) => s.setWidth)

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      e.stopPropagation()
      const startX = e.clientX
      const startWidth = widths[columnId]
      function onMove(ev: MouseEvent): void {
        setWidth(columnId, startWidth + (ev.clientX - startX))
      }
      function onUp(): void {
        window.removeEventListener('mousemove', onMove)
        window.removeEventListener('mouseup', onUp)
      }
      window.addEventListener('mousemove', onMove)
      window.addEventListener('mouseup', onUp)
    },
    [columnId, widths, setWidth]
  )

  return (
    <div
      draggable={false}
      onMouseDown={onMouseDown}
      className="absolute right-0 top-0 h-full w-1.5 shrink-0 cursor-col-resize hover:bg-blue-300"
    />
  )
}

interface HeaderCellProps {
  id: DetailsColumnId
  width: number
  sortKey: SortKey
  sortDir: SortDir
  onSort: (key: SortKey) => void
  onReorder: (id: DetailsColumnId, beforeId: DetailsColumnId | null) => void
}

/** A reorderable, resizable, sortable header cell for one of the non-Name
 * columns. Native HTML5 drag for reordering — a small closed set of known
 * targets doesn't need the app's richer entry-drag machinery. */
function HeaderCell({ id, width, sortKey, sortDir, onSort, onReorder }: HeaderCellProps): React.JSX.Element {
  const [dragOver, setDragOver] = useState(false)

  return (
    <div
      draggable
      onDragStart={(e) => e.dataTransfer.setData('text/mediamind-column', id)}
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes('text/mediamind-column')) {
          e.preventDefault()
          setDragOver(true)
        }
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
        const draggedId = e.dataTransfer.getData('text/mediamind-column') as DetailsColumnId
        if (draggedId && draggedId !== id) onReorder(draggedId, id)
      }}
      onClick={() => onSort(COLUMN_SORT_KEY[id])}
      style={{ width }}
      className={`relative shrink-0 cursor-pointer select-none px-3 py-1.5 text-left hover:bg-zinc-100 ${
        dragOver ? 'bg-blue-100' : ''
      }`}
    >
      {COLUMN_LABELS[id]}
      {sortKey === COLUMN_SORT_KEY[id] && (sortDir === 'asc' ? ' ▲' : ' ▼')}
      <ResizeHandle columnId={id} />
    </div>
  )
}

function ColumnChooser(): React.JSX.Element {
  const hidden = useDetailsColumnsStore((s) => s.hidden)
  const toggleHidden = useDetailsColumnsStore((s) => s.toggleHidden)
  const [moreOpen, setMoreOpen] = useState(false)

  return (
    <>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button
            type="button"
            title="Choose columns"
            className="flex shrink-0 items-center px-2 text-zinc-400 hover:text-zinc-600"
          >
            <Columns3 className="h-3.5 w-3.5" />
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            sideOffset={4}
            className="z-50 w-44 rounded-lg border border-zinc-200 bg-white py-1 text-sm shadow-lg"
          >
            {(Object.keys(COLUMN_LABELS) as DetailsColumnId[]).map((id) => (
              <DropdownMenu.Item
                key={id}
                onSelect={(e) => {
                  e.preventDefault()
                  toggleHidden(id)
                }}
                className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-zinc-700 outline-none hover:bg-zinc-100"
              >
                <Check className={`h-3.5 w-3.5 ${hidden.includes(id) ? 'invisible' : ''}`} />
                {COLUMN_LABELS[id]}
              </DropdownMenu.Item>
            ))}
            <div className={separatorClass} />
            <DropdownMenu.Item
              onSelect={(e) => {
                e.preventDefault()
                setMoreOpen(true)
              }}
              className="cursor-pointer px-3 py-1.5 text-zinc-700 outline-none hover:bg-zinc-100"
            >
              More…
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      <ChooseColumnsDialog open={moreOpen} onClose={() => setMoreOpen(false)} />
    </>
  )
}

interface DetailsViewHeaderProps {
  widths: Record<'name' | DetailsColumnId, number>
  sortKey: SortKey
  sortDir: SortDir
  onSort: (key: SortKey) => void
  visibleColumns: DetailsColumnId[]
  onReorder: (id: DetailsColumnId, beforeId: DetailsColumnId | null) => void
}

export function DetailsViewHeader({
  widths,
  sortKey,
  sortDir,
  onSort,
  visibleColumns,
  onReorder
}: DetailsViewHeaderProps): React.JSX.Element {
  return (
    <div className="sticky top-0 z-10 flex border-b border-zinc-200 bg-zinc-50 text-xs font-medium text-zinc-500">
      <div
        onClick={() => onSort('name')}
        style={{ minWidth: widths.name }}
        className="relative flex-1 cursor-pointer select-none px-3 py-1.5 text-left hover:bg-zinc-100"
      >
        Name
        {sortKey === 'name' && (sortDir === 'asc' ? ' ▲' : ' ▼')}
        <ResizeHandle columnId="name" />
      </div>
      {visibleColumns.map((id) => (
        <HeaderCell key={id} id={id} width={widths[id]} sortKey={sortKey} sortDir={sortDir} onSort={onSort} onReorder={onReorder} />
      ))}
      <ColumnChooser />
    </div>
  )
}
