import { Folder, Home, Laptop, Plus, X } from 'lucide-react'
import { HOME_PATH, tabTitle, useExplorerStore } from '../../stores/explorer'

/** Explorer's tab strip (Phase K). Every tab already mirrors the full
 * per-folder state `stores/explorer.ts` used to carry as a single global —
 * this component only needs the tab list itself plus the switch/new/close
 * actions; everything below it (TopChrome, ContentPane, ...) keeps reading
 * `useExplorerStore`'s top-level fields and automatically reflects whichever
 * tab is active. */
export function TabStrip(): React.JSX.Element {
  const tabs = useExplorerStore((s) => s.tabs)
  const activeTabId = useExplorerStore((s) => s.activeTabId)
  const switchTab = useExplorerStore((s) => s.switchTab)
  const newTab = useExplorerStore((s) => s.newTab)
  const closeTab = useExplorerStore((s) => s.closeTab)

  return (
    <div className="flex items-center gap-0.5 border-b border-zinc-200 bg-zinc-50 px-1.5 pt-1.5">
      {tabs.map((tab) => {
        const isActive = tab.id === activeTabId
        return (
          <div
            key={tab.id}
            role="tab"
            aria-selected={isActive}
            onClick={() => switchTab(tab.id)}
            onMouseDown={(e) => {
              // Middle-click closes the tab, matching browser/Explorer tab strips.
              if (e.button === 1) {
                e.preventDefault()
                closeTab(tab.id)
              }
            }}
            className={`group flex h-8 max-w-56 min-w-0 cursor-default items-center gap-1.5 rounded-t-md border border-b-0 px-2.5 text-sm ${
              isActive
                ? 'border-zinc-200 bg-white text-zinc-900'
                : 'border-transparent text-zinc-500 hover:bg-zinc-100'
            }`}
          >
            {tab.currentPath === null ? (
              <Laptop className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
            ) : tab.currentPath === HOME_PATH ? (
              <Home className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
            ) : (
              <Folder className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
            )}
            <span className="min-w-0 flex-1 truncate">{tabTitle(tab.currentPath)}</span>
            {tabs.length > 1 && (
              <button
                type="button"
                aria-label="Close tab"
                onClick={(e) => {
                  e.stopPropagation()
                  closeTab(tab.id)
                }}
                className={`flex h-4 w-4 shrink-0 items-center justify-center rounded text-zinc-400 hover:bg-zinc-200 hover:text-zinc-700 ${
                  isActive ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                }`}
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
        )
      })}
      <button
        type="button"
        aria-label="New tab"
        title="New tab (Ctrl+T)"
        onClick={() => newTab()}
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-100"
      >
        <Plus className="h-4 w-4" />
      </button>
    </div>
  )
}
