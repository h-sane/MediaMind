/**
 * Client for `GET /v1/fs/search` (Phase I — recursive / cross-subfolder
 * search). Built alongside `client.ts`'s `fs` namespace but kept in its own
 * file so this phase never has to touch that shared, frozen module — see
 * that file's `fs.list`/`fs.metadata` entries for the idiom this follows.
 */
import { request } from './client'

export interface SearchResult {
  kind: 'folder' | 'file'
  name: string
  path: string // absolute
  media_kind: 'image' | 'gif' | 'video' | 'audio' | null // null for folders
  size: number | null // null for folders
  mtime: number
}

export interface SearchResponse {
  path: string // the root that was searched
  query: string
  results: SearchResult[]
  truncated: boolean // true if the result cap was hit — more matches may exist
}

function searchDirectory(root: string, query: string, limit = 200): Promise<SearchResponse> {
  const qs = `path=${encodeURIComponent(root)}&query=${encodeURIComponent(query)}&limit=${limit}`
  return request<SearchResponse>('GET', `/v1/fs/search?${qs}`)
}

/**
 * `signal`-aware wrapper around `searchDirectory`. `request()` itself has no
 * signal parameter (it's shared, frozen code — see module docstring), so
 * cancellation here is cooperative at the promise level: an aborted signal
 * rejects the caller's promise immediately rather than waiting on a stale
 * response. The backend walk (`core/search.py::iter_search_hits`) is bounded
 * on its own by a result cap and a client-disconnect check, so a query that
 * outlives its usefulness doesn't run forever either way.
 */
export const searchApi = {
  search: (root: string, query: string, signal?: AbortSignal): Promise<SearchResponse> => {
    if (signal?.aborted) return Promise.reject(new DOMException('Aborted', 'AbortError'))
    const promise = searchDirectory(root, query)
    if (!signal) return promise
    return new Promise<SearchResponse>((resolve, reject) => {
      const onAbort = (): void => reject(new DOMException('Aborted', 'AbortError'))
      signal.addEventListener('abort', onAbort, { once: true })
      promise.then(
        (value) => {
          signal.removeEventListener('abort', onAbort)
          resolve(value)
        },
        (err) => {
          signal.removeEventListener('abort', onAbort)
          reject(err)
        }
      )
    })
  }
}
