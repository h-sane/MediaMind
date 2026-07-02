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
    start: (libraryId: string, nearThreshold = 5) =>
      request<JobSnapshot>('POST', `/v1/libraries/${libraryId}/scans`, {
        type: 'dedupe',
        near_threshold: nearThreshold
      }),
    get: (libraryId: string, jobId: string) =>
      request<JobSnapshot>('GET', `/v1/libraries/${libraryId}/scans/${jobId}`),
    cancel: (libraryId: string, jobId: string) =>
      request<{ status: string }>('DELETE', `/v1/libraries/${libraryId}/scans/${jobId}`)
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
  }
}
