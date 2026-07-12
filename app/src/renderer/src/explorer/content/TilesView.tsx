import { useEffect, useMemo, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Folder, HardDrive } from 'lucide-react'
import { FileThumbnail } from '../../components/FileThumbnail'
import { useExplorerStore } from '../../stores/explorer'
import { useSelectionStore } from '../../stores/selection'
import { ExplorerContextMenu } from '../context/ContextMenu'
import { useEntryDnd } from '../dnd/useEntryDnd'
import { formatSize } from '../format'
import { RenameInput } from '../interactions/RenameInput'
import { MarqueeLayer } from '../selection/MarqueeLayer'
import { useMarqueeSelect } from '../selection/useMarqueeSelect'
import { useFileOps } from '../useFileOps'
import { useSelectionModel } from '../selection/useSelectionModel'
import { groupEntries } from './grouping'
import type { DirEntry } from './useDirectoryListing'

const CELL_WIDTH = 260
const CELL_HEIGHT = 68

interface Props {
  entries: DirEntry[]
  onOpenFile: (path: string) => void
}

function subtitle(entry: DirEntry): string {
  if (entry.type === 'drive') return 'Drive'
  if (entry.type === 'folder') return 'Folder'
  return `${entry.kind ?? ''}${entry.size !== undefined ? ` · ${formatSize(entry.size)}` : ''}`
}

interface TileProps {
  entry: DirEntry
  orderedPaths: string[]
  onOpenFile: (path: string) => void
  isSelected: boolean
  isCut: boolean
  isRenaming: boolean
  isFocused: boolean
  currentPath: string | null
  onItemClick: (e: React.MouseEvent, path: string) => void
  navigate: (path: string) => void
}

function Tile({
  entry,
  orderedPaths,
  onOpenFile,
  isSelected,
  isCut,
  isRenaming,
  isFocused,
  currentPath,
  onItemClick,
  navigate
}: TileProps): React.JSX.Element {
  const { ref, isDragging, isOver } = useEntryDnd(entry, orderedPaths)

  return (
    <ExplorerContextMenu entry={entry} orderedPaths={orderedPaths} onOpenFile={onOpenFile}>
      <button
        type="button"
        ref={ref}
        data-entry-path={entry.path}
        onClick={(e) => onItemClick(e, entry.path)}
        onDoubleClick={() => (entry.type === 'file' ? onOpenFile(entry.path) : navigate(entry.path))}
        className={`flex min-w-0 items-center gap-2.5 rounded-lg p-2 text-left hover:bg-zinc-100 ${
          isSelected ? 'bg-blue-100 hover:bg-blue-100' : ''
        } ${isFocused ? 'outline outline-1 outline-offset-[-2px] outline-zinc-500' : ''} ${
          isCut ? 'opacity-40' : ''
        } ${isDragging ? 'opacity-40' : ''} ${isOver ? 'ring-2 ring-inset ring-blue-400 bg-blue-50' : ''}`}
        title={entry.name}
      >
        {entry.type === 'file' ? (
          <FileThumbnail path={entry.path} kind={entry.kind ?? 'other'} className="h-11 w-11 shrink-0" />
        ) : (
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-zinc-50">
            {entry.type === 'drive' ? (
              <HardDrive className="h-6 w-6 text-zinc-300" />
            ) : (
              <Folder className="h-6 w-6 text-amber-300" />
            )}
          </div>
        )}
        <div className="min-w-0 flex-1">
          {isRenaming ? (
            <RenameInput path={entry.path} name={entry.name} isFile={entry.type === 'file'} folder={currentPath ?? ''} />
          ) : (
            <span className="block truncate text-sm text-zinc-800">{entry.name}</span>
          )}
          <span className="block truncate text-xs capitalize text-zinc-400">{subtitle(entry)}</span>
        </div>
      </button>
    </ExplorerContextMenu>
  )
}

/** Explorer's "Tiles" view — medium icon + two lines of text (name,
 * type/size), arranged in a virtualized responsive grid. Structurally the
 * same marquee-select + virtualization as IconGridView, just wider/shorter
 * cells and a horizontal icon-then-text tile layout. */
export function TilesView({ entries, onOpenFile }: Props): React.JSX.Element {
  const navigate = useExplorerStore((s) => s.navigate)
  const currentPath = useExplorerStore((s) => s.currentPath)
  const renamingPath = useSelectionStore((s) => s.renamingPath)
  const focusedPath = useSelectionStore((s) => s.focusedPath)
  const groupBy = useExplorerStore((s) => s.groupBy)
  const setContentColumns = useExplorerStore((s) => s.setContentColumns)
  const scrollRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const [columns, setColumns] = useState(3)

  const orderedPaths = entries.map((e) => e.path)
  const { onItemClick, isSelected, setSelected, clear } = useSelectionModel(orderedPaths)
  const fileOps = useFileOps()
  const groups = useMemo(() => groupEntries(entries, groupBy), [entries, groupBy])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const observer = new ResizeObserver((observed) => {
      const width = observed[0]?.contentRect.width ?? el.clientWidth
      setColumns(Math.max(1, Math.floor(width / CELL_WIDTH)))
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    setContentColumns(columns)
  }, [columns, setContentColumns])

  const marquee = useMarqueeSelect({ containerRef: contentRef, onSelect: setSelected, onBackgroundMouseDown: clear })

  const rowCount = Math.ceil(entries.length / columns)
  const virtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => CELL_HEIGHT,
    overscan: 6
  })

  useEffect(() => {
    if (groupBy !== 'none' || !focusedPath) return
    const idx = orderedPaths.indexOf(focusedPath)
    if (idx === -1) return
    virtualizer.scrollToIndex(Math.floor(idx / columns), { align: 'auto' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusedPath, groupBy, columns])

  useEffect(() => {
    if (groupBy === 'none' || !focusedPath) return
    contentRef.current?.querySelector(`[data-entry-path="${CSS.escape(focusedPath)}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [focusedPath, groupBy])

  return (
    <ExplorerContextMenu entry={null} orderedPaths={orderedPaths} onOpenFile={onOpenFile}>
      <div
        ref={scrollRef}
        className="h-full overflow-y-auto p-3"
        onMouseDown={marquee.onMouseDown}
        onMouseMove={marquee.onMouseMove}
        onMouseUp={marquee.onMouseUp}
        onMouseLeave={marquee.onMouseLeave}
      >
        <div
          ref={contentRef}
          style={
            groupBy === 'none'
              ? { height: virtualizer.getTotalSize(), position: 'relative', width: '100%' }
              : { position: 'relative', width: '100%' }
          }
        >
          {groupBy === 'none'
            ? virtualizer.getVirtualItems().map((virtualRow) => {
                const rowEntries = entries.slice(virtualRow.index * columns, virtualRow.index * columns + columns)
                return (
                  <div
                    key={virtualRow.key}
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      height: `${virtualRow.size}px`,
                      transform: `translateY(${virtualRow.start}px)`,
                      display: 'grid',
                      gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`
                    }}
                  >
                    {rowEntries.map((entry) => (
                      <Tile
                        key={entry.path}
                        entry={entry}
                        orderedPaths={orderedPaths}
                        onOpenFile={onOpenFile}
                        isSelected={isSelected(entry.path)}
                        isCut={fileOps.isCut(entry.path)}
                        isRenaming={renamingPath === entry.path}
                        isFocused={focusedPath === entry.path}
                        currentPath={currentPath}
                        onItemClick={onItemClick}
                        navigate={navigate}
                      />
                    ))}
                  </div>
                )
              })
            : groups.map((group) => (
                <div key={group.key}>
                  {group.label && (
                    <div className="sticky top-0 z-10 bg-white px-1 py-1 text-xs font-semibold text-zinc-500">
                      {group.label} <span className="font-normal text-zinc-400">({group.entries.length})</span>
                    </div>
                  )}
                  <div style={{ display: 'grid', gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
                    {group.entries.map((entry) => (
                      <Tile
                        key={entry.path}
                        entry={entry}
                        orderedPaths={orderedPaths}
                        onOpenFile={onOpenFile}
                        isSelected={isSelected(entry.path)}
                        isCut={fileOps.isCut(entry.path)}
                        isRenaming={renamingPath === entry.path}
                        isFocused={focusedPath === entry.path}
                        currentPath={currentPath}
                        onItemClick={onItemClick}
                        navigate={navigate}
                      />
                    ))}
                  </div>
                </div>
              ))}
          <MarqueeLayer rect={marquee.marqueeRect} />
        </div>
      </div>
    </ExplorerContextMenu>
  )
}
