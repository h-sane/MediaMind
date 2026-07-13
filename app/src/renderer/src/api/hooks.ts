import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import { isRealFolder } from '../stores/explorer'
import type { DuplicateFile, Person } from './client'

// ---------------------------------------------------------------------------
// Engine + libraries
// ---------------------------------------------------------------------------

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    retry: 20,
    retryDelay: 500,
    refetchInterval: 15_000
  })
}

export function useLibraries() {
  return useQuery({ queryKey: ['libraries'], queryFn: api.libraries.list })
}

export function useAddLibrary() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.libraries.add,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['libraries'] })
  })
}

export function useRemoveLibrary() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.libraries.remove,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['libraries'] })
  })
}

// ---------------------------------------------------------------------------
// Library file browser (live, filesystem-first — no scan required)
// ---------------------------------------------------------------------------

export function useLibraryFiles(libraryId: string) {
  return useQuery({
    queryKey: ['files', libraryId],
    queryFn: () => api.files.list(libraryId)
  })
}

/**
 * Thumbnail for a file by its library-relative path. Fetch is deferred until
 * `enabled` is true (the grid enables tiles as they approach the viewport so
 * a large folder doesn't fire thousands of requests at once). `failed` lets
 * the tile show a static placeholder for undecodable files.
 */
export function useFileThumbnailUrl(
  libraryId: string,
  path: string,
  size = 256,
  enabled = true
): { url: string | null; failed: boolean } {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const urlRef = useRef<string | null>(null)

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    api.files
      .thumbnailUrl(libraryId, path, size)
      .then((objectUrl) => {
        if (!cancelled) {
          urlRef.current = objectUrl
          setUrl(objectUrl)
        } else {
          URL.revokeObjectURL(objectUrl)
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })

    return () => {
      cancelled = true
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current)
        urlRef.current = null
      }
    }
  }, [libraryId, path, size, enabled])

  return { url, failed }
}

/**
 * Full-resolution file content for the in-app media viewer (image to display,
 * video to play). Fetched only while `enabled` (the viewer is open for this
 * file) so browsing the grid never downloads full files.
 */
export function useFileRawUrl(
  libraryId: string,
  path: string,
  enabled: boolean
): { url: string | null; failed: boolean } {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const urlRef = useRef<string | null>(null)

  useEffect(() => {
    setUrl(null)
    setFailed(false)
    if (!enabled) return
    let cancelled = false
    api.files
      .rawUrl(libraryId, path)
      .then((objectUrl) => {
        if (!cancelled) {
          urlRef.current = objectUrl
          setUrl(objectUrl)
        } else {
          URL.revokeObjectURL(objectUrl)
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })

    return () => {
      cancelled = true
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current)
        urlRef.current = null
      }
    }
  }, [libraryId, path, enabled])

  return { url, failed }
}

// ---------------------------------------------------------------------------
// Explorer shell — right-sidebar tools bridge
// ---------------------------------------------------------------------------

/**
 * Registers (or reuses) the currently-open real folder as a "library" —
 * the dedupe/faces engine's only requirement, a lightweight pointer plus an
 * empty `.mediamind/` metadata folder, not a scan. `api.libraries.add` is
 * idempotent by resolved path server-side, and this query's `path` key plus
 * `staleTime: Infinity` mean it's requested at most once per folder per
 * session — safe against rapid folder/tab switching. Disabled for "This PC"
 * / Home (`isRealFolder`), which have nothing to register.
 */
export function useEnsureLibrary(path: string | null) {
  return useQuery({
    queryKey: ['ensure-library', path],
    queryFn: () => api.libraries.add(path as string),
    enabled: isRealFolder(path),
    staleTime: Infinity,
    retry: false
  })
}

// ---------------------------------------------------------------------------
// Explorer shell (whole-filesystem browsing, library-free)
// ---------------------------------------------------------------------------

export function useDrives() {
  return useQuery({
    queryKey: ['drives'],
    queryFn: api.fs.drives,
    staleTime: 60_000
  })
}

/**
 * A single directory's contents. Subfolders whose `has_media` is still
 * unknown (the backend is walking their subtree in the background) trigger a
 * short poll until every entry has resolved to true/false, then it stops.
 */
export function useBrowseDir(path: string | null) {
  return useQuery({
    queryKey: ['browse', path],
    queryFn: () => api.fs.list(path as string),
    enabled: !!path,
    refetchInterval: (query) => {
      const data = query.state.data
      const stillChecking = data?.folders.some((f) => f.has_media === null)
      return stillChecking ? 1500 : false
    }
  })
}

/** Thumbnail for a file by absolute filesystem path (no library needed). */
export function useBrowseThumbnailUrl(
  path: string,
  size = 256,
  enabled = true
): { url: string | null; failed: boolean } {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const urlRef = useRef<string | null>(null)

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    api.fs
      .thumbnailUrl(path, size)
      .then((objectUrl) => {
        if (!cancelled) {
          urlRef.current = objectUrl
          setUrl(objectUrl)
        } else {
          URL.revokeObjectURL(objectUrl)
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })

    return () => {
      cancelled = true
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current)
        urlRef.current = null
      }
    }
  }, [path, size, enabled])

  return { url, failed }
}

/** Full-resolution file content by absolute path, for the in-app viewer. */
export function useBrowseRawUrl(
  path: string,
  enabled: boolean
): { url: string | null; failed: boolean } {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const urlRef = useRef<string | null>(null)

  useEffect(() => {
    setUrl(null)
    setFailed(false)
    if (!enabled) return
    let cancelled = false
    api.fs
      .rawUrl(path)
      .then((objectUrl) => {
        if (!cancelled) {
          urlRef.current = objectUrl
          setUrl(objectUrl)
        } else {
          URL.revokeObjectURL(objectUrl)
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })

    return () => {
      cancelled = true
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current)
        urlRef.current = null
      }
    }
  }, [path, enabled])

  return { url, failed }
}

// ---------------------------------------------------------------------------
// Explorer shell — file operations (M12 Phase B)
// ---------------------------------------------------------------------------

/** Every mutation below takes the folder(s) it affects explicitly, so the
 * calling component (which already knows the current path) decides what to
 * invalidate rather than this module reaching into the explorer store. */

export function useFsNewFolder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ parent, name }: { parent: string; name?: string }) =>
      api.fsOps.newFolder(parent, name),
    onSuccess: (_data, { parent }) => {
      qc.invalidateQueries({ queryKey: ['browse', parent] })
      // Gallery view (Phase O) walks the same folder recursively under a
      // separate query key — every folder-scoped browse invalidation below
      // has a matching gallery one so a folder open in Gallery view doesn't
      // go stale after a write.
      qc.invalidateQueries({ queryKey: ['fs-gallery', parent] })
    }
  })
}

export function useFsRename() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ path, newName }: { path: string; newName: string; folder: string }) =>
      api.fsOps.rename(path, newName),
    onSuccess: (_data, { folder }) => {
      qc.invalidateQueries({ queryKey: ['browse', folder] })
      qc.invalidateQueries({ queryKey: ['fs-gallery', folder] })
    }
  })
}

export function useFsDelete() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ paths, permanent }: { paths: string[]; permanent?: boolean; folder: string }) =>
      api.fsOps.delete(paths, permanent),
    onSuccess: (_data, { folder }) => {
      qc.invalidateQueries({ queryKey: ['browse', folder] })
      qc.invalidateQueries({ queryKey: ['fs-gallery', folder] })
      // Keeps the "Recent deletions" panel (Phase P item 4) fresh if it's
      // open — a cheap invalidate even when it isn't, since that query is
      // only ever enabled while the panel is mounted.
      qc.invalidateQueries({ queryKey: ['fs-recent-deletions'] })
    }
  })
}

export function useFsMove() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ sources, dest }: { sources: string[]; dest: string; sourceFolder: string }) =>
      api.fsOps.move(sources, dest),
    onSuccess: (_data, { dest, sourceFolder }) => {
      qc.invalidateQueries({ queryKey: ['browse', dest] })
      qc.invalidateQueries({ queryKey: ['fs-gallery', dest] })
      if (sourceFolder !== dest) {
        qc.invalidateQueries({ queryKey: ['browse', sourceFolder] })
        qc.invalidateQueries({ queryKey: ['fs-gallery', sourceFolder] })
      }
    }
  })
}

export function useFsCopy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ sources, dest }: { sources: string[]; dest: string }) =>
      api.fsOps.copy(sources, dest),
    onSuccess: (_data, { dest }) => {
      qc.invalidateQueries({ queryKey: ['browse', dest] })
      qc.invalidateQueries({ queryKey: ['fs-gallery', dest] })
    }
  })
}

/** Undo can reverse a move/copy/rename/new-folder touching folders this
 * component has no direct handle on — invalidate every open browse (and
 * gallery) query rather than trying to track exactly which ones changed. */
export function useFsUndo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.fsOps.undo(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['browse'] })
      qc.invalidateQueries({ queryKey: ['fs-gallery'] })
    }
  })
}

/** Mirrors `useFsUndo` — redo can touch the same folders undo could have. */
export function useFsRedo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.fsOps.redo(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['browse'] })
      qc.invalidateQueries({ queryKey: ['fs-gallery'] })
    }
  })
}

export function useFsCreateShortcut() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      target,
      destFolder,
      name
    }: {
      target: string
      destFolder: string
      name?: string
    }) => api.fsOps.createShortcut(target, destFolder, name),
    onSuccess: (_data, { destFolder }) => {
      qc.invalidateQueries({ queryKey: ['browse', destFolder] })
      qc.invalidateQueries({ queryKey: ['fs-gallery', destFolder] })
    }
  })
}

// ---------------------------------------------------------------------------
// Explorer shell — metadata + Quick Access (M12 Phase C)
// ---------------------------------------------------------------------------

/** Dimensions/duration for the preview pane. Only fetched while `enabled`
 * (the preview pane is open and a single file is selected). */
export function useFileMetadata(path: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['metadata', path],
    queryFn: () => api.fs.metadata(path as string),
    enabled: enabled && !!path
  })
}

/**
 * Recursive item-count/total-bytes for a folder, for the Properties panel.
 * Same lazy-resolve-then-poll shape as `useBrowseDir`'s has_media polling —
 * the backend answers "unknown, computing" on first look.
 */
export function useFolderStats(path: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['folder-stats', path],
    queryFn: () => api.fs.folderStats(path as string),
    enabled: enabled && !!path,
    refetchInterval: (query) => (query.state.data?.item_count === null ? 1500 : false)
  })
}

export function useDiskUsage(path: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['disk-usage', path],
    queryFn: () => api.fs.diskUsage(path as string),
    enabled: enabled && !!path,
    staleTime: 30_000
  })
}

export function useQuickAccess() {
  return useQuery({ queryKey: ['quick-access'], queryFn: api.fs.quickAccess.list })
}

export function usePinQuickAccess() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (path: string) => api.fs.quickAccess.pin(path),
    onSuccess: (data) => qc.setQueryData(['quick-access'], data)
  })
}

export function useUnpinQuickAccess() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (path: string) => api.fs.quickAccess.unpin(path),
    onSuccess: (data) => qc.setQueryData(['quick-access'], data)
  })
}

export function useReorderQuickAccess() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (paths: string[]) => api.fs.quickAccess.reorder(paths),
    onSuccess: (data) => qc.setQueryData(['quick-access'], data)
  })
}

export function useRecentFiles() {
  return useQuery({ queryKey: ['recent-files'], queryFn: api.fs.recent.list })
}

/** Records a file as just-opened for the Home page's Recent files list.
 * Call this at the point a file is actually opened (double-click / Enter),
 * not on hover or selection. */
export function useRecordRecentFile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (path: string) => api.fs.recent.record(path),
    onSuccess: (data) => qc.setQueryData(['recent-files'], data)
  })
}

/** Folder Options settings (currently just the Recent files privacy
 * toggle) — mirrors real Explorer's "Show recently used files" checkbox. */
export function useSettings() {
  return useQuery({ queryKey: ['settings'], queryFn: api.fs.settings.get })
}

export function useUpdateSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (recentFilesEnabled: boolean) => api.fs.settings.update(recentFilesEnabled),
    onSuccess: (data) => {
      qc.setQueryData(['settings'], data)
      qc.invalidateQueries({ queryKey: ['recent-files'] })
    }
  })
}

// ---------------------------------------------------------------------------
// Scans
// ---------------------------------------------------------------------------

export function useStartScan(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.scans.start(libraryId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scan', libraryId] })
  })
}

export function useStartFaceScan(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (providerId?: string) =>
      api.scans.start(libraryId, { type: 'faces', providerId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scan', libraryId] })
  })
}

export function useCancelScan(libraryId: string, jobId: string) {
  return useMutation({
    mutationFn: () => api.scans.cancel(libraryId, jobId)
  })
}

// ---------------------------------------------------------------------------
// Duplicates
// ---------------------------------------------------------------------------

export function useDuplicates(libraryId: string) {
  return useQuery({
    queryKey: ['duplicates', libraryId],
    queryFn: () => api.duplicates.list(libraryId),
    retry: false
  })
}

export function useRecycleBinCheck(libraryId: string) {
  return useQuery({
    queryKey: ['recycle-bin-check', libraryId],
    queryFn: () => api.duplicates.recycleBinCheck(libraryId),
    retry: false
  })
}

export function useResolve(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (resolutions: { file_id: number; action: 'keep' | 'trash' }[]) =>
      api.duplicates.resolve(libraryId, resolutions),
    onMutate: async (resolutions) => {
      await qc.cancelQueries({ queryKey: ['duplicates', libraryId] })
      const prev = qc.getQueryData(['duplicates', libraryId])
      qc.setQueryData(['duplicates', libraryId], (old: ReturnType<typeof api.duplicates.list> extends Promise<infer T> ? T : never) => {
        if (!old) return old
        return {
          ...old,
          groups: old.groups.map((g) => ({
            ...g,
            files: g.files.map((f: DuplicateFile) => {
              const res = resolutions.find((r) => r.file_id === f.id)
              return res ? { ...f, resolution: res.action } : f
            })
          }))
        }
      })
      return { prev }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(['duplicates', libraryId], ctx.prev)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['duplicates', libraryId] })
  })
}

export function useExecute(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      dryRun,
      expectedTrashCount,
      permanent
    }: {
      dryRun: boolean
      expectedTrashCount: number
      permanent?: boolean
    }) => api.duplicates.execute(libraryId, dryRun, expectedTrashCount, permanent),
    onSuccess: (_data, { dryRun }) => {
      if (!dryRun) qc.invalidateQueries({ queryKey: ['duplicates', libraryId] })
    }
  })
}

export function useConfirmReviewed(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.duplicates.confirm(libraryId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['duplicates', libraryId] })
  })
}

export function useResetDismissals(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.duplicates.resetDismissals(libraryId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['duplicates', libraryId] })
  })
}

// ---------------------------------------------------------------------------
// Providers (M5)
// ---------------------------------------------------------------------------

export function useProviders() {
  return useQuery({
    queryKey: ['providers'],
    queryFn: api.providers.list,
    retry: false
  })
}

export function useDownloadProvider() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (providerId: string) => api.providers.download(providerId),
    onSettled: () => qc.invalidateQueries({ queryKey: ['providers'] })
  })
}

// ---------------------------------------------------------------------------
// Persons (M5)
// ---------------------------------------------------------------------------

export function usePersons(libraryId: string) {
  return useQuery({
    queryKey: ['persons', libraryId],
    queryFn: () => api.persons.list(libraryId),
    retry: false
  })
}

export function useRenamePerson(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ personId, name }: { personId: number; name: string | null }) =>
      api.persons.rename(libraryId, personId, name),
    onMutate: async ({ personId, name }) => {
      await qc.cancelQueries({ queryKey: ['persons', libraryId] })
      const prev = qc.getQueryData(['persons', libraryId])
      qc.setQueryData(['persons', libraryId], (old: ReturnType<typeof api.persons.list> extends Promise<infer T> ? T : never) => {
        if (!old) return old
        return {
          ...old,
          persons: old.persons.map((p: Person) =>
            p.id === personId ? { ...p, name } : p
          )
        }
      })
      return { prev }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(['persons', libraryId], ctx.prev)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['persons', libraryId] })
  })
}

export function useMergePersons(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ sourceId, targetId }: { sourceId: number; targetId: number }) =>
      api.persons.merge(libraryId, sourceId, targetId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['persons', libraryId] })
  })
}

export function usePersonMedia(libraryId: string, personId: number) {
  return useQuery({
    queryKey: ['person-media', libraryId, personId],
    queryFn: () => api.persons.media(libraryId, personId),
    enabled: personId > 0
  })
}

// ---------------------------------------------------------------------------
// Thumbnails (fetch with auth header → object URL, revoked on unmount)
// ---------------------------------------------------------------------------

export function useThumbnailUrl(libraryId: string, memberId: number, size = 256): string | null {
  const [url, setUrl] = useState<string | null>(null)
  const urlRef = useRef<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api.duplicates
      .thumbnailUrl(libraryId, memberId, size)
      .then((objectUrl) => {
        if (!cancelled) {
          urlRef.current = objectUrl
          setUrl(objectUrl)
        } else {
          URL.revokeObjectURL(objectUrl)
        }
      })
      .catch(() => {})

    return () => {
      cancelled = true
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current)
        urlRef.current = null
      }
    }
  }, [libraryId, memberId, size])

  return url
}

// ---------------------------------------------------------------------------
// Organize (M6)
// ---------------------------------------------------------------------------

export function useOrganizePreview(libraryId: string) {
  return useQuery({
    queryKey: ['organize-preview', libraryId],
    queryFn: () => api.organize.preview(libraryId),
    retry: false
  })
}

export function useOrganizeExecute(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ dryRun, expectedPlanned }: { dryRun: boolean; expectedPlanned?: number }) =>
      api.organize.execute(libraryId, dryRun, expectedPlanned),
    onSuccess: (_data, vars) => {
      if (!vars.dryRun) {
        qc.invalidateQueries({ queryKey: ['organize-preview', libraryId] })
        qc.invalidateQueries({ queryKey: ['organize-audit', libraryId] })
      }
    }
  })
}

export function useOrganizeUndo(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.organize.undo(libraryId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['organize-preview', libraryId] })
      qc.invalidateQueries({ queryKey: ['organize-audit', libraryId] })
    }
  })
}

export function useOrganizeAudit(libraryId: string) {
  return useQuery({
    queryKey: ['organize-audit', libraryId],
    queryFn: () => api.organize.audit(libraryId),
    retry: false
  })
}

// ---------------------------------------------------------------------------
// Pending matches (M6)
// ---------------------------------------------------------------------------

export function usePendingMatches(libraryId: string) {
  return useQuery({
    queryKey: ['pending', libraryId],
    queryFn: () => api.pending.list(libraryId),
    retry: false
  })
}

export function useDecidePending(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (decisions: { pending_id: number; decision: 'confirmed' | 'rejected' }[]) =>
      api.pending.decide(libraryId, decisions),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pending', libraryId] })
      qc.invalidateQueries({ queryKey: ['persons', libraryId] })
    }
  })
}

// ---------------------------------------------------------------------------
// Multi-person review (M6 remainder)
// ---------------------------------------------------------------------------

export function useMultiPersonFiles(libraryId: string) {
  return useQuery({
    queryKey: ['multi-person', libraryId],
    queryFn: () => api.multiPerson.list(libraryId),
    retry: false
  })
}

export function useSetRouteChoices(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (choices: { file_id: number; person_id: number }[]) =>
      api.multiPerson.setChoices(libraryId, choices),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['multi-person', libraryId] })
      qc.invalidateQueries({ queryKey: ['organize-preview', libraryId] })
    }
  })
}

export function useFaceThumbnailUrl(libraryId: string, faceId: number, size = 192): string | null {
  const [url, setUrl] = useState<string | null>(null)
  const urlRef = useRef<string | null>(null)

  useEffect(() => {
    let cancelled = false
    if (faceId <= 0) return
    api.persons
      .faceThumbnailUrl(libraryId, faceId, size)
      .then((objectUrl) => {
        if (!cancelled) {
          urlRef.current = objectUrl
          setUrl(objectUrl)
        } else {
          URL.revokeObjectURL(objectUrl)
        }
      })
      .catch(() => {})

    return () => {
      cancelled = true
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current)
        urlRef.current = null
      }
    }
  }, [libraryId, faceId, size])

  return url
}
