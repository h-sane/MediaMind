import { useEffect, useMemo, useRef, useState } from 'react'
import { Folder, HardDrive } from 'lucide-react'
import { FileThumbnail } from '../../components/FileThumbnail'
import { useExplorerStore } from '../../stores/explorer'
import type { IconSize } from '../../stores/explorer'
import { useSelectionStore } from '../../stores/selection'
import { ExplorerContextMenu } from '../context/ContextMenu'
import { useEntryDnd } from '../dnd/useEntryDnd'
import { RenameInput } from '../interactions/RenameInput'
import { useFileOps } from '../useFileOps'
import { useSelectionModel } from '../selection/useSelectionModel'
import { groupEntries } from './grouping'
import { GroupedVirtualGrid } from './GroupedVirtualGrid'
import { useIconSizeZoom } from './useIconSizeZoom'
import type { DirEntry } from './useDirectoryListing'

/** Same four icon-size tiers `IconGridView.tsx` uses (`Ctrl+Shift+1-4`) — a
 * gallery is visually the same kind of thumbnail grid, just always grouped
 * by date instead of respecting the independent Group-by setting. `cellHeight`
 * mirrors `IconGridView.tsx`'s `ICON_SIZE_CONFIG` (same tile markup, so the
 * same measured row heights apply) — used by `GroupedVirtualGrid` to
 * estimate virtualized row size. */
const ICON_SIZE_CONFIG: Record<IconSize, { thumbClass: string; iconClass: string; cellHeight: number }> = {
  'extra-large': { thumbClass: 'h-32 w-32', iconClass: 'h-14 w-14', cellHeight: 188 },
  large: { thumbClass: 'h-24 w-24', iconClass: 'h-10 w-10', cellHeight: 150 },
  medium: { thumbClass: 'h-16 w-16', iconClass: 'h-7 w-7', cellHeight: 116 },
  small: { thumbClass: 'h-9 w-9', iconClass: 'h-5 w-5', cellHeight: 80 }
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
        onDoubleClick={() => onOpenFile(entry.path)}
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
            isFile
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

/**
 * Explorer's "Gallery" view (Phase O) — a recursive, always date-grouped
 * thumbnail timeline (`entries` is already the recursive walk from
 * `useDirectoryListing`'s gallery branch, sorted by mtime desc). Every item
 * is a file — no folders/drives ever appear here, matching real Explorer's
 * own Gallery, which is a flat photo/video timeline, not a folder browser.
 *
 * Structurally this is `IconGridView.tsx` with the grouping forced to
 * `'date'` instead of reading the store's independent Group-by setting.
 * Rendering is windowed via the shared `GroupedVirtualGrid` (see
 * `docs/PERFORMANCE_AND_INGEST_V4_PLAN.md` Phase 5) — only the section
 * headers and tile rows near the viewport are ever mounted, regardless of
 * how many files the recursive walk found.
 */
export function GalleryView({ entries, onOpenFile }: Props): React.JSX.Element {
  const currentPath = useExplorerStore((s) => s.currentPath)
  const renamingPath = useSelectionStore((s) => s.renamingPath)
  const focusedPath = useSelectionStore((s) => s.focusedPath)
  const iconSize = useExplorerStore((s) => s.iconSize)
  const setContentColumns = useExplorerStore((s) => s.setContentColumns)
  const sizeConfig = ICON_SIZE_CONFIG[iconSize]
  const scrollRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const [columns, setColumns] = useState(6)
  useIconSizeZoom(scrollRef)

  const orderedPaths = entries.map((e) => e.path)
  const { onItemClick, isSelected } = useSelectionModel(orderedPaths)
  const fileOps = useFileOps()
  const groups = useMemo(() => groupEntries(entries, 'date'), [entries])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const observer = new ResizeObserver((observed) => {
      const width = observed[0]?.contentRect.width ?? el.clientWidth
      setColumns(Math.max(1, Math.floor(width / 140)))
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    setContentColumns(columns)
  }, [columns, setContentColumns])

  return (
    <ExplorerContextMenu entry={null} orderedPaths={orderedPaths} onOpenFile={onOpenFile}>
      <div ref={scrollRef} className="h-full overflow-y-auto p-3">
        <GroupedVirtualGrid
          groups={groups}
          columns={columns}
          cellHeight={sizeConfig.cellHeight}
          scrollRef={scrollRef}
          containerRef={contentRef}
          focusedPath={focusedPath}
          renderTile={(entry) => (
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
              thumbClass={sizeConfig.thumbClass}
              iconClass={sizeConfig.iconClass}
            />
          )}
        />
      </div>
    </ExplorerContextMenu>
  )
}
