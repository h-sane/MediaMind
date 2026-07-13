import { create } from 'zustand'

/** "Folder Options" dialog (Privacy: Recent files toggle) — opened from the
 * command bar only today, mirrors `recentDeletionsDialog.ts`'s pattern so
 * `ExplorerShell` owns the actual dialog mount. */
interface FolderOptionsDialogStore {
  isOpen: boolean
  open: () => void
  close: () => void
}

export const useFolderOptionsDialogStore = create<FolderOptionsDialogStore>((set) => ({
  isOpen: false,
  open: () => set({ isOpen: true }),
  close: () => set({ isOpen: false })
}))
