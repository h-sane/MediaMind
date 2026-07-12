import { create } from 'zustand'

type LibrariesView = { name: 'libraries' }
type LibraryView = { name: 'library'; libraryId: string }
type FilesView = { name: 'files'; libraryId: string }
type DedupeView = { name: 'dedupe-review'; libraryId: string }
type ProvidersView = { name: 'providers'; libraryId: string }
type PeopleView = { name: 'people'; libraryId: string }
type PersonDetailView = { name: 'person-detail'; libraryId: string; personId: number }
type OrganizeView = { name: 'organize'; libraryId: string }
type PendingReviewView = { name: 'pending-review'; libraryId: string }
type MultiPersonReviewView = { name: 'multi-person-review'; libraryId: string }
type AuditView = { name: 'audit'; libraryId: string }

export type View =
  | LibrariesView
  | LibraryView
  | FilesView
  | DedupeView
  | ProvidersView
  | PeopleView
  | PersonDetailView
  | OrganizeView
  | PendingReviewView
  | MultiPersonReviewView
  | AuditView

// All views that are "children" of a library view navigate back to that library.
const LIBRARY_CHILDREN = new Set([
  'files', 'dedupe-review', 'providers', 'people', 'organize',
  'pending-review', 'multi-person-review', 'audit',
])

function parentOf(view: View): View {
  if (view.name === 'person-detail') {
    return { name: 'people', libraryId: view.libraryId }
  }
  if (LIBRARY_CHILDREN.has(view.name)) {
    const v = view as { name: string; libraryId: string }
    return { name: 'library', libraryId: v.libraryId }
  }
  if (view.name === 'library') {
    return { name: 'libraries' }
  }
  return { name: 'libraries' }
}

interface AppStore {
  view: View
  navigate: (view: View) => void
  back: () => void
}

export const useAppStore = create<AppStore>((set, get) => ({
  view: { name: 'libraries' },
  navigate: (view) => set({ view }),
  back: () => set({ view: parentOf(get().view) })
}))
