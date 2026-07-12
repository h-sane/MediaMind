import { useRef } from 'react'
import { Search, X } from 'lucide-react'
import { isRealFolder, useExplorerStore } from '../../stores/explorer'

/**
 * Typing filters the current folder's already-loaded entries instantly — no
 * network round trip, see `useDirectoryListing`'s `filterEntries` — matching
 * Explorer's own live "search this folder" behavior.
 *
 * Pressing Enter escalates the same query into a real recursive backend
 * search of every subfolder (Phase I, `GET /v1/fs/search`): the content pane
 * then shows a flat search-results pseudo-listing instead of the current
 * folder's own contents (see `useDirectoryListing`/`stores/explorer.ts`).
 * Editing the query afterward drops back to the fast local filter rather
 * than re-searching on every keystroke; Escape or clearing the box exits
 * recursive search entirely. `id="explorer-search-input"` is how
 * `useKeyboardShortcuts` focuses this box for Ctrl+F/Ctrl+E/F3.
 */
export function SearchBox(): React.JSX.Element {
  const searchQuery = useExplorerStore((s) => s.searchQuery)
  const setSearchQuery = useExplorerStore((s) => s.setSearchQuery)
  const recursiveSearchActive = useExplorerStore((s) => s.recursiveSearchActive)
  const startRecursiveSearch = useExplorerStore((s) => s.startRecursiveSearch)
  const stopRecursiveSearch = useExplorerStore((s) => s.stopRecursiveSearch)
  const currentPath = useExplorerStore((s) => s.currentPath)
  const inputRef = useRef<HTMLInputElement>(null)

  function clear(): void {
    setSearchQuery('')
    stopRecursiveSearch()
  }

  return (
    <div
      className={`flex h-8 w-56 shrink-0 items-center gap-1.5 rounded-md border px-2 ${
        recursiveSearchActive ? 'border-blue-400 bg-blue-50' : 'border-zinc-200 bg-white'
      }`}
      title={
        isRealFolder(currentPath)
          ? 'Type to filter this folder — press Enter to search subfolders too'
          : 'Type to filter'
      }
    >
      <Search className={`h-3.5 w-3.5 shrink-0 ${recursiveSearchActive ? 'text-blue-500' : 'text-zinc-400'}`} />
      <input
        ref={inputRef}
        id="explorer-search-input"
        value={searchQuery}
        onChange={(e) => {
          setSearchQuery(e.target.value)
          // Editing the query after a recursive search restarts it as a
          // plain local filter — the user is refining, not re-committing.
          if (recursiveSearchActive) stopRecursiveSearch()
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && searchQuery.trim() && isRealFolder(currentPath)) {
            e.preventDefault()
            startRecursiveSearch()
          } else if (e.key === 'Escape' && (searchQuery || recursiveSearchActive)) {
            e.preventDefault()
            clear()
            inputRef.current?.blur()
          }
        }}
        placeholder={recursiveSearchActive ? 'Search subfolders' : 'Search'}
        className="w-full min-w-0 text-sm text-zinc-900 outline-none placeholder:text-zinc-400"
      />
      {searchQuery && (
        <button
          type="button"
          onClick={clear}
          aria-label="Clear search"
          className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </div>
  )
}
