import { useEffect, useMemo, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Folder, HardDrive } from 'lucide-react'
import { FileThumbnail } from '../../components/FileThumbnail'
import { useDetailsColumnsStore, type DetailsColumnId } from '../../stores/detailsColumns'
import { useExplorerStore } from '../../stores/explorer'
import { useSelectionStore } from '../../stores/selection'
import { ExplorerContextMenu } from '../context/ContextMenu'
import { useEntryDnd } from '../dnd/useEntryDnd'
import { formatAttributes, formatDate, formatSize } from '../format'
import { RenameInput } from '../interactions/RenameInput'
import { MarqueeLayer } from '../selection/MarqueeLayer'
import { useMarqueeSelect } from '../selection/useMarqueeSelect'
import { useFileOps } from '../useFileOps'
import { useSelectionModel } from '../selection/useSelectionModel'
import { DetailsViewHeader } from './DetailsViewHeader'
import { groupEntries } from './grouping'
import type { DirEntry } from './useDirectoryListing'

interface Props {
  entries: DirEntry[]
  onOpenFile: (path: string) => void
}

function typeLabel(entry: DirEntry): string {
  if (entry.type === 'drive') return 'Drive'
  if (entry.type === 'folder') return 'Folder'
  return entry.kind ?? ''
}

interface RowProps {
  entry: DirEntry
  orderedPaths: string[]
  onOpenFile: (path: string) => void
  visibleColumns: DetailsColumnId[]
  widths: Record<'name' | DetailsColumnId, number>
  isSelected: boolean
  isCut: boolean
  isRenaming: boolean
  isFocused: boolean
  currentPath: string | null
  onItemClick: (e: React.MouseEvent, path: string) => void
  navigate: (path: string) => void
}

function Row({
  entry,
  orderedPaths,
  onOpenFile,
  visibleColumns,
  widths,
  isSelected,
  isCut,
  isRenaming,
  isFocused,
  currentPath,
  onItemClick,
  navigate
}: RowProps): React.JSX.Element {
  const { ref, isDragging, isOver } = useEntryDnd(entry, orderedPaths)

  return (
    <ExplorerContextMenu entry={entry} orderedPaths={orderedPaths} onOpenFile={onOpenFile}>
      <div
        ref={ref}
        data-entry-path={entry.path}
        onClick={(e) => onItemClick(e, entry.path)}
        onDoubleClick={() => (entry.type === 'file' ? onOpenFile(entry.path) : navigate(entry.path))}
        className={`flex h-full cursor-pointer items-center text-sm hover:bg-zinc-50 ${
          isSelected ? 'bg-blue-100 hover:bg-blue-100' : ''
        } ${isFocused ? 'outline outline-1 outline-offset-[-2px] outline-zinc-500' : ''} ${
          isCut ? 'opacity-40' : ''
        } ${isDragging ? 'opacity-40' : ''} ${isOver ? 'ring-2 ring-inset ring-blue-400 bg-blue-50' : ''}`}
      >
        <div className="flex min-w-0 flex-1 items-center gap-2 px-3" style={{ minWidth: widths.name }}>
          {entry.type === 'file' ? (
            <FileThumbnail path={entry.path} kind={entry.kind ?? 'other'} className="h-5 w-5 shrink-0" />
          ) : entry.type === 'drive' ? (
            <HardDrive className="h-4 w-4 shrink-0 text-zinc-400" />
          ) : (
            <Folder className="h-4 w-4 shrink-0 text-amber-400" />
          )}
          {isRenaming ? (
            <RenameInput path={entry.path} name={entry.name} isFile={entry.type === 'file'} folder={currentPath ?? ''} />
          ) : (
            <span className="truncate">{entry.name}</span>
          )}
        </div>
        {visibleColumns.map((id) => (
          <div key={id} style={{ width: widths[id] }} className="shrink-0 truncate px-3 text-zinc-500">
            {id === 'date' ? (
              formatDate(entry.mtime)
            ) : id === 'type' ? (
              <span className="capitalize">{typeLabel(entry)}</span>
            ) : id === 'size' ? (
              formatSize(entry.size)
            ) : id === 'created' ? (
              formatDate(entry.created)
            ) : id === 'accessed' ? (
              formatDate(entry.accessed)
            ) : (
              formatAttributes(entry.readOnly, entry.hidden, entry.system) || '—'
            )}
          </div>
        ))}
      </div>
    </ExplorerContextMenu>
  )
}

/** Height of the column-header row below, so a group's sticky section
 * header (grouped-mode only) pins itself just under it instead of
 * overlapping — both are `position: sticky` within the same scrollport. */
const COLUMN_HEADER_HEIGHT = 29

export function DetailsView({ entries, onOpenFile }: Props): React.JSX.Element {
  const navigate = useExplorerStore((s) => s.navigate)
  const currentPath = useExplorerStore((s) => s.currentPath)
  const sortKey = useExplorerStore((s) => s.sortKey)
  const sortDir = useExplorerStore((s) => s.sortDir)
  const setSort = useExplorerStore((s) => s.setSort)
  const renamingPath = useSelectionStore((s) => s.renamingPath)
  const focusedPath = useSelectionStore((s) => s.focusedPath)
  const groupBy = useExplorerStore((s) => s.groupBy)
  const setContentColumns = useExplorerStore((s) => s.setContentColumns)
  const scrollRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)

  const order = useDetailsColumnsStore((s) => s.order)
  const hidden = useDetailsColumnsStore((s) => s.hidden)
  const widths = useDetailsColumnsStore((s) => s.widths)
  const reorder = useDetailsColumnsStore((s) => s.reorder)
  const visibleColumns = order.filter((id) => !hidden.includes(id))

  const orderedPaths = entries.map((e) => e.path)
  const { onItemClick, isSelected, setSelected, clear } = useSelectionModel(orderedPaths)
  const fileOps = useFileOps()
  const groups = useMemo(() => groupEntries(entries, groupBy), [entries, groupBy])

  // A Details row is a single-column list — Up/Down always move by one row.
  useEffect(() => {
    setContentColumns(1)
  }, [setContentColumns])

  const marquee = useMarqueeSelect({ containerRef: contentRef, onSelect: setSelected, onBackgroundMouseDown: clear })

  const virtualizer = useVirtualizer({
    count: entries.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 32,
    overscan: 8
  })

  useEffect(() => {
    if (groupBy !== 'none' || !focusedPath) return
    const idx = orderedPaths.indexOf(focusedPath)
    if (idx === -1) return
    virtualizer.scrollToIndex(idx, { align: 'auto' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusedPath, groupBy])

  useEffect(() => {
    if (groupBy === 'none' || !focusedPath) return
    contentRef.current?.querySelector(`[data-entry-path="${CSS.escape(focusedPath)}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [focusedPath, groupBy])

  function renderRow(entry: DirEntry): React.JSX.Element {
    return (
      <Row
        key={entry.path}
        entry={entry}
        orderedPaths={orderedPaths}
        onOpenFile={onOpenFile}
        visibleColumns={visibleColumns}
        widths={widths}
        isSelected={isSelected(entry.path)}
        isCut={fileOps.isCut(entry.path)}
        isRenaming={renamingPath === entry.path}
        isFocused={focusedPath === entry.path}
        currentPath={currentPath}
        onItemClick={onItemClick}
        navigate={navigate}
      />
    )
  }

  return (
    <ExplorerContextMenu entry={null} orderedPaths={orderedPaths} onOpenFile={onOpenFile}>
      <div
        ref={scrollRef}
        className="h-full overflow-y-auto"
        onMouseDown={marquee.onMouseDown}
        onMouseMove={marquee.onMouseMove}
        onMouseUp={marquee.onMouseUp}
        onMouseLeave={marquee.onMouseLeave}
      >
        <DetailsViewHeader
          widths={widths}
          sortKey={sortKey}
          sortDir={sortDir}
          onSort={setSort}
          visibleColumns={visibleColumns}
          onReorder={reorder}
        />

        {groupBy === 'none' ? (
          <div
            ref={contentRef}
            style={{ height: virtualizer.getTotalSize(), position: 'relative', width: '100%' }}
          >
            {virtualizer.getVirtualItems().map((virtualRow) => {
              const entry = entries[virtualRow.index]
              return (
                <div
                  key={entry.path}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: `${virtualRow.size}px`,
                    transform: `translateY(${virtualRow.start}px)`
                  }}
                >
                  {renderRow(entry)}
                </div>
              )
            })}
            <MarqueeLayer rect={marquee.marqueeRect} />
          </div>
        ) : (
          <div ref={contentRef} style={{ position: 'relative' }}>
            {groups.map((group) => (
              <div key={group.key}>
                {group.label && (
                  <div
                    className="sticky z-[9] bg-white px-3 py-1 text-xs font-semibold text-zinc-500"
                    style={{ top: COLUMN_HEADER_HEIGHT }}
                  >
                    {group.label} <span className="font-normal text-zinc-400">({group.entries.length})</span>
                  </div>
                )}
                {group.entries.map(renderRow)}
              </div>
            ))}
            <MarqueeLayer rect={marquee.marqueeRect} />
          </div>
        )}
      </div>
    </ExplorerContextMenu>
  )
}
