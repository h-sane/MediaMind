import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import {
  ArrowDownAZ,
  ArrowUpAZ,
  CheckSquare,
  ClipboardPaste,
  Copy,
  FileArchive,
  FolderPlus,
  History,
  Info,
  Layers,
  LayoutList,
  PanelRight,
  PenLine,
  Scissors,
  Settings,
  Share2,
  SlidersHorizontal,
  SquareDashedMousePointer,
  Trash2
} from 'lucide-react'
import { isRealFolder, useExplorerStore } from '../../stores/explorer'
import type { GroupKey, SortKey } from '../../stores/explorer'
import { useFolderOptionsDialogStore } from '../../stores/folderOptionsDialog'
import { useRecentDeletionsDialogStore } from '../../stores/recentDeletionsDialog'
import { useSelectionStore } from '../../stores/selection'
import { useDirectoryListing } from '../content/useDirectoryListing'
import { useFileOps } from '../useFileOps'
import { GROUP_LABELS, SORT_LABELS, VIEW_OPTIONS } from './viewMenuData'

function ActionButton({
  icon: Icon,
  label,
  onClick,
  disabled,
  title
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  onClick?: () => void
  disabled?: boolean
  title?: string
}): React.JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title ?? label}
      className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-zinc-600 hover:bg-zinc-100 disabled:text-zinc-300 disabled:hover:bg-transparent"
    >
      <Icon className="h-4 w-4" />
      {label}
    </button>
  )
}

export function CommandBar(): React.JSX.Element {
  const currentPath = useExplorerStore((s) => s.currentPath)
  const viewMode = useExplorerStore((s) => s.viewMode)
  const setViewMode = useExplorerStore((s) => s.setViewMode)
  const sortKey = useExplorerStore((s) => s.sortKey)
  const sortDir = useExplorerStore((s) => s.sortDir)
  const setSort = useExplorerStore((s) => s.setSort)
  const groupBy = useExplorerStore((s) => s.groupBy)
  const setGroupBy = useExplorerStore((s) => s.setGroupBy)
  const filtersOpen = useExplorerStore((s) => s.filtersOpen)
  const toggleFiltersOpen = useExplorerStore((s) => s.toggleFiltersOpen)
  const previewPaneOpen = useExplorerStore((s) => s.previewPaneOpen)
  const togglePreviewPane = useExplorerStore((s) => s.togglePreviewPane)
  const fileOps = useFileOps()
  const { entries } = useDirectoryListing()
  const openRecentDeletions = useRecentDeletionsDialogStore((s) => s.open)
  const openFolderOptions = useFolderOptionsDialogStore((s) => s.open)
  const selectAll = useSelectionStore((s) => s.selectAll)
  const invertSelection = useSelectionStore((s) => s.invertSelection)
  const clearSelection = useSelectionStore((s) => s.clear)

  const ActiveViewIcon = VIEW_OPTIONS.find((v) => v.mode === viewMode)?.icon ?? LayoutList
  const orderedPaths = entries.map((e) => e.path)

  return (
    <div className="flex items-center justify-between border-b border-zinc-200 px-3 py-1.5">
      <div className="flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto">
        <ActionButton icon={FolderPlus} label="New" onClick={fileOps.newFolder} disabled={!fileOps.canNewFolder} />
        <div className="mx-1 h-4 w-px bg-zinc-200" />
        <ActionButton icon={Scissors} label="Cut" onClick={fileOps.cut} disabled={!fileOps.canCutCopy} />
        <ActionButton icon={Copy} label="Copy" onClick={fileOps.copy} disabled={!fileOps.canCutCopy} />
        <ActionButton icon={ClipboardPaste} label="Paste" onClick={fileOps.paste} disabled={!fileOps.canPaste} />
        <div className="mx-1 h-4 w-px bg-zinc-200" />
        <ActionButton icon={PenLine} label="Rename" onClick={fileOps.renameSelected} disabled={!fileOps.canRename} />
        <ActionButton
          icon={FileArchive}
          label="Compress"
          onClick={fileOps.compressSelected}
          disabled={!fileOps.canCompress}
        />
        <ActionButton
          icon={FileArchive}
          label="Extract"
          onClick={fileOps.extractSelected}
          disabled={!fileOps.canExtract}
        />
        <ActionButton
          icon={Share2}
          label="Share"
          disabled
          title="Share is not available for desktop apps on Windows"
        />
        <ActionButton
          icon={Trash2}
          label="Delete"
          onClick={() => fileOps.deleteSelected(false)}
          disabled={!fileOps.canDelete}
        />
        <div className="mx-1 h-4 w-px bg-zinc-200" />
        <ActionButton
          icon={Info}
          label="Properties"
          onClick={fileOps.openPropertiesForSelection}
          disabled={!fileOps.canProperties}
        />
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-zinc-600 hover:bg-zinc-100">
              {sortDir === 'asc' ? <ArrowDownAZ className="h-4 w-4" /> : <ArrowUpAZ className="h-4 w-4" />}
              Sort: {SORT_LABELS[sortKey]}
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="end"
              sideOffset={4}
              className="z-50 w-44 rounded-lg border border-zinc-200 bg-white py-1 text-sm shadow-lg"
            >
              {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
                <DropdownMenu.Item
                  key={key}
                  onSelect={() => setSort(key)}
                  className={`cursor-pointer px-3 py-1.5 outline-none hover:bg-zinc-100 ${
                    key === sortKey ? 'font-medium text-zinc-900' : 'text-zinc-600'
                  }`}
                >
                  {SORT_LABELS[key]}
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>

        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              className={`flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm hover:bg-zinc-100 ${
                groupBy !== 'none' ? 'text-blue-600' : 'text-zinc-600'
              }`}
            >
              <Layers className="h-4 w-4" />
              Group by: {GROUP_LABELS[groupBy]}
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="end"
              sideOffset={4}
              className="z-50 w-44 rounded-lg border border-zinc-200 bg-white py-1 text-sm shadow-lg"
            >
              {(Object.keys(GROUP_LABELS) as GroupKey[]).map((key) => (
                <DropdownMenu.Item
                  key={key}
                  onSelect={() => setGroupBy(key)}
                  className={`cursor-pointer px-3 py-1.5 outline-none hover:bg-zinc-100 ${
                    key === groupBy ? 'font-medium text-zinc-900' : 'text-zinc-600'
                  }`}
                >
                  {GROUP_LABELS[key]}
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>

        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-zinc-600 hover:bg-zinc-100">
              <ActiveViewIcon className="h-4 w-4" />
              View
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="end"
              sideOffset={4}
              className="z-50 w-40 rounded-lg border border-zinc-200 bg-white py-1 text-sm shadow-lg"
            >
              {VIEW_OPTIONS.map(({ mode, label, icon: Icon }) => (
                <DropdownMenu.Item
                  key={mode}
                  disabled={mode === 'gallery' && !isRealFolder(currentPath)}
                  onSelect={() => setViewMode(mode)}
                  className={`flex cursor-pointer items-center gap-2 px-3 py-1.5 outline-none hover:bg-zinc-100 data-[disabled]:pointer-events-none data-[disabled]:text-zinc-300 ${
                    mode === viewMode ? 'font-medium text-zinc-900' : 'text-zinc-600'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>

        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-zinc-600 hover:bg-zinc-100">
              <SquareDashedMousePointer className="h-4 w-4" />
              Select
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="end"
              sideOffset={4}
              className="z-50 w-40 rounded-lg border border-zinc-200 bg-white py-1 text-sm shadow-lg"
            >
              <DropdownMenu.Item
                onSelect={() => selectAll(orderedPaths)}
                className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-zinc-600 outline-none hover:bg-zinc-100"
              >
                <CheckSquare className="h-4 w-4" /> Select all
              </DropdownMenu.Item>
              <DropdownMenu.Item
                onSelect={clearSelection}
                className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-zinc-600 outline-none hover:bg-zinc-100"
              >
                Select none
              </DropdownMenu.Item>
              <DropdownMenu.Item
                onSelect={() => invertSelection(orderedPaths)}
                className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-zinc-600 outline-none hover:bg-zinc-100"
              >
                Invert selection
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>

        <button
          type="button"
          onClick={toggleFiltersOpen}
          title="Filters"
          aria-pressed={filtersOpen}
          className={`flex items-center px-1.5 py-1.5 ${
            filtersOpen ? 'text-blue-600' : 'text-zinc-500 hover:text-zinc-700'
          }`}
        >
          <SlidersHorizontal className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={togglePreviewPane}
          title="Preview pane"
          aria-pressed={previewPaneOpen}
          className={`flex items-center px-1.5 py-1.5 ${
            previewPaneOpen ? 'text-blue-600' : 'text-zinc-500 hover:text-zinc-700'
          }`}
        >
          <PanelRight className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={openRecentDeletions}
          title="Recent deletions"
          className="flex items-center px-1.5 py-1.5 text-zinc-500 hover:text-zinc-700"
        >
          <History className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={openFolderOptions}
          title="Folder Options"
          className="flex items-center px-1.5 py-1.5 text-zinc-500 hover:text-zinc-700"
        >
          <Settings className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
