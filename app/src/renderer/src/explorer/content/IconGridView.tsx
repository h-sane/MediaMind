import { useEffect, useMemo, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Folder, HardDrive } from 'lucide-react'
import { FileThumbnail } from '../../components/FileThumbnail'
import { useExplorerStore } from '../../stores/explorer'
import type { IconSize } from '../../stores/explorer'
import { useSelectionStore } from '../../stores/selection'
import { ExplorerContextMenu } from '../context/ContextMenu'
import { useEntryDnd } from '../dnd/useEntryDnd'
import { RenameInput } from '../interactions/RenameInput'
import { MarqueeLayer } from '../selection/MarqueeLayer'
import { useMarqueeSelect } from '../selection/useMarqueeSelect'
import { useFileOps } from '../useFileOps'
import { useSelectionModel } from '../selection/useSelectionModel'
import { groupEntries } from './grouping'
import { useIconSizeZoom } from './useIconSizeZoom'
import type { DirEntry } from './useDirectoryListing'

/** The four Explorer icon-size tiers (`Ctrl+Shift+1-4`). `large` matches
 * this view's original single fixed size exactly, so the default stays
 * pixel-identical for anyone who never touches icon size. */
const ICON_SIZE_CONFIG: Record<IconSize, { cellWidth: number; cellHeight: number; thumbClass: string; iconClass: string }> = {
  'extra-large': { cellWidth: 176, cellHeight: 188, thumbClass: 'h-32 w-32', iconClass: 'h-14 w-14' },
  large: { cellWidth: 140, cellHeight: 150, thumbClass: 'h-24 w-24', iconClass: 'h-10 w-10' },
  medium: { cellWidth: 104, cellHeight: 116, thumbClass: 'h-16 w-16', iconClass: 'h-7 w-7' },
  small: { cellWidth: 72, cellHeight: 80, thumbClass: 'h-9 w-9', iconClass: 'h-5 w-5' }
}

interface Props {
  entries: DirEntry[]
  onOpenFile: (path: string) => void
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
  thumbClass: string
  iconClass: string
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
  navigate,
  thumbClass,
  iconClass
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
        className={`flex flex-col items-center gap-1 rounded-lg p-2 text-center hover:bg-zinc-100 ${
          isSelected ? 'bg-blue-100 hover:bg-blue-100' : ''
        } ${isFocused ? 'outline outline-1 outline-offset-[-2px] outline-zinc-500' : ''} ${
          isCut ? 'opacity-40' : ''
        } ${isDragging ? 'opacity-40' : ''} ${isOver ? 'ring-2 ring-inset ring-blue-400 bg-blue-50' : ''}`}
        title={entry.name}
      >
        {entry.type === 'file' ? (
          <FileThumbnail path={entry.path} kind={entry.kind ?? 'other'} className={thumbClass} />
        ) : (
          <div className={`flex items-center justify-center rounded-lg bg-zinc-50 ${thumbClass}`}>
            {entry.type === 'drive' ? (
              <HardDrive className={`${iconClass} text-zinc-300`} />
            ) : (
              <Folder className={`${iconClass} text-amber-300`} />
            )}
          </div>
        )}
        {isRenaming ? (
          <RenameInput
            path={entry.path}
            name={entry.name}
            isFile={entry.type === 'file'}
            folder={currentPath ?? ''}
            className="w-full rounded border border-blue-500 px-1 py-0 text-center text-xs outline-none"
          />
        ) : (
          <span className="w-full truncate text-xs text-zinc-600">{entry.name}</span>
        )}
      </button>
    </ExplorerContextMenu>
  )
}

/** Explorer's "Large icons" view — a virtualized, responsive grid of tiles.
 * When Group-by is active, section headers replace virtualization (see
 * `content/grouping.ts` — module-level doc explains the trade-off). */
export function IconGridView({ entries, onOpenFile }: Props): React.JSX.Element {
  const navigate = useExplorerStore((s) => s.navigate)
  const currentPath = useExplorerStore((s) => s.currentPath)
  const renamingPath = useSelectionStore((s) => s.renamingPath)
  const focusedPath = useSelectionStore((s) => s.focusedPath)
  const groupBy = useExplorerStore((s) => s.groupBy)
  const iconSize = useExplorerStore((s) => s.iconSize)
  const setContentColumns = useExplorerStore((s) => s.setContentColumns)
  const sizeConfig = ICON_SIZE_CONFIG[iconSize]
  const scrollRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const [columns, setColumns] = useState(6)
  useIconSizeZoom(scrollRef)

  const orderedPaths = entries.map((e) => e.path)
  const { onItemClick, isSelected, setSelected, clear } = useSelectionModel(orderedPaths)
  const fileOps = useFileOps()
  const groups = useMemo(() => groupEntries(entries, groupBy), [entries, groupBy])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const observer = new ResizeObserver((observed) => {
      const width = observed[0]?.contentRect.width ?? el.clientWidth
      setColumns(Math.max(1, Math.floor(width / sizeConfig.cellWidth)))
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [sizeConfig.cellWidth])

  useEffect(() => {
    setContentColumns(columns)
  }, [columns, setContentColumns])

  const marquee = useMarqueeSelect({ containerRef: contentRef, onSelect: setSelected, onBackgroundMouseDown: clear })

  const rowCount = Math.ceil(entries.length / columns)
  const virtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => sizeConfig.cellHeight,
    overscan: 4
  })

  // Keep the focused row scrolled into view as arrow-key navigation moves
  // focus past what's currently rendered — without this, focus could land
  // on a row the virtualizer hasn't mounted yet.
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
                        thumbClass={sizeConfig.thumbClass}
                        iconClass={sizeConfig.iconClass}
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
                        thumbClass={sizeConfig.thumbClass}
                        iconClass={sizeConfig.iconClass}
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
