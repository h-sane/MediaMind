import { useEffect, useMemo, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Folder, HardDrive } from 'lucide-react'
import { FileThumbnail } from '../../components/FileThumbnail'
import { useExplorerStore } from '../../stores/explorer'
import { useSelectionStore } from '../../stores/selection'
import { ExplorerContextMenu } from '../context/ContextMenu'
import { useEntryDnd } from '../dnd/useEntryDnd'
import { formatDate, formatSize } from '../format'
import { RenameInput } from '../interactions/RenameInput'
import { useFileOps } from '../useFileOps'
import { useSelectionModel } from '../selection/useSelectionModel'
import { groupEntries } from './grouping'
import type { DirEntry } from './useDirectoryListing'

const ROW_HEIGHT = 56

interface Props {
  entries: DirEntry[]
  onOpenFile: (path: string) => void
}

function typeLabel(entry: DirEntry): string {
  if (entry.type === 'drive') return 'Drive'
  if (entry.type === 'folder') return 'Folder'
  return entry.kind ?? ''
}

function metaLine(entry: DirEntry): string {
  const parts = [typeLabel(entry)]
  if (entry.size !== undefined) parts.push(formatSize(entry.size))
  if (entry.mtime !== undefined) parts.push(formatDate(entry.mtime))
  return parts.join(' · ')
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
      <div
        ref={ref}
        data-entry-path={entry.path}
        onClick={(e) => onItemClick(e, entry.path)}
        onDoubleClick={() => (entry.type === 'file' ? onOpenFile(entry.path) : navigate(entry.path))}
        className={`flex h-full w-full cursor-pointer items-center gap-3 border-b border-zinc-100 px-3 hover:bg-zinc-50 ${
          isSelected ? 'bg-blue-100 hover:bg-blue-100' : ''
        } ${isFocused ? 'outline outline-1 outline-offset-[-2px] outline-zinc-500' : ''} ${
          isCut ? 'opacity-40' : ''
        } ${isDragging ? 'opacity-40' : ''} ${isOver ? 'ring-2 ring-inset ring-blue-400 bg-blue-50' : ''}`}
      >
        {entry.type === 'file' ? (
          <FileThumbnail path={entry.path} kind={entry.kind ?? 'other'} className="h-9 w-9 shrink-0" />
        ) : (
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-zinc-50">
            {entry.type === 'drive' ? (
              <HardDrive className="h-5 w-5 text-zinc-300" />
            ) : (
              <Folder className="h-5 w-5 text-amber-300" />
            )}
          </div>
        )}
        <div className="min-w-0 flex-1">
          {isRenaming ? (
            <RenameInput path={entry.path} name={entry.name} isFile={entry.type === 'file'} folder={currentPath ?? ''} />
          ) : (
            <span className="block truncate text-sm font-medium text-zinc-800">{entry.name}</span>
          )}
          <span className="block truncate text-xs text-zinc-400">{metaLine(entry)}</span>
        </div>
      </div>
    </ExplorerContextMenu>
  )
}

/** Explorer's "Content" view — one full-width row per item: icon, name, and
 * a type/size/date summary line beneath it. No columns, no marquee-select
 * (matching List view's simpler interaction model). */
export function ContentModeView({ entries, onOpenFile }: Props): React.JSX.Element {
  const navigate = useExplorerStore((s) => s.navigate)
  const currentPath = useExplorerStore((s) => s.currentPath)
  const renamingPath = useSelectionStore((s) => s.renamingPath)
  const focusedPath = useSelectionStore((s) => s.focusedPath)
  const groupBy = useExplorerStore((s) => s.groupBy)
  const setContentColumns = useExplorerStore((s) => s.setContentColumns)
  const scrollRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)

  const orderedPaths = entries.map((e) => e.path)
  const { onItemClick, isSelected } = useSelectionModel(orderedPaths)
  const fileOps = useFileOps()
  const groups = useMemo(() => groupEntries(entries, groupBy), [entries, groupBy])

  // Single-column view — Up/Down always move by exactly one entry.
  useEffect(() => {
    setContentColumns(1)
  }, [setContentColumns])

  const virtualizer = useVirtualizer({
    count: entries.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
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
      <div ref={scrollRef} className="h-full overflow-y-auto">
        {groupBy === 'none' ? (
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative', width: '100%' }}>
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
          </div>
        ) : (
          <div ref={contentRef}>
            {groups.map((group) => (
              <div key={group.key}>
                {group.label && (
                  <div className="sticky top-0 z-10 bg-white px-3 py-1 text-xs font-semibold text-zinc-500">
                    {group.label} <span className="font-normal text-zinc-400">({group.entries.length})</span>
                  </div>
                )}
                {group.entries.map(renderRow)}
              </div>
            ))}
          </div>
        )}
      </div>
    </ExplorerContextMenu>
  )
}
