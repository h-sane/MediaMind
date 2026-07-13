import { Home } from 'lucide-react'
import { HOME_PATH, useExplorerStore } from '../../stores/explorer'
import { TOOL_RAIL_MAX, TOOL_RAIL_MIN, usePaneLayoutStore } from '../../stores/paneLayout'
import { PaneResizer } from '../layout/PaneResizer'
import { ToolRail } from '../tools/ToolRail'
import { FolderTree } from './FolderTree'
import { QuickAccess } from './QuickAccess'

/** The Home landing page (Phase N) — a fixed row above Quick access, not a
 * pin itself (can't be unpinned/reordered). */
function HomeRow(): React.JSX.Element {
  const navigate = useExplorerStore((s) => s.navigate)
  const isCurrent = useExplorerStore((s) => s.currentPath === HOME_PATH)

  return (
    <button
      type="button"
      onClick={() => navigate(HOME_PATH)}
      className={`flex w-full items-center gap-1.5 py-1 pl-3 pr-2 text-left text-sm ${
        isCurrent ? 'bg-blue-50 text-blue-700' : 'text-zinc-700 hover:bg-zinc-100'
      }`}
    >
      <Home className="h-4 w-4 shrink-0 text-zinc-400" />
      <span className="truncate">Home</span>
    </button>
  )
}

/** Left sidebar, split top/bottom: Home, pinned Quick Access folders, and the
 * live folder tree (rooted at This PC) scroll in the top half; the media
 * tools (dedupe, faces — see `ToolRail`) sit pinned in the bottom half,
 * reusing the space the tree otherwise leaves empty. Both the pane's overall
 * width and the height of its own bottom (Tools) section are drag-resizable
 * (`stores/paneLayout.ts`), matching real Explorer's own resizable panes. */
export function NavigationPane(): React.JSX.Element {
  const navPaneWidth = usePaneLayoutStore((s) => s.navPaneWidth)
  const toolRailHeight = usePaneLayoutStore((s) => s.toolRailHeight)
  const setToolRailHeight = usePaneLayoutStore((s) => s.setToolRailHeight)

  return (
    <aside
      style={{ width: navPaneWidth }}
      className="flex h-full shrink-0 flex-col border-r border-zinc-200 bg-zinc-50"
    >
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        <HomeRow />
        <QuickAccess />
        <FolderTree />
      </div>
      <PaneResizer
        orientation="horizontal"
        getValue={() => usePaneLayoutStore.getState().toolRailHeight}
        setValue={setToolRailHeight}
        min={TOOL_RAIL_MIN}
        max={TOOL_RAIL_MAX}
        invert
      />
      <div style={{ height: toolRailHeight }} className="shrink-0 overflow-y-auto">
        <ToolRail />
      </div>
    </aside>
  )
}
