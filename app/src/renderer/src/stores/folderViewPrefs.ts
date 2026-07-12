import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { SortDir, SortKey, ViewMode } from './explorer'

export interface FolderViewPref {
  viewMode: ViewMode
  sortKey: SortKey
  sortDir: SortDir
}

interface FolderViewPrefsState {
  prefs: Record<string, FolderViewPref>
  setPref: (path: string, pref: FolderViewPref) => void
}

/** Per-folder view mode + sort, persisted across restarts — matches
 * Explorer's own behavior of remembering how you last looked at a specific
 * folder. Search/filter chips deliberately stay per-session-only (Phase C);
 * see stores/explorer.ts for how a folder without a saved pref falls back
 * to whatever view/sort was last active. */
export const useFolderViewPrefsStore = create<FolderViewPrefsState>()(
  persist(
    (set) => ({
      prefs: {},
      setPref: (path, pref) => set((s) => ({ prefs: { ...s.prefs, [path]: pref } }))
    }),
    { name: 'mediamind-folder-view-prefs' }
  )
)
