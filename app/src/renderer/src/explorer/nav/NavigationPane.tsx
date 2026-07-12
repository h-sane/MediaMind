import { Home } from 'lucide-react'
import { HOME_PATH, useExplorerStore } from '../../stores/explorer'
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

/** Left sidebar: Home above pinned Quick Access folders above the live
 * folder tree, rooted at This PC. */
export function NavigationPane(): React.JSX.Element {
  return (
    <aside className="flex h-full w-64 shrink-0 flex-col overflow-y-auto border-r border-zinc-200 bg-zinc-50">
      <HomeRow />
      <QuickAccess />
      <FolderTree />
    </aside>
  )
}
