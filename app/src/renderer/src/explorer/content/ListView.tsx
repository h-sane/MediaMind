import { useEffect, useMemo, useRef, useState } from 'react'
import { Folder, HardDrive } from 'lucide-react'
import { FileThumbnail } from '../../components/FileThumbnail'
import { useExplorerStore } from '../../stores/explorer'
import { useSelectionStore } from '../../stores/selection'
import { ExplorerContextMenu } from '../context/ContextMenu'
import { useEntryDnd } from '../dnd/useEntryDnd'
import { RenameInput } from '../interactions/RenameInput'
import { useFileOps } from '../useFileOps'
import { useSelectionModel } from '../selection/useSelectionModel'
import { groupEntries } from './grouping'
import type { DirEntry } from './useDirectoryListing'

/** Matches the `minmax(220px,1fr)` used by the CSS auto-fill grid below —
 * kept in sync manually since there's no JS-computed column count otherwise
 * for the roving-focus row/column math in `useKeyboardShortcuts.ts`. */
const CELL_MIN_WIDTH = 220

interface Props {
  entries: DirEntry[]
  onOpenFile: (path: string) => void
}

interface RowProps {
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

function Row({
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
}: RowProps): React.JSX.Element {
  const { ref, isDragging, isOver } = useEntryDnd(entry, orderedPaths)

  return (
    <ExplorerContextMenu entry={entry} orderedPaths={orderedPaths} onOpenFile={onOpenFile}>
      <button
        type="button"
        ref={ref}
        data-entry-path={entry.path}
        onClick={(e) => onItemClick(e, entry.path)}
        onDoubleClick={() => (entry.type === 'file' ? onOpenFile(entry.path) : navigate(entry.path))}
        className={`flex min-w-0 items-center gap-2 rounded px-2 py-1 text-left text-sm hover:bg-zinc-100 ${
          isSelected ? 'bg-blue-100 hover:bg-blue-100' : ''
        } ${isFocused ? 'outline outline-1 outline-offset-[-2px] outline-zinc-500' : ''} ${
          isCut ? 'opacity-40' : ''
        } ${isDragging ? 'opacity-40' : ''} ${isOver ? 'ring-2 ring-inset ring-blue-400 bg-blue-50' : ''}`}
        title={entry.name}
      >
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
      </button>
    </ExplorerContextMenu>
  )
}

/** Explorer's "List" view — small icon + name, flowing into columns. Never
 * had marquee-select in real Explorer either (unlike Details, which Phase J
 * adds it to), so this stays click/ctrl/shift-click only. */
export function ListView({ entries, onOpenFile }: Props): React.JSX.Element {
  const navigate = useExplorerStore((s) => s.navigate)
  const currentPath = useExplorerStore((s) => s.currentPath)
  const renamingPath = useSelectionStore((s) => s.renamingPath)
  const focusedPath = useSelectionStore((s) => s.focusedPath)
  const groupBy = useExplorerStore((s) => s.groupBy)
  const setContentColumns = useExplorerStore((s) => s.setContentColumns)
  const scrollRef = useRef<HTMLDivElement>(null)
  const orderedPaths = entries.map((e) => e.path)
  const { onItemClick, isSelected } = useSelectionModel(orderedPaths)
  const fileOps = useFileOps()
  const groups = useMemo(() => groupEntries(entries, groupBy), [entries, groupBy])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const observer = new ResizeObserver((observed) => {
      const width = observed[0]?.contentRect.width ?? el.clientWidth
      setContentColumns(Math.max(1, Math.floor(width / CELL_MIN_WIDTH)))
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [setContentColumns])

  useEffect(() => {
    if (!focusedPath) return
    scrollRef.current?.querySelector(`[data-entry-path="${CSS.escape(focusedPath)}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [focusedPath])

  function renderRow(entry: DirEntry): React.JSX.Element {
    return (
      <Row
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
    )
  }

  return (
    <ExplorerContextMenu entry={null} orderedPaths={orderedPaths} onOpenFile={onOpenFile}>
      <div ref={scrollRef} className="h-full overflow-y-auto p-2">
        {groupBy === 'none' ? (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))]">{entries.map(renderRow)}</div>
        ) : (
          groups.map((group) => (
            <div key={group.key}>
              {group.label && (
                <div className="sticky top-0 z-10 bg-white px-1 py-1 text-xs font-semibold text-zinc-500">
                  {group.label} <span className="font-normal text-zinc-400">({group.entries.length})</span>
                </div>
              )}
              <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))]">{group.entries.map(renderRow)}</div>
            </div>
          ))
        )}
      </div>
    </ExplorerContextMenu>
  )
}
