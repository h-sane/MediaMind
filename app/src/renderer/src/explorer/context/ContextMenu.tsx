import * as RadixContextMenu from '@radix-ui/react-context-menu'
import { useQueryClient } from '@tanstack/react-query'
import {
  ChevronRight,
  Copy,
  FileArchive,
  FolderPlus,
  Info,
  Link2,
  Redo2,
  RefreshCw,
  Scissors,
  Send,
  Star,
  StarOff,
  Trash2,
  Undo2
} from 'lucide-react'
import { usePinQuickAccess, useQuickAccess, useUnpinQuickAccess } from '../../api/hooks'
import { isRealFolder, useExplorerStore } from '../../stores/explorer'
import type { GroupKey, SortKey, ViewMode } from '../../stores/explorer'
import { useSelectionStore } from '../../stores/selection'
import { GROUP_LABELS, SORT_LABELS, VIEW_OPTIONS } from '../chrome/viewMenuData'
import { useFileOps } from '../useFileOps'
import type { DirEntry } from '../content/useDirectoryListing'

interface Props {
  /** The entry under the cursor, or null for a right-click on empty space. */
  entry: DirEntry | null
  orderedPaths: string[]
  onOpenFile: (path: string) => void
  children: React.ReactNode
}

const itemClass =
  'flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm text-zinc-700 outline-none hover:bg-zinc-100 data-[disabled]:pointer-events-none data-[disabled]:text-zinc-300'
const separatorClass = 'my-1 h-px bg-zinc-200'
const contentClass = 'z-50 w-52 rounded-lg border border-zinc-200 bg-white py-1 shadow-lg'
const subContentClass = 'z-50 w-44 rounded-lg border border-zinc-200 bg-white py-1 shadow-lg'

/** One right-click menu, reused for every row across all three views and
 * for empty-space clicks. Menu contents branch on `entry` and the current
 * selection rather than each view building its own menu. */
export function ExplorerContextMenu({ entry, orderedPaths, onOpenFile, children }: Props): React.JSX.Element {
  const navigate = useExplorerStore((s) => s.navigate)
  const currentPath = useExplorerStore((s) => s.currentPath)
  const sortKey = useExplorerStore((s) => s.sortKey)
  const setSort = useExplorerStore((s) => s.setSort)
  const groupBy = useExplorerStore((s) => s.groupBy)
  const setGroupBy = useExplorerStore((s) => s.setGroupBy)
  const viewMode = useExplorerStore((s) => s.viewMode)
  const setViewMode = useExplorerStore((s) => s.setViewMode)
  const selected = useSelectionStore((s) => s.selected)
  const click = useSelectionStore((s) => s.click)
  const qc = useQueryClient()
  const fileOps = useFileOps()
  const { data: quickAccess } = useQuickAccess()
  const pinMutation = usePinQuickAccess()
  const unpinMutation = useUnpinQuickAccess()

  function ensureSelected(): void {
    if (entry && !selected.has(entry.path)) {
      click(entry.path, { ctrl: false, shift: false }, orderedPaths)
    }
  }

  function openEntry(): void {
    if (!entry) return
    if (entry.type === 'file') onOpenFile(entry.path)
    else navigate(entry.path)
  }

  const isMultiSelect = !!entry && selected.size > 1 && selected.has(entry.path)
  const canOpen = !!entry && entry.type !== 'drive' && (!isMultiSelect || entry.type === 'file')
  const isPinned = !!entry && entry.type === 'folder' && (quickAccess?.pins ?? []).some((p) => p.path === entry.path)

  const sortByGroupByViewSubmenus = (
    <>
      <RadixContextMenu.Sub>
        <RadixContextMenu.SubTrigger className={itemClass}>
          View <ChevronRight className="ml-auto h-3.5 w-3.5" />
        </RadixContextMenu.SubTrigger>
        <RadixContextMenu.Portal>
          <RadixContextMenu.SubContent className={subContentClass} sideOffset={2} alignOffset={-4}>
            {VIEW_OPTIONS.map(({ mode, label }) => (
              <RadixContextMenu.Item
                key={mode}
                disabled={mode === 'gallery' && !isRealFolder(currentPath)}
                className={`${itemClass} ${mode === viewMode ? 'font-medium text-zinc-900' : ''}`}
                onSelect={() => setViewMode(mode as ViewMode)}
              >
                {label}
              </RadixContextMenu.Item>
            ))}
          </RadixContextMenu.SubContent>
        </RadixContextMenu.Portal>
      </RadixContextMenu.Sub>
      <RadixContextMenu.Sub>
        <RadixContextMenu.SubTrigger className={itemClass}>
          Sort by <ChevronRight className="ml-auto h-3.5 w-3.5" />
        </RadixContextMenu.SubTrigger>
        <RadixContextMenu.Portal>
          <RadixContextMenu.SubContent className={subContentClass} sideOffset={2} alignOffset={-4}>
            {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
              <RadixContextMenu.Item
                key={key}
                className={`${itemClass} ${key === sortKey ? 'font-medium text-zinc-900' : ''}`}
                onSelect={() => setSort(key)}
              >
                {SORT_LABELS[key]}
              </RadixContextMenu.Item>
            ))}
          </RadixContextMenu.SubContent>
        </RadixContextMenu.Portal>
      </RadixContextMenu.Sub>
      <RadixContextMenu.Sub>
        <RadixContextMenu.SubTrigger className={itemClass}>
          Group by <ChevronRight className="ml-auto h-3.5 w-3.5" />
        </RadixContextMenu.SubTrigger>
        <RadixContextMenu.Portal>
          <RadixContextMenu.SubContent className={subContentClass} sideOffset={2} alignOffset={-4}>
            {(Object.keys(GROUP_LABELS) as GroupKey[]).map((key) => (
              <RadixContextMenu.Item
                key={key}
                className={`${itemClass} ${key === groupBy ? 'font-medium text-zinc-900' : ''}`}
                onSelect={() => setGroupBy(key)}
              >
                {GROUP_LABELS[key]}
              </RadixContextMenu.Item>
            ))}
          </RadixContextMenu.SubContent>
        </RadixContextMenu.Portal>
      </RadixContextMenu.Sub>
    </>
  )

  return (
    <RadixContextMenu.Root>
      <RadixContextMenu.Trigger asChild onContextMenu={ensureSelected}>
        {children}
      </RadixContextMenu.Trigger>
      <RadixContextMenu.Portal>
        {/* Radix returns focus to the trigger on close by default, which
            steals focus from RenameInput's own autofocus when "Rename" was
            just selected — suppress it and let our own focus management win. */}
        <RadixContextMenu.Content className={contentClass} onCloseAutoFocus={(e) => e.preventDefault()}>
          {entry === null ? (
            <>
              {sortByGroupByViewSubmenus}
              <div className={separatorClass} />
              <RadixContextMenu.Item
                className={itemClass}
                onSelect={() => {
                  qc.invalidateQueries({ queryKey: ['browse', currentPath] })
                  qc.invalidateQueries({ queryKey: ['fs-gallery', currentPath] })
                }}
              >
                <RefreshCw className="h-4 w-4" /> Refresh
              </RadixContextMenu.Item>
              <div className={separatorClass} />
              <RadixContextMenu.Item
                className={itemClass}
                onSelect={() => fileOps.newFolder()}
                disabled={!fileOps.canNewFolder}
              >
                <FolderPlus className="h-4 w-4" /> New folder
              </RadixContextMenu.Item>
              <RadixContextMenu.Item className={itemClass} onSelect={fileOps.paste} disabled={!fileOps.canPaste}>
                <Copy className="h-4 w-4" /> Paste
              </RadixContextMenu.Item>
              <div className={separatorClass} />
              <RadixContextMenu.Item className={itemClass} onSelect={fileOps.undo}>
                <Undo2 className="h-4 w-4" /> Undo
              </RadixContextMenu.Item>
              <RadixContextMenu.Item className={itemClass} onSelect={fileOps.redo}>
                <Redo2 className="h-4 w-4" /> Redo
              </RadixContextMenu.Item>
            </>
          ) : entry.type === 'drive' ? (
            <>
              <RadixContextMenu.Item className={itemClass} onSelect={openEntry}>
                Open
              </RadixContextMenu.Item>
              <div className={separatorClass} />
              <RadixContextMenu.Item className={itemClass} onSelect={fileOps.copyPathSelected}>
                <Link2 className="h-4 w-4" /> Copy as path
              </RadixContextMenu.Item>
            </>
          ) : (
            <>
              {canOpen && (
                <>
                  <RadixContextMenu.Item className={itemClass} onSelect={openEntry}>
                    Open
                  </RadixContextMenu.Item>
                  {fileOps.canOpenWith && (
                    <RadixContextMenu.Item className={itemClass} onSelect={fileOps.openWithSelected}>
                      Open with…
                    </RadixContextMenu.Item>
                  )}
                  <div className={separatorClass} />
                </>
              )}
              <RadixContextMenu.Item className={itemClass} onSelect={fileOps.cut}>
                <Scissors className="h-4 w-4" /> Cut
              </RadixContextMenu.Item>
              <RadixContextMenu.Item className={itemClass} onSelect={fileOps.copy}>
                <Copy className="h-4 w-4" /> Copy
              </RadixContextMenu.Item>
              <RadixContextMenu.Item className={itemClass} onSelect={fileOps.renameSelected} disabled={isMultiSelect}>
                Rename
              </RadixContextMenu.Item>
              {!isMultiSelect && entry.type === 'folder' && (
                <RadixContextMenu.Item
                  className={itemClass}
                  onSelect={() =>
                    isPinned ? unpinMutation.mutate(entry.path) : pinMutation.mutate(entry.path)
                  }
                >
                  {isPinned ? (
                    <>
                      <StarOff className="h-4 w-4" /> Remove from Quick access
                    </>
                  ) : (
                    <>
                      <Star className="h-4 w-4" /> Pin to Quick access
                    </>
                  )}
                </RadixContextMenu.Item>
              )}
              <div className={separatorClass} />
              <RadixContextMenu.Item className={itemClass} onSelect={fileOps.revealSelected}>
                Reveal in File Explorer
              </RadixContextMenu.Item>
              <RadixContextMenu.Item className={itemClass} onSelect={fileOps.copyPathSelected}>
                <Link2 className="h-4 w-4" /> Copy as path
              </RadixContextMenu.Item>
              <RadixContextMenu.Sub>
                <RadixContextMenu.SubTrigger className={itemClass}>
                  <Send className="h-4 w-4" /> Send to <ChevronRight className="ml-auto h-3.5 w-3.5" />
                </RadixContextMenu.SubTrigger>
                <RadixContextMenu.Portal>
                  <RadixContextMenu.SubContent className={subContentClass} sideOffset={2} alignOffset={-4}>
                    <RadixContextMenu.Item className={itemClass} onSelect={fileOps.compressSelected}>
                      Compressed (zipped) folder
                    </RadixContextMenu.Item>
                    <RadixContextMenu.Item
                      className={itemClass}
                      onSelect={() => fileOps.createShortcut('desktop')}
                      disabled={!fileOps.canCreateShortcut}
                    >
                      Desktop (create shortcut)
                    </RadixContextMenu.Item>
                  </RadixContextMenu.SubContent>
                </RadixContextMenu.Portal>
              </RadixContextMenu.Sub>
              <RadixContextMenu.Item
                className={itemClass}
                onSelect={() => fileOps.createShortcut('here')}
                disabled={!fileOps.canCreateShortcut}
              >
                Create shortcut
              </RadixContextMenu.Item>
              {!isMultiSelect && (
                <RadixContextMenu.Item
                  className={itemClass}
                  onSelect={fileOps.compressSelected}
                  disabled={!fileOps.canCompress}
                >
                  <FileArchive className="h-4 w-4" /> Compress to ZIP
                </RadixContextMenu.Item>
              )}
              {fileOps.canExtract && (
                <RadixContextMenu.Item className={itemClass} onSelect={fileOps.extractSelected}>
                  <FileArchive className="h-4 w-4" /> Extract All…
                </RadixContextMenu.Item>
              )}
              <div className={separatorClass} />
              <RadixContextMenu.Item className={itemClass} onSelect={() => fileOps.deleteSelected(false)}>
                <Trash2 className="h-4 w-4" /> Delete
              </RadixContextMenu.Item>
              <div className={separatorClass} />
              <RadixContextMenu.Item className={itemClass} onSelect={fileOps.openPropertiesForSelection}>
                <Info className="h-4 w-4" /> Properties
              </RadixContextMenu.Item>
            </>
          )}
        </RadixContextMenu.Content>
      </RadixContextMenu.Portal>
    </RadixContextMenu.Root>
  )
}
