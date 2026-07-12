import { create } from 'zustand'

export type ClipboardMode = 'cut' | 'copy'

interface ClipboardStore {
  mode: ClipboardMode | null
  paths: string[]
  /** The folder the items were cut/copied from — captured at cut/copy time,
   * not derived at paste time, since the user navigates elsewhere before
   * pasting. Needed only to invalidate the right browse query on paste. */
  sourceFolder: string | null

  setCut: (paths: string[], sourceFolder: string) => void
  setCopy: (paths: string[], sourceFolder: string) => void
  clear: () => void
}

export const useClipboardStore = create<ClipboardStore>((set) => ({
  mode: null,
  paths: [],
  sourceFolder: null,
  setCut: (paths, sourceFolder) => set({ mode: 'cut', paths, sourceFolder }),
  setCopy: (paths, sourceFolder) => set({ mode: 'copy', paths, sourceFolder }),
  clear: () => set({ mode: null, paths: [], sourceFolder: null })
}))
