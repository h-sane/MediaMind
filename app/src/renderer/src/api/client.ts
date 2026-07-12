/**
 * Typed client for the MediaMind engine.
 *
 * Connection details (port + session token) come from the Electron main
 * process via the preload bridge; every request carries the token header.
 */
import type { BackendInfo } from '../../../shared/types'

let backend: BackendInfo | null = null

export async function connectBackend(): Promise<BackendInfo> {
  if (backend) return backend
  const existing = await window.mediamind.getBackendInfo()
  if (existing) {
    backend = existing
    return existing
  }
  return new Promise((resolve) => {
    window.mediamind.onBackendReady((info) => {
      backend = info
      resolve(info)
    })
  })
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const { port, token } = await connectBackend()
  let res: Response
  try {
    res = await fetch(`http://127.0.0.1:${port}${path}`, {
      method,
      headers: {
        'X-MediaMind-Token': token,
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {})
      },
      body: body !== undefined ? JSON.stringify(body) : undefined
    })
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    window.mediamind.logError(
      'api',
      `${method} ${path} (port ${port}): network error — ${message}`
    )
    throw err
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    window.mediamind.logError('api', `${method} ${path} -> ${res.status}: ${detail}`)
    throw new Error(detail)
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

export interface Health {
  status: string
  version: string
}

export interface Library {
  id: string
  path: string
  name: string
}

export interface JobSnapshot {
  id: string
  library_id: string
  type: string
  state: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'
  phase: string
  done: number
  total: number
  error: string
  result: Record<string, unknown> | null
  created_at: number
  finished_at: number | null
}

export interface DuplicateFile {
  id: number
  path: string
  size: number
  mtime: number
  kind: string
  width: number
  height: number
  suggested_keep: boolean
  resolution: 'keep' | 'trash' | 'trashed' | null
}

export interface DuplicateGroup {
  id: number
  match: 'exact' | 'near'
  files: DuplicateFile[]
}

export interface DuplicatesSummary {
  groups: number
  files: number
  reclaimable_bytes: number
}

export interface DuplicatesOut {
  scan_id: string
  scanned_at: number | null
  summary: DuplicatesSummary
  groups: DuplicateGroup[]
}

export interface ManifestEntry {
  source: string
  action: string
  destination: string
  error: string
}

export interface ExecutionReport {
  planned: number
  handled: number
  ok: boolean
  dry_run: boolean
  manifest_path: string | null
  entries: ManifestEntry[]
}

// ---------------------------------------------------------------------------
// Library file browser types (live, filesystem-first)
// ---------------------------------------------------------------------------

export interface FileEntry {
  path: string // relative to library root, forward-slash
  kind: 'image' | 'gif' | 'video' | 'audio' | 'other'
  size: number
  mtime: number
}

export interface LibraryFiles {
  library_id: string
  root: string
  total: number
  files: FileEntry[]
}

// ---------------------------------------------------------------------------
// Explorer shell (whole-filesystem browsing, library-free)
// ---------------------------------------------------------------------------

export interface Drive {
  path: string // e.g. "C:\\"
  label: string // e.g. "Local Disk (C:)"
}

export interface BrowseFolder {
  name: string
  path: string // absolute
  has_media: boolean | null // null = not yet known, checking in background
  mtime: number
  created: number | null // epoch seconds; null if the OS can't report it
  accessed: number | null
  read_only: boolean | null
  hidden: boolean | null
  system: boolean | null
}

export interface BrowseFile {
  name: string
  path: string // absolute
  kind: 'image' | 'gif' | 'video' | 'audio'
  size: number
  mtime: number
  created: number | null // epoch seconds; null if the OS can't report it
  accessed: number | null
  read_only: boolean | null
  hidden: boolean | null
  system: boolean | null
}

export interface BrowseDir {
  path: string
  folders: BrowseFolder[]
  files: BrowseFile[]
}

// ---------------------------------------------------------------------------
// Explorer shell — file operations (M12 Phase B)
// ---------------------------------------------------------------------------

export interface FsUndoResult {
  ok: boolean
  kind: string | null
  message: string
}

export interface FsRedoResult {
  ok: boolean
  kind: string | null
  message: string
}

// ---------------------------------------------------------------------------
// Explorer shell — metadata + Quick Access (M12 Phase C)
// ---------------------------------------------------------------------------

export interface BrowseMetadata {
  path: string
  name: string
  kind: 'image' | 'gif' | 'video' | 'audio'
  size: number
  mtime: number
  width: number | null
  height: number | null
  duration_seconds: number | null // video only; always null for image/gif/audio
  created: number | null
  accessed: number | null
  read_only: boolean | null
  hidden: boolean | null
  system: boolean | null
  owner: string | null
}

export interface FolderStats {
  path: string
  item_count: number | null // null = not yet known, computing in background
  total_bytes: number | null
}

export interface DiskUsage {
  path: string
  total_bytes: number
  used_bytes: number
  free_bytes: number
}

export interface QuickAccessEntry {
  path: string
  name: string
}

export interface QuickAccessList {
  pins: QuickAccessEntry[]
}

export interface RecentFile {
  path: string
  name: string
  kind: string
  size: number
  mtime: number
  opened_at: number
}

export interface RecentFilesList {
  files: RecentFile[]
}

// ---------------------------------------------------------------------------
// Provider types (M5)
// ---------------------------------------------------------------------------

export interface License {
  name: string
  url: string
  commercial_use: boolean
  summary: string
}

export interface Provider {
  id: string
  name: string
  description: string
  license: License
  installed: boolean
  size_bytes: number
  embedding_dim: number
}

// ---------------------------------------------------------------------------
// Person types (M5)
// ---------------------------------------------------------------------------

export interface Person {
  id: number
  auto_label: string
  name: string | null
  face_count: number
  media_count: number
  sample_face_ids: number[]
}

export interface PersonsOut {
  scan_id: string
  scanned_at: number | null
  provider_id: string
  persons: Person[]
  unassigned_faces: number
  no_face_files: number
  unreadable_files: number
  pending_count: number
  multi_person_count: number
}

export interface PersonMediaItem {
  file_id: number
  path: string
  kind: string
  face_id: number
  bbox: [number, number, number, number]
}

// ---------------------------------------------------------------------------
// Multi-person types (M6 remainder)
// ---------------------------------------------------------------------------

export interface PersonOption {
  person_id: number
  person_name: string
  face_count: number
  sample_face_id: number
}

export interface MultiPersonFile {
  file_id: number
  path: string
  kind: string
  persons: PersonOption[]
  current_choice: number | null
}

// ---------------------------------------------------------------------------
// Organize types (M6)
// ---------------------------------------------------------------------------

export interface PlannedMove {
  source_rel: string
  dest_folder_rel: string
  person_id: number | null
  person_name: string | null
}

export interface OrganizePreview {
  planned: number
  by_person: Record<string, number>
  moves: PlannedMove[]
}

export interface OrganizeAction {
  id: number
  kind: string
  created_at: number
  planned: number
  handled: number
  ok: boolean
  dry_run: boolean
  undone: boolean
}

// ---------------------------------------------------------------------------
// Pending match types (M6)
// ---------------------------------------------------------------------------

export interface PendingMatch {
  id: number
  face_id: number
  person_id: number
  person_name: string
  confidence: number
}

// ---------------------------------------------------------------------------
// API surface
// ---------------------------------------------------------------------------

export const api = {
  health: () => request<Health>('GET', '/v1/health'),

  libraries: {
    list: () => request<Library[]>('GET', '/v1/libraries'),
    add: (path: string) => request<Library>('POST', '/v1/libraries', { path }),
    remove: (id: string) => request<void>('DELETE', `/v1/libraries/${id}`)
  },

  files: {
    list: (libraryId: string) =>
      request<LibraryFiles>('GET', `/v1/libraries/${libraryId}/files`),

    thumbnailUrl: async (libraryId: string, path: string, size = 256): Promise<string> => {
      const { port, token } = await connectBackend()
      const res = await fetch(
        `http://127.0.0.1:${port}/v1/libraries/${libraryId}/files/thumbnail?path=${encodeURIComponent(path)}&size=${size}`,
        { headers: { 'X-MediaMind-Token': token } }
      )
      if (!res.ok) throw new Error('Thumbnail unavailable')
      return URL.createObjectURL(await res.blob())
    },

    rawUrl: async (libraryId: string, path: string): Promise<string> => {
      const { port, token } = await connectBackend()
      const res = await fetch(
        `http://127.0.0.1:${port}/v1/libraries/${libraryId}/files/raw?path=${encodeURIComponent(path)}`,
        { headers: { 'X-MediaMind-Token': token } }
      )
      if (!res.ok) throw new Error('File unavailable')
      return URL.createObjectURL(await res.blob())
    }
  },

  fs: {
    drives: () => request<Drive[]>('GET', '/v1/fs/drives'),

    list: (path: string) =>
      request<BrowseDir>('GET', `/v1/fs/list?path=${encodeURIComponent(path)}`),

    thumbnailUrl: async (path: string, size = 256): Promise<string> => {
      const { port, token } = await connectBackend()
      const res = await fetch(
        `http://127.0.0.1:${port}/v1/fs/thumbnail?path=${encodeURIComponent(path)}&size=${size}`,
        { headers: { 'X-MediaMind-Token': token } }
      )
      if (!res.ok) throw new Error('Thumbnail unavailable')
      return URL.createObjectURL(await res.blob())
    },

    rawUrl: async (path: string): Promise<string> => {
      const { port, token } = await connectBackend()
      const res = await fetch(
        `http://127.0.0.1:${port}/v1/fs/raw?path=${encodeURIComponent(path)}`,
        { headers: { 'X-MediaMind-Token': token } }
      )
      if (!res.ok) throw new Error('File unavailable')
      return URL.createObjectURL(await res.blob())
    },

    metadata: (path: string) =>
      request<BrowseMetadata>('GET', `/v1/fs/metadata?path=${encodeURIComponent(path)}`),

    folderStats: (path: string) =>
      request<FolderStats>('GET', `/v1/fs/folder-stats?path=${encodeURIComponent(path)}`),

    diskUsage: (path: string) =>
      request<DiskUsage>('GET', `/v1/fs/disk-usage?path=${encodeURIComponent(path)}`),

    quickAccess: {
      list: () => request<QuickAccessList>('GET', '/v1/fs/quick-access'),
      pin: (path: string) => request<QuickAccessList>('POST', '/v1/fs/quick-access', { path }),
      unpin: (path: string) =>
        request<QuickAccessList>('DELETE', `/v1/fs/quick-access?path=${encodeURIComponent(path)}`),
      reorder: (paths: string[]) =>
        request<QuickAccessList>('PUT', '/v1/fs/quick-access/reorder', { paths })
    },

    recent: {
      list: () => request<RecentFilesList>('GET', '/v1/fs/recent'),
      record: (path: string) => request<RecentFilesList>('POST', '/v1/fs/recent', { path })
    }
  },

  fsOps: {
    newFolder: (parent: string, name?: string) =>
      request<{ path: string }>('POST', '/v1/fs/new-folder', { parent, name: name ?? null }),

    rename: (path: string, newName: string) =>
      request<{ path: string }>('POST', '/v1/fs/rename', { path, new_name: newName }),

    delete: (paths: string[], permanent = false) =>
      request<ExecutionReport>('POST', '/v1/fs/delete', { paths, permanent }),

    move: (sources: string[], dest: string) =>
      request<ExecutionReport>('POST', '/v1/fs/move', { sources, dest }),

    copy: (sources: string[], dest: string) =>
      request<ExecutionReport>('POST', '/v1/fs/copy', { sources, dest }),

    undo: () => request<FsUndoResult>('POST', '/v1/fs/undo'),

    redo: () => request<FsRedoResult>('POST', '/v1/fs/redo'),

    createShortcut: (target: string, destFolder: string, name?: string) =>
      request<{ path: string }>('POST', '/v1/fs/create-shortcut', {
        target,
        dest_folder: destFolder,
        name: name ?? null
      })
  },

  scans: {
    start: (
      libraryId: string,
      opts?: { type?: 'dedupe' | 'faces'; nearThreshold?: number; providerId?: string }
    ) =>
      request<JobSnapshot>('POST', `/v1/libraries/${libraryId}/scans`, {
        type: opts?.type ?? 'dedupe',
        near_threshold: opts?.nearThreshold ?? 5,
        provider_id: opts?.providerId ?? null
      }),
    get: (libraryId: string, jobId: string) =>
      request<JobSnapshot>('GET', `/v1/libraries/${libraryId}/scans/${jobId}`),
    cancel: (libraryId: string, jobId: string) =>
      request<{ status: string }>('DELETE', `/v1/libraries/${libraryId}/scans/${jobId}`)
  },

  jobs: {
    get: (jobId: string) => request<JobSnapshot>('GET', `/v1/jobs/${jobId}`),
    cancel: (jobId: string) => request<{ status: string }>('DELETE', `/v1/jobs/${jobId}`)
  },

  duplicates: {
    list: (libraryId: string) =>
      request<DuplicatesOut>('GET', `/v1/libraries/${libraryId}/duplicates`),

    resolve: (libraryId: string, resolutions: { file_id: number; action: 'keep' | 'trash' }[]) =>
      request<{ updated: number }>('POST', `/v1/libraries/${libraryId}/duplicates/resolutions`, {
        resolutions
      }),

    execute: (libraryId: string, dryRun: boolean, expectedTrashCount: number) =>
      request<ExecutionReport>('POST', `/v1/libraries/${libraryId}/duplicates/execute`, {
        dry_run: dryRun,
        expected_trash_count: expectedTrashCount
      }),

    thumbnailUrl: async (libraryId: string, memberId: number, size = 256): Promise<string> => {
      const { port, token } = await connectBackend()
      const res = await fetch(
        `http://127.0.0.1:${port}/v1/libraries/${libraryId}/duplicates/files/${memberId}/thumbnail?size=${size}`,
        { headers: { 'X-MediaMind-Token': token } }
      )
      if (!res.ok) throw new Error('Thumbnail unavailable')
      return URL.createObjectURL(await res.blob())
    }
  },

  providers: {
    list: () => request<Provider[]>('GET', '/v1/providers'),
    download: (id: string) =>
      request<JobSnapshot>('POST', `/v1/providers/${id}/download`, { license_accepted: true })
  },

  organize: {
    preview: (libraryId: string) =>
      request<OrganizePreview>('POST', `/v1/libraries/${libraryId}/organize/preview`),
    execute: (libraryId: string, dryRun: boolean, expectedPlanned?: number) =>
      request<ExecutionReport>('POST', `/v1/libraries/${libraryId}/organize/execute`, {
        dry_run: dryRun,
        expected_planned: expectedPlanned ?? null
      }),
    undo: (libraryId: string) =>
      request<{ ok: boolean; handled: number; planned: number; errors: number }>(
        'POST',
        `/v1/libraries/${libraryId}/organize/undo`
      ),
    audit: (libraryId: string) =>
      request<OrganizeAction[]>('GET', `/v1/libraries/${libraryId}/organize/audit`)
  },

  pending: {
    list: (libraryId: string) =>
      request<PendingMatch[]>('GET', `/v1/libraries/${libraryId}/pending`),
    decide: (
      libraryId: string,
      decisions: { pending_id: number; decision: 'confirmed' | 'rejected' }[]
    ) =>
      request<{ updated: number }>('POST', `/v1/libraries/${libraryId}/pending/decisions`, {
        decisions
      })
  },

  multiPerson: {
    list: (libraryId: string) =>
      request<MultiPersonFile[]>('GET', `/v1/libraries/${libraryId}/multi-person`),
    setChoices: (libraryId: string, choices: { file_id: number; person_id: number }[]) =>
      request<{ updated: number }>('POST', `/v1/libraries/${libraryId}/route-choices`, { choices })
  },

  persons: {
    list: (libraryId: string) =>
      request<PersonsOut>('GET', `/v1/libraries/${libraryId}/persons`),

    rename: (libraryId: string, personId: number, name: string | null) =>
      request<{ ok: boolean }>('PATCH', `/v1/libraries/${libraryId}/persons/${personId}`, { name }),

    merge: (libraryId: string, sourceId: number, targetId: number) =>
      request<{ ok: boolean }>('POST', `/v1/libraries/${libraryId}/persons/merge`, {
        source_id: sourceId,
        target_id: targetId
      }),

    media: (libraryId: string, personId: number) =>
      request<PersonMediaItem[]>('GET', `/v1/libraries/${libraryId}/persons/${personId}/media`),

    faceThumbnailUrl: async (libraryId: string, faceId: number, size = 192): Promise<string> => {
      const { port, token } = await connectBackend()
      const res = await fetch(
        `http://127.0.0.1:${port}/v1/libraries/${libraryId}/faces/${faceId}/thumbnail?size=${size}`,
        { headers: { 'X-MediaMind-Token': token } }
      )
      if (!res.ok) throw new Error('Face thumbnail unavailable')
      return URL.createObjectURL(await res.blob())
    }
  }
}
