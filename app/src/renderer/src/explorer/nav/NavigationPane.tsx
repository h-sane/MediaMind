import { Download, Globe2, Home, Sparkles, Users } from 'lucide-react'
import { HOME_PATH, isRealFolder, useExplorerStore } from '../../stores/explorer'
import { useUpdateStore } from '../../stores/update'
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

/** People as a first-class place near Home — opens the Facial Recognition
 * tool (its default sub-view is the People grid) for the current folder.
 * Folder-scoped like the tool itself; a global cross-folder People view is a
 * later feature (needs a library concept), so this is disabled off a folder. */
function PeopleRow(): React.JSX.Element {
  const currentPath = useExplorerStore((s) => s.currentPath)
  const toolMode = useExplorerStore((s) => s.toolMode)
  const setToolMode = useExplorerStore((s) => s.setToolMode)
  const folderOpen = isRealFolder(currentPath)
  const isActive = toolMode === 'faces'

  return (
    <button
      type="button"
      disabled={!folderOpen}
      onClick={() => setToolMode(isActive ? 'none' : 'faces')}
      title={folderOpen ? 'People in this folder' : 'Open a folder to see its people'}
      className={`flex w-full items-center gap-1.5 py-1 pl-3 pr-2 text-left text-sm disabled:text-zinc-300 ${
        isActive ? 'bg-blue-50 text-blue-700' : 'text-zinc-700 hover:bg-zinc-100'
      }`}
    >
      <Users className={`h-4 w-4 shrink-0 ${isActive ? 'text-blue-600' : 'text-zinc-400'}`} />
      <span className="truncate">People</span>
    </button>
  )
}

/** A person identity that can span multiple registered libraries (different
 * drives/mounts) — always available, unlike `PeopleRow` which needs a folder
 * open. Not folder-scoped at all, so it just toggles `toolMode` without
 * touching `currentPath`. */
function GlobalPeopleRow(): React.JSX.Element {
  const toolMode = useExplorerStore((s) => s.toolMode)
  const setToolMode = useExplorerStore((s) => s.setToolMode)
  const isActive = toolMode === 'global-people'

  return (
    <button
      type="button"
      onClick={() => setToolMode(isActive ? 'none' : 'global-people')}
      title="People across all your libraries"
      className={`flex w-full items-center gap-1.5 py-1 pl-3 pr-2 text-left text-sm ${
        isActive ? 'bg-blue-50 text-blue-700' : 'text-zinc-700 hover:bg-zinc-100'
      }`}
    >
      <Globe2 className={`h-4 w-4 shrink-0 ${isActive ? 'text-blue-600' : 'text-zinc-400'}`} />
      <span className="truncate">People (All Libraries)</span>
    </button>
  )
}

/** Cross-library review queue: cross-library link suggestions and physical
 * move suggestions, both requiring explicit confirmation. Not folder-scoped,
 * same reasoning as `GlobalPeopleRow` — distinct from the existing
 * folder-scoped `suggestions` toolMode (duplicates + per-library pending
 * face matches). */
function GlobalSuggestionsRow(): React.JSX.Element {
  const toolMode = useExplorerStore((s) => s.toolMode)
  const setToolMode = useExplorerStore((s) => s.setToolMode)
  const isActive = toolMode === 'global-suggestions'

  return (
    <button
      type="button"
      onClick={() => setToolMode(isActive ? 'none' : 'global-suggestions')}
      title="Cross-library suggestions"
      className={`flex w-full items-center gap-1.5 py-1 pl-3 pr-2 text-left text-sm ${
        isActive ? 'bg-blue-50 text-blue-700' : 'text-zinc-700 hover:bg-zinc-100'
      }`}
    >
      <Sparkles className={`h-4 w-4 shrink-0 ${isActive ? 'text-blue-600' : 'text-zinc-400'}`} />
      <span className="truncate">Suggestions (All Libraries)</span>
    </button>
  )
}

/** Persistent update entry at the very bottom of the sidebar. Unlike the
 * top-right bubble (dismissable), this stays for as long as an update is
 * pending, so the user always has a way back to it. Hidden when there's no
 * update. */
function UpdateSidebarButton(): React.JSX.Element | null {
  const phase = useUpdateStore((s) => s.phase)
  const version = useUpdateStore((s) => s.version)
  const percent = useUpdateStore((s) => s.percent)
  const download = useUpdateStore((s) => s.download)
  const install = useUpdateStore((s) => s.install)

  if (phase === null) return null

  const label =
    phase === 'downloading'
      ? `Downloading ${percent}%`
      : phase === 'downloaded'
        ? 'Restart & install'
        : phase === 'error'
          ? 'Update failed — retry'
          : `Update to ${version}`
  const onClick =
    phase === 'downloaded' ? install : phase === 'downloading' ? undefined : download

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={phase === 'downloading'}
      title={label}
      className="flex w-full items-center gap-1.5 border-t border-zinc-200 bg-emerald-50 py-1.5 pl-3 pr-2 text-left text-sm font-medium text-emerald-700 hover:bg-emerald-100 disabled:cursor-default disabled:hover:bg-emerald-50"
    >
      <Download className="h-4 w-4 shrink-0" />
      <span className="truncate">{label}</span>
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
        <PeopleRow />
        <GlobalPeopleRow />
        <GlobalSuggestionsRow />
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
      <UpdateSidebarButton />
    </aside>
  )
}
