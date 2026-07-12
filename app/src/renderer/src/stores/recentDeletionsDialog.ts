import { create } from 'zustand'

/** The "Recent deletions" panel (Phase P item 4) is opened from the command
 * bar only today, but a store keeps it consistent with `propertiesDialog.ts`'s
 * pattern — `ExplorerShell` owns the actual dialog mount, any future trigger
 * (context menu, shortcut) just calls `open()`. */
interface RecentDeletionsDialogStore {
  isOpen: boolean
  open: () => void
  close: () => void
}

export const useRecentDeletionsDialogStore = create<RecentDeletionsDialogStore>((set) => ({
  isOpen: false,
  open: () => set({ isOpen: true }),
  close: () => set({ isOpen: false })
}))
