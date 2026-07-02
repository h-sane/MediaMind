import { create } from 'zustand'

type LibrariesView = { name: 'libraries' }
type LibraryView = { name: 'library'; libraryId: string }
type DedupeView = { name: 'dedupe-review'; libraryId: string }
export type View = LibrariesView | LibraryView | DedupeView

interface AppStore {
  view: View
  navigate: (view: View) => void
  back: () => void
}

export const useAppStore = create<AppStore>((set, get) => ({
  view: { name: 'libraries' },
  navigate: (view) => set({ view }),
  back: () => {
    const { view } = get()
    if (view.name === 'dedupe-review') {
      set({ view: { name: 'library', libraryId: view.libraryId } })
    } else {
      set({ view: { name: 'libraries' } })
    }
  }
}))
