import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Folder, HardDrive } from 'lucide-react'
import { FileThumbnail } from '../../components/FileThumbnail'
import { FolderFaceThumbnail } from '../../components/FolderFaceThumbnail'
import { useExplorerStore } from '../../stores/explorer'
import type { IconSize } from '../../stores/explorer'
import { useSelectionStore } from '../../stores/selection'
import { ExplorerContextMenu } from '../context/ContextMenu'
import { useEntryDnd } from '../dnd/useEntryDnd'
import { RenameInput } from '../interactions/RenameInput'
import { MarqueeLayer } from '../selection/MarqueeLayer'
import { useMarqueeSelect } from '../selection/useMarqueeSelect'
import { useSelectionModel } from '../selection/useSelectionModel'
import { useTileFlags } from '../selection/useTileFlags'
import { groupEntries } from './grouping'
import { GroupedVirtualGrid } from './GroupedVirtualGrid'
import { useIconSizeZoom } from './useIconSizeZoom'
import type { DirEntry } from './useDirectoryListing'

/** The four Explorer icon-size tiers (`Ctrl+Shift+1-4`). `large` matches
 * this view's original single fixed size exactly, so the default stays
 * pixel-identical for anyone who never touches icon size. */
const ICON_SIZE_CONFIG: Record<
  IconSize,
  { cellWidth: number; cellHeight: number; thumbClass: string; iconClass: string; thumbPx: number; displayPx: number }
> = {
  'extra-large': { cellWidth: 176, cellHeight: 188, thumbClass: 'h-32 w-32', iconClass: 'h-14 w-14', thumbPx: 256, displayPx: 128 },
  large: { cellWidth: 140, cellHeight: 150, thumbClass: 'h-24 w-24', iconClass: 'h-10 w-10', thumbPx: 256, displayPx: 96 },
  medium: { cellWidth: 104, cellHeight: 116, thumbClass: 'h-16 w-16', iconClass: 'h-7 w-7', thumbPx: 128, displayPx: 64 },
  small: { cellWidth: 72, cellHeight: 80, thumbClass: 'h-9 w-9', iconClass: 'h-5 w-5', thumbPx: 96, displayPx: 36 }
}

interface Props {
  entries: DirEntry[]
  onOpenFile: (path: string) => void
}

interface TileProps {
  entry: DirEntry
  orderedPaths: string[]
  onOpenFile: (path: string) => void
  currentPath: string | null
  onItemClick: (e: React.MouseEvent, path: string) => void
  navigate: (path: string) => void
  thumbClass: string
  iconClass: string
  thumbPx: number
  displayPx: number
}

const Tile = memo(function Tile({
  entry,
  orderedPaths,
  onOpenFile,
  currentPath,
  onItemClick,
  navigate,
  thumbClass,
  iconClass,
  thumbPx,
  displayPx
}: TileProps): React.JSX.Element {
  const { ref, isDragging, isOver } = useEntryDnd(entry, orderedPaths)
  const { isSelected, isCut, isRenaming, isFocused } = useTileFlags(entry.path)

  return (
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
        <div className="relative">
          <FileThumbnail path={entry.path} kind={entry.kind ?? 'other'} className={thumbClass} size={thumbPx} />
          {entry.viaPlacement && (
            <span
              title="In this person's folder (no face match — kept by placement)"
              className="absolute right-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-zinc-900/70 text-white"
            >
              <Folder className="h-2.5 w-2.5" />
            </span>
          )}
        </div>
      ) : entry.type === 'drive' ? (
        <div className={`flex items-center justify-center rounded-lg bg-zinc-50 ${thumbClass}`}>
          <HardDrive className={`${iconClass} text-zinc-300`} />
        </div>
      ) : (
        <FolderFaceThumbnail
          path={entry.path}
          size={displayPx}
          fallback={
            <div className={`flex items-center justify-center rounded-lg bg-zinc-50 ${thumbClass}`}>
              <Folder className={`${iconClass} text-amber-300`} />
            </div>
          }
        />
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
  )
})

/** Explorer's "Large icons" view — a virtualized, responsive grid of tiles.
 * Both the ungrouped and Group-by branches are windowed (the grouped branch
 * via the shared `GroupedVirtualGrid`, Phase 6 / F5). */
export function IconGridView({ entries, onOpenFile }: Props): React.JSX.Element {
  const navigate = useExplorerStore((s) => s.navigate)
  const currentPath = useExplorerStore((s) => s.currentPath)
  const focusedPath = useSelectionStore((s) => s.focusedPath)
  const groupBy = useExplorerStore((s) => s.groupBy)
  const iconSize = useExplorerStore((s) => s.iconSize)
  const setContentColumns = useExplorerStore((s) => s.setContentColumns)
  const sizeConfig = ICON_SIZE_CONFIG[iconSize]
  const scrollRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const [columns, setColumns] = useState(6)
  useIconSizeZoom(scrollRef)

  const orderedPaths = useMemo(() => entries.map((e) => e.path), [entries])
  const { onItemClick, setSelected, clear } = useSelectionModel(orderedPaths)
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
  // on a row the virtualizer hasn't mounted yet. (The grouped branch's own
  // scroll-into-view is handled inside GroupedVirtualGrid.)
  useEffect(() => {
    if (groupBy !== 'none' || !focusedPath) return
    const idx = orderedPaths.indexOf(focusedPath)
    if (idx === -1) return
    virtualizer.scrollToIndex(Math.floor(idx / columns), { align: 'auto' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusedPath, groupBy, columns])

  function renderTile(entry: DirEntry): React.JSX.Element {
    return (
      <Tile
        key={entry.path}
        entry={entry}
        orderedPaths={orderedPaths}
        onOpenFile={onOpenFile}
        currentPath={currentPath}
        onItemClick={onItemClick}
        navigate={navigate}
        thumbClass={sizeConfig.thumbClass}
        iconClass={sizeConfig.iconClass}
        thumbPx={sizeConfig.thumbPx}
        displayPx={sizeConfig.displayPx}
      />
    )
  }

  return (
    <ExplorerContextMenu entries={entries} orderedPaths={orderedPaths} onOpenFile={onOpenFile}>
      <div
        ref={scrollRef}
        className="h-full overflow-y-auto p-3"
        onMouseDown={marquee.onMouseDown}
        onMouseMove={marquee.onMouseMove}
        onMouseUp={marquee.onMouseUp}
        onMouseLeave={marquee.onMouseLeave}
      >
        {groupBy === 'none' ? (
          <div
            ref={contentRef}
            style={{ height: virtualizer.getTotalSize(), position: 'relative', width: '100%' }}
          >
            {virtualizer.getVirtualItems().map((virtualRow) => {
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
                  {rowEntries.map(renderTile)}
                </div>
              )
            })}
            <MarqueeLayer rect={marquee.marqueeRect} />
          </div>
        ) : (
          <GroupedVirtualGrid
            groups={groups}
            columns={columns}
            cellHeight={sizeConfig.cellHeight}
            scrollRef={scrollRef}
            containerRef={contentRef}
            focusedPath={focusedPath}
            renderTile={renderTile}
            overlay={<MarqueeLayer rect={marquee.marqueeRect} />}
          />
        )}
      </div>
    </ExplorerContextMenu>
  )
}
