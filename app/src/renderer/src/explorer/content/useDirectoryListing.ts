import { useMemo } from 'react'
import { useBrowseDir, useDrives } from '../../api/hooks'
import { useGalleryItems } from '../../api/useGallery'
import { useRecursiveSearch } from '../../api/useSearch'
import { HOME_PATH, isRealFolder, useExplorerStore } from '../../stores/explorer'
import type { FilterDate, FilterSize, FilterType, SortDir, SortKey } from '../../stores/explorer'
import type { BrowseFile, BrowseFolder } from '../../api/client'
import type { GalleryItem } from '../../api/galleryClient'
import type { SearchResult } from '../../api/searchClient'
import { formatAttributes } from '../format'

const DAY_MS = 24 * 60 * 60 * 1000
const SMALL_MAX_BYTES = 1_000_000 // 1 MB
const MEDIUM_MAX_BYTES = 10_000_000 // 10 MB

export interface DirEntry {
  type: 'drive' | 'folder' | 'file'
  name: string
  path: string
  kind?: 'image' | 'gif' | 'video' | 'audio'
  size?: number
  mtime?: number
  hasMedia?: boolean | null
  created?: number | null
  accessed?: number | null
  readOnly?: boolean | null
  hidden?: boolean | null
  system?: boolean | null
}

function compareEntries(a: DirEntry, b: DirEntry, sortKey: SortKey, sortDir: SortDir): number {
  let result = 0
  switch (sortKey) {
    case 'name':
      result = a.name.localeCompare(b.name)
      break
    case 'date':
      result = (a.mtime ?? 0) - (b.mtime ?? 0)
      break
    case 'size':
      result = (a.size ?? 0) - (b.size ?? 0)
      break
    case 'type':
      result = (a.kind ?? '').localeCompare(b.kind ?? '')
      break
    case 'created':
      result = (a.created ?? 0) - (b.created ?? 0)
      break
    case 'accessed':
      result = (a.accessed ?? 0) - (b.accessed ?? 0)
      break
    case 'attributes':
      result = formatAttributes(a.readOnly, a.hidden, a.system).localeCompare(
        formatAttributes(b.readOnly, b.hidden, b.system)
      )
      break
  }
  return sortDir === 'asc' ? result : -result
}

function sortEntries(
  folders: BrowseFolder[],
  files: BrowseFile[],
  sortKey: SortKey,
  sortDir: SortDir
): DirEntry[] {
  const folderEntries: DirEntry[] = folders.map((f) => ({
    type: 'folder',
    name: f.name,
    path: f.path,
    hasMedia: f.has_media,
    mtime: f.mtime,
    created: f.created,
    accessed: f.accessed,
    readOnly: f.read_only,
    hidden: f.hidden,
    system: f.system
  }))
  const fileEntries: DirEntry[] = files.map((f) => ({
    type: 'file',
    name: f.name,
    path: f.path,
    kind: f.kind,
    size: f.size,
    mtime: f.mtime,
    created: f.created,
    accessed: f.accessed,
    readOnly: f.read_only,
    hidden: f.hidden,
    system: f.system
  }))

  folderEntries.sort((a, b) => compareEntries(a, b, sortKey, sortDir))
  fileEntries.sort((a, b) => compareEntries(a, b, sortKey, sortDir))
  // Folders first, like Explorer, regardless of sort key.
  return [...folderEntries, ...fileEntries]
}

/**
 * Same folders-first sort as `sortEntries`, but over a flat recursive-search
 * result set (Phase I) instead of a single folder's `BrowseFolder`/
 * `BrowseFile` listing — each hit already carries an absolute path that may
 * point anywhere under the searched root, not just the current folder.
 */
function sortSearchResults(results: SearchResult[], sortKey: SortKey, sortDir: SortDir): DirEntry[] {
  const entries: DirEntry[] = results.map((r) => ({
    type: r.kind,
    name: r.name,
    path: r.path,
    kind: r.media_kind ?? undefined,
    size: r.size ?? undefined,
    mtime: r.mtime
  }))
  const folderEntries = entries.filter((e) => e.type === 'folder')
  const fileEntries = entries.filter((e) => e.type === 'file')
  folderEntries.sort((a, b) => compareEntries(a, b, sortKey, sortDir))
  fileEntries.sort((a, b) => compareEntries(a, b, sortKey, sortDir))
  return [...folderEntries, ...fileEntries]
}

/**
 * Gallery items (Phase O) arrive from the backend already sorted by mtime,
 * most recent first — that order *is* the feature (a chronological media
 * timeline), so unlike `sortEntries`/`sortSearchResults` this never
 * re-orders by the store's `sortKey`/`sortDir`; `GalleryView.tsx` always
 * groups them by date regardless of the global Group-by setting too.
 */
function galleryToEntries(items: GalleryItem[]): DirEntry[] {
  return items.map((i) => ({
    type: 'file',
    name: i.name,
    path: i.path,
    kind: i.media_kind,
    size: i.size,
    mtime: i.mtime
  }))
}

interface FilterState {
  searchQuery: string
  filterType: FilterType
  filterDate: FilterDate
  filterSize: FilterSize
}

/**
 * Search matches folders and files by name (Explorer's own "search this
 * folder" semantics). Type/Date/Size only make sense for files — a folder's
 * contents are mixed, so it always stays visible and lets the user navigate
 * in rather than being filtered out by a file-shaped rule.
 */
function filterEntries(entries: DirEntry[], filters: FilterState): DirEntry[] {
  const { searchQuery, filterType, filterDate, filterSize } = filters
  const noFilters = !searchQuery && filterType === 'all' && filterDate === 'any' && filterSize === 'any'
  if (noFilters) return entries

  const query = searchQuery.trim().toLowerCase()
  const now = Date.now()

  return entries.filter((entry) => {
    if (query && !entry.name.toLowerCase().includes(query)) return false
    if (entry.type !== 'file') return true

    if (filterType !== 'all' && entry.kind !== filterType) return false

    if (filterDate !== 'any' && entry.mtime !== undefined) {
      const ageMs = now - entry.mtime * 1000
      if (filterDate === 'today' && ageMs > DAY_MS) return false
      if (filterDate === 'week' && ageMs > 7 * DAY_MS) return false
      if (filterDate === 'month' && ageMs > 30 * DAY_MS) return false
      if (filterDate === 'older' && ageMs <= 30 * DAY_MS) return false
    }

    if (filterSize !== 'any' && entry.size !== undefined) {
      if (filterSize === 'small' && entry.size >= SMALL_MAX_BYTES) return false
      if (filterSize === 'medium' && (entry.size < SMALL_MAX_BYTES || entry.size >= MEDIUM_MAX_BYTES)) return false
      if (filterSize === 'large' && entry.size < MEDIUM_MAX_BYTES) return false
    }

    return true
  })
}

/**
 * The current folder's contents, sorted per the explorer store and filtered
 * by the live search box / filter chips. At the "This PC" root (`currentPath
 * === null`) there is no folder to list — the entries are the OS drives
 * instead (search still applies to drive labels; type/date/size don't apply).
 *
 * When a recursive search is active (Phase I — see `stores/explorer.ts` and
 * `chrome/SearchBox.tsx`), `entries` is instead the flat search-results
 * pseudo-listing for `recursiveSearchRoot`. Likewise, when Gallery view mode
 * is active (Phase O) on a real folder, `entries` is the recursive,
 * date-sorted media timeline under `currentPath` instead of that folder's
 * own single-level listing. Every other view/selection/file-op consumer of
 * this hook keeps working unmodified either way: a `DirEntry` looks the same
 * regardless of source, so folder double-click/navigate, thumbnails, rename,
 * delete, etc. all still resolve off `entry.path`.
 */
export function useDirectoryListing() {
  const currentPath = useExplorerStore((s) => s.currentPath)
  const viewMode = useExplorerStore((s) => s.viewMode)
  const sortKey = useExplorerStore((s) => s.sortKey)
  const sortDir = useExplorerStore((s) => s.sortDir)
  const searchQuery = useExplorerStore((s) => s.searchQuery)
  const filterType = useExplorerStore((s) => s.filterType)
  const filterDate = useExplorerStore((s) => s.filterDate)
  const filterSize = useExplorerStore((s) => s.filterSize)
  const recursiveSearchActive = useExplorerStore((s) => s.recursiveSearchActive)
  const recursiveSearchRoot = useExplorerStore((s) => s.recursiveSearchRoot)
  const isRoot = currentPath === null
  const isHome = currentPath === HOME_PATH
  const galleryActive = viewMode === 'gallery' && isRealFolder(currentPath) && !recursiveSearchActive

  const dirQuery = useBrowseDir(isRealFolder(currentPath) ? currentPath : null)
  const drivesQuery = useDrives()
  const searchResultsQuery = useRecursiveSearch(recursiveSearchRoot, searchQuery, recursiveSearchActive)
  const galleryQuery = useGalleryItems(isRealFolder(currentPath) ? currentPath : null, galleryActive)

  const entries = useMemo((): DirEntry[] => {
    if (recursiveSearchActive && recursiveSearchRoot) {
      const raw = sortSearchResults(searchResultsQuery.data?.results ?? [], sortKey, sortDir)
      // The name match already happened server-side — only the type/date/size
      // chips still make sense to re-apply here, on the returned set.
      return filterEntries(raw, { searchQuery: '', filterType, filterDate, filterSize })
    }
    if (galleryActive) {
      const raw = galleryToEntries(galleryQuery.data?.items ?? [])
      return filterEntries(raw, { searchQuery, filterType, filterDate, filterSize })
    }
    const raw = isRoot
      ? [...(drivesQuery.data ?? [])]
          .sort((a, b) => a.label.localeCompare(b.label))
          .map((d): DirEntry => ({ type: 'drive', name: d.label, path: d.path }))
      : dirQuery.data
        ? sortEntries(dirQuery.data.folders, dirQuery.data.files, sortKey, sortDir)
        : []
    return filterEntries(raw, { searchQuery, filterType, filterDate, filterSize })
  }, [
    recursiveSearchActive,
    recursiveSearchRoot,
    searchResultsQuery.data,
    galleryActive,
    galleryQuery.data,
    isRoot,
    drivesQuery.data,
    dirQuery.data,
    sortKey,
    sortDir,
    searchQuery,
    filterType,
    filterDate,
    filterSize
  ])

  return {
    entries,
    isRoot,
    // Home (Phase N) has no folder listing of its own — ContentPane renders
    // HomeView instead and never consults these once isHome is true, but
    // they're kept truthful (not a permanently-disabled query's stale
    // "pending") for any future consumer of this hook.
    isHome,
    isPending: recursiveSearchActive
      ? searchResultsQuery.isPending
      : galleryActive
        ? galleryQuery.isPending
        : isHome
          ? false
          : isRoot
            ? drivesQuery.isPending
            : dirQuery.isPending,
    isError: recursiveSearchActive
      ? searchResultsQuery.isError
      : galleryActive
        ? galleryQuery.isError
        : isHome
          ? false
          : isRoot
            ? drivesQuery.isError
            : dirQuery.isError,
    isFetching: recursiveSearchActive
      ? searchResultsQuery.isFetching
      : galleryActive
        ? galleryQuery.isFetching
        : isHome
          ? false
          : isRoot
            ? drivesQuery.isFetching
            : dirQuery.isFetching,
    refetch: recursiveSearchActive
      ? searchResultsQuery.refetch
      : galleryActive
        ? galleryQuery.refetch
        : isRoot
          ? drivesQuery.refetch
          : dirQuery.refetch,
    isRecursiveSearch: recursiveSearchActive,
    searchTruncated: searchResultsQuery.data?.truncated ?? false,
    isGallery: galleryActive,
    galleryTruncated: galleryQuery.data?.truncated ?? false
  }
}
