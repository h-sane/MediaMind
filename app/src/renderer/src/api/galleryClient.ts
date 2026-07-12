/**
 * Client for `GET /v1/fs/gallery` (Phase O — Gallery view). Built alongside
 * `client.ts`'s `fs` namespace but kept in its own file so this phase never
 * has to touch that shared, frozen module — same idiom `searchClient.ts`
 * already established for Phase I.
 */
import { request } from './client'

export interface GalleryItem {
  name: string
  path: string // absolute
  media_kind: 'image' | 'gif' | 'video' | 'audio'
  size: number
  mtime: number
}

export interface GalleryResponse {
  path: string // the root that was walked
  items: GalleryItem[] // sorted by mtime, most recent first
  truncated: boolean // true if more media exists than `items` includes
}

function fetchGallery(root: string, limit = 500): Promise<GalleryResponse> {
  const qs = `path=${encodeURIComponent(root)}&limit=${limit}`
  return request<GalleryResponse>('GET', `/v1/fs/gallery?${qs}`)
}

/**
 * `signal`-aware wrapper around `fetchGallery`, same cancellation shape as
 * `searchApi.search` — an aborted signal rejects immediately rather than
 * waiting on a stale response.
 */
export const galleryApi = {
  list: (root: string, signal?: AbortSignal): Promise<GalleryResponse> => {
    if (signal?.aborted) return Promise.reject(new DOMException('Aborted', 'AbortError'))
    const promise = fetchGallery(root)
    if (!signal) return promise
    return new Promise<GalleryResponse>((resolve, reject) => {
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
