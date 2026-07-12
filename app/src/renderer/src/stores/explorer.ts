import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { useFolderViewPrefsStore } from './folderViewPrefs'

export type ViewMode = 'icons' | 'list' | 'details' | 'tiles' | 'content' | 'gallery'
export type SortKey = 'name' | 'date' | 'size' | 'type' | 'created' | 'accessed' | 'attributes'
export type SortDir = 'asc' | 'desc'
export type FilterType = 'all' | 'image' | 'gif' | 'video' | 'audio'
export type FilterDate = 'any' | 'today' | 'week' | 'month' | 'older'
export type FilterSize = 'any' | 'small' | 'medium' | 'large'
/** A parallel, independent feature from Sort (see `content/grouping.ts`) —
 * same field vocabulary as `SortKey` plus "(None)". */
export type GroupKey = SortKey | 'none'
/** The four Explorer icon-size tiers within "Large icons" view (`Ctrl+Shift+1-4`);
 * every other view mode (List/Details/Tiles/Content) is unaffected by this. */
export type IconSize = 'extra-large' | 'large' | 'medium' | 'small'

/**
 * Sentinel for the Home landing page (Phase N) — a third root alongside
 * `null` ("This PC"). Never a real filesystem path and never sent to the
 * backend; every `currentPath` consumer that reads/writes real folders must
 * treat it the same as having no folder open (see `isRealFolder`).
 */
export const HOME_PATH = 'mediamind:home'

/** True for an actual filesystem path — false for both "This PC" (`null`)
 * and the Home sentinel. Narrows `string | null` to `string` so callers can
 * pass the result straight to path-taking APIs. */
export function isRealFolder(path: string | null): path is string {
  return path !== null && path !== HOME_PATH
}

/**
 * Windows-style "go up one level". `null` means "This PC" (the drive list) —
 * going up from a drive root (`C:\`) lands there; going up further is a no-op.
 */
export function parentPath(path: string): string | null {
  const trimmed = path.replace(/[\\/]+$/, '')
  const lastSep = Math.max(trimmed.lastIndexOf('\\'), trimmed.lastIndexOf('/'))
  if (lastSep === -1) return null
  const parent = trimmed.slice(0, lastSep)
  return /^[A-Za-z]:$/.test(parent) ? parent + '\\' : parent
}

/** A tab's display title — "Home", the last path segment, or "This PC" for
 * the drive-list root (matches `Breadcrumb.tsx`'s own null-path label). */
export function tabTitle(path: string | null): string {
  if (path === null) return 'This PC'
  if (path === HOME_PATH) return 'Home'
  const trimmed = path.replace(/[\\/]+$/, '')
  const lastSep = Math.max(trimmed.lastIndexOf('\\'), trimmed.lastIndexOf('/'))
  return lastSep === -1 ? trimmed : trimmed.slice(lastSep + 1)
}

/** Everything one tab tracks — the entire state shape this store had before
 * Phase K (tabs) existed. Kept as its own type so a tab's internal shape
 * stays identical to "today's per-folder model" (per the Explorer-parity
 * plan), just multiplied by however many tabs are open. */
interface TabFields {
  /** null = "This PC" (drive list) */
  currentPath: string | null
  history: (string | null)[]
  future: (string | null)[]
  viewMode: ViewMode
  sortKey: SortKey
  sortDir: SortDir

  /** Live filter over the current folder's entries. Search and the filter
   * chips are per-folder-view state (like Explorer's own search box), not
   * persisted across navigation — see setNavState. Per-folder *persistence*
   * across sessions is out of scope here (Phase D, same as view-mode/sort). */
  searchQuery: string
  filtersOpen: boolean
  filterType: FilterType
  filterDate: FilterDate
  filterSize: FilterSize
  previewPaneOpen: boolean

  /** Phase I — recursive/cross-subfolder search. When active, the content
   * pane shows a flat search-results pseudo-listing (see
   * `content/useDirectoryListing.ts`) instead of `recursiveSearchRoot`'s own
   * contents. `recursiveSearchRoot` is captured at the moment the search is
   * launched (rather than tracking `currentPath` live) so the results don't
   * shift under the user if something else changes the current path. */
  recursiveSearchActive: boolean
  recursiveSearchRoot: string | null

  /** Group-by (Phase J) — a parallel, independent feature from Sort. Global
   * *per-tab* session state, not per-folder-persisted like `viewMode`/
   * `sortKey` (see `folderPrefState`); Explorer scopes it per-folder too,
   * but doing the same here would mean widening `folderViewPrefs.ts`'s
   * persisted shape and migration, which nothing so far has asked for. */
  groupBy: GroupKey
  iconSize: IconSize
  /** How many columns the active content view is currently laying out —
   * reported by whichever view is mounted (grid views measure it via
   * ResizeObserver; single-column views just report 1) so arrow-key
   * up/down can jump by a full row instead of one entry. Pure transient UI
   * geometry, not persisted. */
  contentColumns: number
}

/** One Explorer tab — `TabFields` plus a stable identity. */
export interface Tab extends TabFields {
  id: string
}

const CLEARED_NAV_STATE: Partial<TabFields> = {
  searchQuery: '',
  filterType: 'all',
  filterDate: 'any',
  filterSize: 'any',
  recursiveSearchActive: false,
  recursiveSearchRoot: null
}

/** A folder with a saved pref (Phase D) applies it; one without falls back
 * to whatever view/sort is already active — "last used" carries over,
 * matching Explorer's own behavior for folders you haven't customized. */
function folderPrefState(path: string | null): Partial<Pick<TabFields, 'viewMode' | 'sortKey' | 'sortDir'>> {
  if (!isRealFolder(path)) return {}
  const pref = useFolderViewPrefsStore.getState().prefs[path]
  return pref ? { viewMode: pref.viewMode, sortKey: pref.sortKey, sortDir: pref.sortDir } : {}
}

function makeTabId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function makeTab(path: string | null = HOME_PATH): Tab {
  return {
    id: makeTabId(),
    currentPath: path,
    history: [],
    future: [],
    viewMode: 'icons',
    sortKey: 'name',
    sortDir: 'asc',
    searchQuery: '',
    filtersOpen: false,
    filterType: 'all',
    filterDate: 'any',
    filterSize: 'any',
    previewPaneOpen: false,
    recursiveSearchActive: false,
    recursiveSearchRoot: null,
    groupBy: 'none',
    iconSize: 'large',
    contentColumns: 1,
    ...folderPrefState(path)
  }
}

function omitId({ id: _id, ...fields }: Tab): TabFields {
  return fields
}

interface ExplorerStore extends TabFields {
  tabs: Tab[]
  activeTabId: string

  navigate: (path: string | null) => void
  back: () => void
  forward: () => void
  up: () => void
  setViewMode: (mode: ViewMode) => void
  setSort: (key: SortKey) => void
  setSearchQuery: (query: string) => void
  toggleFiltersOpen: () => void
  setFilterType: (type: FilterType) => void
  setFilterDate: (date: FilterDate) => void
  setFilterSize: (size: FilterSize) => void
  togglePreviewPane: () => void
  startRecursiveSearch: () => void
  stopRecursiveSearch: () => void
  setGroupBy: (key: GroupKey) => void
  setIconSize: (size: IconSize) => void
  setContentColumns: (columns: number) => void

  /** Opens a new tab — defaults to duplicating the active tab's current
   * folder, matching Explorer's own `Ctrl+T` — and makes it active. */
  newTab: (path?: string | null) => void
  /** Closes a tab. Closing the last remaining tab is a no-op: unlike a real
   * Explorer window, this app has no OS-level multi-window concept for the
   * content pane, so there must always be at least one tab open. Activates
   * whichever tab was immediately to the right of the closed one (or the
   * new last tab, if the closed tab was rightmost) — the same convention
   * Explorer/Chrome tab strips use. */
  closeTab: (id: string) => void
  switchTab: (id: string) => void
  /** `Ctrl+Tab` / `Ctrl+Shift+Tab` — cycles the active tab forward/backward, wrapping. */
  cycleTab: (direction: 1 | -1) => void
}

/** Applies `patch` to the active tab's entry in `tabs` *and* to the
 * top-level mirrored fields every pre-existing consumer already reads (e.g.
 * `useExplorerStore(s => s.currentPath)`). This mirroring is what lets
 * Phase K introduce multiple tabs without touching any of the ~20 files
 * that read per-folder state off this store — they keep seeing a flat
 * `ExplorerStore` that always reflects whichever tab is active. */
function syncActiveTab(
  set: (partial: Partial<ExplorerStore>) => void,
  get: () => ExplorerStore,
  patch: Partial<TabFields>
): void {
  const { tabs, activeTabId } = get()
  const nextTabs = tabs.map((t) => (t.id === activeTabId ? { ...t, ...patch } : t))
  set({ ...patch, tabs: nextTabs })
}

const initialTab = makeTab(HOME_PATH)

export const useExplorerStore = create<ExplorerStore>()(
  persist(
    (set, get) => ({
      tabs: [initialTab],
      activeTabId: initialTab.id,
      ...omitId(initialTab),

      navigate: (path) => {
        const { currentPath, history } = get()
        if (path === currentPath) return
        syncActiveTab(set, get, {
          currentPath: path,
          history: [...history, currentPath],
          future: [],
          ...CLEARED_NAV_STATE,
          ...folderPrefState(path)
        })
      },

      back: () => {
        const { history, currentPath, future } = get()
        if (history.length === 0) return
        const prev = history[history.length - 1]
        syncActiveTab(set, get, {
          currentPath: prev,
          history: history.slice(0, -1),
          future: [currentPath, ...future],
          ...CLEARED_NAV_STATE,
          ...folderPrefState(prev)
        })
      },

      forward: () => {
        const { future, currentPath, history } = get()
        if (future.length === 0) return
        const next = future[0]
        syncActiveTab(set, get, {
          currentPath: next,
          future: future.slice(1),
          history: [...history, currentPath],
          ...CLEARED_NAV_STATE,
          ...folderPrefState(next)
        })
      },

      up: () => {
        const { currentPath } = get()
        if (!isRealFolder(currentPath)) return
        get().navigate(parentPath(currentPath))
      },

      setViewMode: (viewMode) => {
        syncActiveTab(set, get, { viewMode })
        const { currentPath, sortKey, sortDir } = get()
        if (isRealFolder(currentPath)) useFolderViewPrefsStore.getState().setPref(currentPath, { viewMode, sortKey, sortDir })
      },

      setSort: (key) => {
        const s = get()
        const sortDir = s.sortKey === key ? (s.sortDir === 'asc' ? 'desc' : 'asc') : 'asc'
        if (isRealFolder(s.currentPath)) {
          useFolderViewPrefsStore.getState().setPref(s.currentPath, { viewMode: s.viewMode, sortKey: key, sortDir })
        }
        syncActiveTab(set, get, { sortKey: key, sortDir })
      },

      setSearchQuery: (searchQuery) => syncActiveTab(set, get, { searchQuery }),
      toggleFiltersOpen: () => syncActiveTab(set, get, { filtersOpen: !get().filtersOpen }),
      setFilterType: (filterType) => syncActiveTab(set, get, { filterType }),
      setFilterDate: (filterDate) => syncActiveTab(set, get, { filterDate }),
      setFilterSize: (filterSize) => syncActiveTab(set, get, { filterSize }),
      togglePreviewPane: () => syncActiveTab(set, get, { previewPaneOpen: !get().previewPaneOpen }),

      startRecursiveSearch: () => {
        const { currentPath, searchQuery } = get()
        // Neither "This PC" nor Home (currentPath not a real folder) has a
        // single folder to search below, and an empty query has nothing to
        // match — both are no-ops.
        if (!isRealFolder(currentPath) || !searchQuery.trim()) return
        syncActiveTab(set, get, { recursiveSearchActive: true, recursiveSearchRoot: currentPath })
      },
      stopRecursiveSearch: () => syncActiveTab(set, get, { recursiveSearchActive: false, recursiveSearchRoot: null }),

      setGroupBy: (groupBy) => syncActiveTab(set, get, { groupBy }),
      setIconSize: (iconSize) => syncActiveTab(set, get, { iconSize }),
      setContentColumns: (contentColumns) => syncActiveTab(set, get, { contentColumns }),

      newTab: (path) => {
        const tab = makeTab(path === undefined ? get().currentPath : path)
        set((s) => ({ tabs: [...s.tabs, tab], activeTabId: tab.id, ...omitId(tab) }))
      },

      closeTab: (id) => {
        const { tabs, activeTabId } = get()
        if (tabs.length <= 1) return
        const idx = tabs.findIndex((t) => t.id === id)
        if (idx === -1) return
        const nextTabs = tabs.filter((t) => t.id !== id)
        if (activeTabId !== id) {
          set({ tabs: nextTabs })
          return
        }
        const neighbor = nextTabs[idx] ?? nextTabs[nextTabs.length - 1]
        set({ tabs: nextTabs, activeTabId: neighbor.id, ...omitId(neighbor) })
      },

      switchTab: (id) => {
        const { tabs, activeTabId } = get()
        if (id === activeTabId) return
        const tab = tabs.find((t) => t.id === id)
        if (!tab) return
        set({ activeTabId: id, ...omitId(tab) })
      },

      cycleTab: (direction) => {
        const { tabs, activeTabId } = get()
        if (tabs.length <= 1) return
        const idx = tabs.findIndex((t) => t.id === activeTabId)
        const nextIdx = (idx + direction + tabs.length) % tabs.length
        get().switchTab(tabs[nextIdx].id)
      }
    }),
    {
      name: 'mediamind-explorer-tabs',
      // Only the tab identity + folder survive a restart — everything else
      // (history, search, filters, view/sort) is re-derived fresh per tab
      // the same way a single navigate() already re-derives it today
      // (view/sort from folderViewPrefs.ts, the rest defaulted/cleared).
      partialize: (s) => ({
        tabs: s.tabs.map((t) => ({ id: t.id, currentPath: t.currentPath })),
        activeTabId: s.activeTabId
      }),
      merge: (persistedState, currentState) => {
        const persisted = persistedState as
          | { tabs?: { id: string; currentPath: string | null }[]; activeTabId?: string }
          | null
          | undefined
        if (!persisted?.tabs || persisted.tabs.length === 0) return currentState
        const tabs = persisted.tabs.map((pt) => ({ ...makeTab(pt.currentPath), id: pt.id }))
        const activeTabId =
          persisted.activeTabId && tabs.some((t) => t.id === persisted.activeTabId) ? persisted.activeTabId : tabs[0].id
        const active = tabs.find((t) => t.id === activeTabId) as Tab
        return { ...currentState, tabs, activeTabId, ...omitId(active) }
      }
    }
  )
)
