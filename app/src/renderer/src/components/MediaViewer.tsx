import { useEffect } from 'react'
import { useBrowseRawUrl, useFileRawUrl } from '../api/hooks'

export interface MediaViewerFile {
  path: string
  kind: string
}

interface Props {
  /** Library-relative mode (existing screens). Omit to address each file's
   * `path` as an absolute filesystem path instead (the Explorer shell). */
  libraryId?: string
  files: MediaViewerFile[]
  index: number
  onClose: () => void
  onIndexChange: (index: number) => void
}

function fileName(path: string): string {
  const idx = path.lastIndexOf('/')
  return idx === -1 ? path : path.slice(idx + 1)
}

/**
 * Full-screen viewer for a single image or video, with prev/next through the
 * list it was opened from. Opened by clicking a thumbnail in the file grid —
 * MediaMind's "digicam" view onto the real files, not a re-import.
 */
export function MediaViewer({ libraryId, files, index, onClose, onIndexChange }: Props): React.JSX.Element {
  const file = files[index]
  const hasPrev = index > 0
  const hasNext = index < files.length - 1
  const libraryResult = useFileRawUrl(libraryId ?? '', file.path, !!libraryId)
  const browseResult = useBrowseRawUrl(file.path, !libraryId)
  const { url, failed } = libraryId ? libraryResult : browseResult

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent): void {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowRight' && hasNext) onIndexChange(index + 1)
      else if (e.key === 'ArrowLeft' && hasPrev) onIndexChange(index - 1)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [index, hasPrev, hasNext, onClose, onIndexChange])

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black/95" onClick={onClose}>
      <div
        className="flex items-center justify-between px-6 py-4 text-white"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="truncate text-sm" title={file.path}>
          {fileName(file.path)}
          <span className="ml-2 text-zinc-400">
            {index + 1} / {files.length}
          </span>
        </p>
        <button
          onClick={onClose}
          className="rounded-full p-1.5 text-zinc-300 transition hover:bg-white/10 hover:text-white"
          aria-label="Close"
        >
          <svg className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="relative flex flex-1 items-center justify-center overflow-hidden px-4 pb-6">
        {hasPrev && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onIndexChange(index - 1)
            }}
            className="absolute left-2 z-10 rounded-full bg-black/40 p-3 text-white transition hover:bg-black/60"
            aria-label="Previous"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
        )}

        {failed && <p className="text-sm text-red-400">Could not load this file.</p>}
        {!url && !failed && <p className="text-sm text-zinc-400">Loading…</p>}
        {url && file.kind === 'video' && (
          <video
            src={url}
            controls
            autoPlay
            className="max-h-full max-w-full"
            onClick={(e) => e.stopPropagation()}
          />
        )}
        {url && file.kind === 'audio' && (
          <audio
            src={url}
            controls
            autoPlay
            className="w-full max-w-md"
            onClick={(e) => e.stopPropagation()}
          />
        )}
        {url && file.kind !== 'video' && file.kind !== 'audio' && (
          <img
            src={url}
            alt=""
            className="max-h-full max-w-full object-contain"
            onClick={(e) => e.stopPropagation()}
          />
        )}

        {hasNext && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onIndexChange(index + 1)
            }}
            className="absolute right-2 z-10 rounded-full bg-black/40 p-3 text-white transition hover:bg-black/60"
            aria-label="Next"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
          </button>
        )}
      </div>
    </div>
  )
}
