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

export interface Health {
  status: string
  version: string
}

export interface Library {
  id: string
  path: string
  name: string
}

export const api = {
  health: () => request<Health>('GET', '/v1/health'),
  libraries: {
    list: () => request<Library[]>('GET', '/v1/libraries'),
    add: (path: string) => request<Library>('POST', '/v1/libraries', { path }),
    remove: (id: string) => request<void>('DELETE', `/v1/libraries/${id}`)
  }
}
