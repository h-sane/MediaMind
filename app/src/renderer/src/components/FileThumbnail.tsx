import { Music } from 'lucide-react'
import { useBrowseThumbnailUrl, useFileThumbnailUrl } from '../api/hooks'
import { useNearViewport } from '../hooks/useNearViewport'

const MEDIA_KINDS = new Set(['image', 'gif', 'video'])

interface Props {
  /** Library-relative mode (existing screens). Omit to address `path` as an
   * absolute filesystem path instead (the Explorer shell — no library needed). */
  libraryId?: string
  path: string
  kind: string
  className?: string
  size?: number
  fit?: 'cover' | 'contain'
}

function FileIcon({ label }: { label: string }): React.JSX.Element {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-1 text-zinc-300">
      <svg className="h-8 w-8" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z"
        />
      </svg>
      <span className="text-[10px] uppercase tracking-wide">{label}</span>
    </div>
  )
}

function AudioIcon({ label }: { label: string }): React.JSX.Element {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-1 text-zinc-300">
      <Music className="h-8 w-8" strokeWidth={1.5} />
      <span className="text-[10px] uppercase tracking-wide">{label}</span>
    </div>
  )
}

/**
 * Thumbnail for any file in a library, addressed by relative path (no scan
 * or DB row needed). Image/gif/video get a live thumbnail; audio (no visual
 * frame to render) gets a music-note icon; everything else gets a generic
 * icon; undecodable media gets a static "unreadable" tile — one bad file
 * never breaks the grid.
 */
export function FileThumbnail({
  libraryId,
  path,
  kind,
  className = '',
  size = 256,
  fit = 'cover'
}: Props): React.JSX.Element {
  const [ref, visible] = useNearViewport<HTMLDivElement>()
  const isMedia = MEDIA_KINDS.has(kind)
  const wantFetch = visible && isMedia
  const libraryResult = useFileThumbnailUrl(libraryId ?? '', path, size, !!libraryId && wantFetch)
  const browseResult = useBrowseThumbnailUrl(path, size, !libraryId && wantFetch)
  const { url, failed } = libraryId ? libraryResult : browseResult

  const ext = path.includes('.') ? path.slice(path.lastIndexOf('.') + 1) : 'file'

  return (
    <div ref={ref} className={`relative overflow-hidden rounded-lg bg-zinc-100 ${className}`}>
      {url ? (
        <img
          src={url}
          alt=""
          draggable={false}
          className={`h-full w-full ${fit === 'cover' ? 'object-cover' : 'object-contain'}`}
        />
      ) : kind === 'audio' ? (
        <AudioIcon label={ext} />
      ) : !isMedia ? (
        <FileIcon label={ext} />
      ) : failed ? (
        <FileIcon label="unreadable" />
      ) : (
        <div className="h-full w-full animate-pulse bg-zinc-100" aria-label="Loading thumbnail" />
      )}
      {(kind === 'video' || kind === 'gif') && (
        <span className="absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-white">
          {kind}
        </span>
      )}
    </div>
  )
}
