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

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const { port, token } = await connectBackend()
  const res = await fetch(`http://127.0.0.1:${port}${path}`, {
    method,
    headers: {
      'X-MediaMind-Token': token,
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {})
    },
    body: body !== undefined ? JSON.stringify(body) : undefined
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* non-JSON error body */
    }
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
    execute: (libraryId: string, dryRun: boolean) =>
      request<ExecutionReport>('POST', `/v1/libraries/${libraryId}/organize/execute`, {
        dry_run: dryRun
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
