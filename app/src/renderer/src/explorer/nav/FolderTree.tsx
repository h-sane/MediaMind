import { useRef } from 'react'
import { asyncDataLoaderFeature, hotkeysCoreFeature, selectionFeature } from '@headless-tree/core'
import { useTree } from '@headless-tree/react'
import { ChevronRight, Folder, HardDrive, Laptop } from 'lucide-react'
import { api } from '../../api/client'
import { useExplorerStore } from '../../stores/explorer'
import { useFolderDropTarget } from '../dnd/useFolderDropTarget'

const ROOT_ID = '__this_pc__'

function basename(path: string): string {
  const trimmed = path.replace(/[\\/]+$/, '')
  const idx = Math.max(trimmed.lastIndexOf('\\'), trimmed.lastIndexOf('/'))
  return idx === -1 ? trimmed : trimmed.slice(idx + 1)
}

interface TreeRowProps {
  id: string
  isRoot: boolean
  isDrive: boolean
  isCurrent: boolean
  isExpanded: boolean
  isLoading: boolean
  level: number
  name: string
  props: Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any -- passthrough of @headless-tree's own loosely-typed item.getProps()
  onClick: (e: React.MouseEvent) => void
  onToggle: (e: React.MouseEvent) => void
}

/** A single tree node — a drop target for moving/copying into that folder
 * (not the synthetic "This PC" root, which isn't a real path). */
function TreeRow({
  id,
  isRoot,
  isDrive,
  isCurrent,
  isExpanded,
  isLoading,
  level,
  name,
  props,
  onClick,
  onToggle
}: TreeRowProps): React.JSX.Element {
  const { ref: dropRef, isOver } = useFolderDropTarget(isRoot ? null : id)

  return (
    <div
      {...props}
      ref={dropRef}
      onClick={onClick}
      style={{ paddingLeft: `${level * 16 + 8}px` }}
      className={`flex cursor-pointer items-center gap-1.5 py-1 pr-2 ${
        isOver ? 'bg-blue-100 ring-1 ring-inset ring-blue-400' : isCurrent ? 'bg-blue-50 text-blue-700' : 'text-zinc-700 hover:bg-zinc-100'
      }`}
    >
      <button
        type="button"
        onClick={onToggle}
        className="flex h-4 w-4 shrink-0 items-center justify-center text-zinc-400"
        aria-label={isExpanded ? 'Collapse' : 'Expand'}
      >
        <ChevronRight className={`h-3.5 w-3.5 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
      </button>
      {isRoot ? (
        <Laptop className="h-4 w-4 shrink-0 text-zinc-400" />
      ) : isDrive ? (
        <HardDrive className="h-4 w-4 shrink-0 text-zinc-400" />
      ) : (
        <Folder className="h-4 w-4 shrink-0 text-zinc-400" />
      )}
      <span className="truncate">{name}</span>
      {isLoading && <span className="ml-1 text-[10px] text-zinc-300">…</span>}
    </div>
  )
}

/**
 * Nav-pane folder tree, rooted at a synthetic "This PC" node whose children
 * are the real OS drives. Every other node is an absolute path; children are
 * loaded lazily from `/v1/fs/list` the first time a folder is expanded.
 * Headless Tree renders a flat, already-indented list — no manual recursion.
 */
export function FolderTree(): React.JSX.Element {
  const currentPath = useExplorerStore((s) => s.currentPath)
  const navigate = useExplorerStore((s) => s.navigate)
  const driveLabels = useRef(new Map<string, string>())

  const tree = useTree<string>({
    rootItemId: ROOT_ID,
    initialState: { expandedItems: [ROOT_ID] },
    getItemName: (item) => item.getItemData(),
    isItemFolder: () => true,
    dataLoader: {
      getItem: async (itemId) => {
        if (itemId === ROOT_ID) return 'This PC'
        return driveLabels.current.get(itemId) ?? basename(itemId)
      },
      getChildren: async (itemId) => {
        if (itemId === ROOT_ID) {
          const drives = await api.fs.drives()
          for (const d of drives) driveLabels.current.set(d.path, d.label)
          return drives.map((d) => d.path)
        }
        const dir = await api.fs.list(itemId)
        return dir.folders.map((f) => f.path)
      }
    },
    indent: 16,
    features: [asyncDataLoaderFeature, selectionFeature, hotkeysCoreFeature]
  })

  return (
    <div {...tree.getContainerProps()} className="select-none overflow-y-auto py-2 text-sm">
      {tree.getItems().map((item) => {
        const id = item.getId()
        const isRoot = id === ROOT_ID
        const isDrive = driveLabels.current.has(id)
        const isCurrent = !isRoot && id === currentPath
        const props = item.getProps()

        return (
          <TreeRow
            key={id}
            id={id}
            isRoot={isRoot}
            isDrive={isDrive}
            isCurrent={isCurrent}
            isExpanded={item.isExpanded()}
            isLoading={item.isLoading()}
            level={item.getItemMeta().level}
            name={item.getItemName()}
            props={props}
            onClick={(e) => {
              props.onClick?.(e)
              navigate(isRoot ? null : id)
            }}
            onToggle={(e) => {
              e.stopPropagation()
              if (item.isExpanded()) item.collapse()
              else item.expand()
            }}
          />
        )
      })}
    </div>
  )
}
