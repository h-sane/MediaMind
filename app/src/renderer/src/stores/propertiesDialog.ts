import { create } from 'zustand'
import type { DirEntry } from '../explorer/content/useDirectoryListing'

/** The Properties dialog is opened from three places (command bar, context
 * menu, `Alt+Enter`) — a store instead of ExplorerShell-owned state so none
 * of them need to reach up through a prop callback to trigger it. */
interface PropertiesDialogStore {
  entries: DirEntry[] | null
  open: (entries: DirEntry[]) => void
  close: () => void
}

export const usePropertiesDialogStore = create<PropertiesDialogStore>((set) => ({
  entries: null,
  open: (entries) => set({ entries }),
  close: () => set({ entries: null })
}))
