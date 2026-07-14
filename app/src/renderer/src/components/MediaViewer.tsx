import { useEffect, useRef, useState } from 'react'
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

const MIN_SCALE = 1
const MAX_SCALE = 6
const DOUBLE_CLICK_SCALE = 2.5

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

function touchDistance(touches: TouchList | React.TouchList): number {
  const a = touches[0]
  const b = touches[1]
  return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY)
}

/** Keeps a zoomed image/video from panning past its own edge — `el`'s
 * rendered rect already reflects `scale`, so dividing it back out gives the
 * unscaled box and, from that, how far the scaled box overhangs each side. */
function clampOffsetForEl(
  el: HTMLElement | null,
  scale: number,
  x: number,
  y: number
): { x: number; y: number } {
  if (!el || scale <= 1) return { x: 0, y: 0 }
  const rect = el.getBoundingClientRect()
  const baseW = rect.width / scale
  const baseH = rect.height / scale
  const maxX = (baseW * (scale - 1)) / 2
  const maxY = (baseH * (scale - 1)) / 2
  return { x: clamp(x, -maxX, maxX), y: clamp(y, -maxY, maxY) }
}

function fileName(path: string): string {
  const idx = path.lastIndexOf('/')
  return idx === -1 ? path : path.slice(idx + 1)
}

/**
 * Full-screen viewer for a single image or video, with prev/next through the
 * list it was opened from. Opened by clicking a thumbnail in the file grid —
 * MediaMind's "digicam" view onto the real files, not a re-import.
 *
 * Supports pinch-to-zoom (trackpad/touchscreen), scroll-to-zoom, and
 * drag-to-pan once zoomed, on both images and video.
 */
export function MediaViewer({ libraryId, files, index, onClose, onIndexChange }: Props): React.JSX.Element {
  const file = files[index]
  const hasPrev = index > 0
  const hasNext = index < files.length - 1
  const libraryResult = useFileRawUrl(libraryId ?? '', file.path, !!libraryId)
  const browseResult = useBrowseRawUrl(file.path, !libraryId)
  const { url, failed } = libraryId ? libraryResult : browseResult

  const mediaRef = useRef<HTMLElement | null>(null)
  const [scale, setScale] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [dragging, setDragging] = useState(false)
  const pinchRef = useRef<{ distance: number; scale: number } | null>(null)
  const dragRef = useRef<{ startX: number; startY: number; startOffsetX: number; startOffsetY: number } | null>(
    null
  )
  // The native touchmove listener below only rebinds when `url` changes, so
  // it can't close over fresh `scale` state across a zoom gesture — mirror
  // it into a ref it can read live instead.
  const scaleRef = useRef(scale)
  useEffect(() => {
    scaleRef.current = scale
  }, [scale])

  // A new file (navigated via prev/next, or the viewer reopened on a
  // different item) always starts unzoomed.
  useEffect(() => {
    setScale(1)
    setOffset({ x: 0, y: 0 })
  }, [index, file.path])

  // Zooming out must never leave the pan offset stranded outside the
  // (now smaller) allowed range.
  useEffect(() => {
    setOffset((prev) => clampOffsetForEl(mediaRef.current, scale, prev.x, prev.y))
  }, [scale])

  // Wheel/touchmove need a real preventDefault to stop the page/OS from
  // treating a trackpad pinch or scroll as its own zoom — React attaches
  // these as passive listeners by default, so they're bound natively here.
  useEffect(() => {
    const el = mediaRef.current
    if (!el) return

    function handleWheel(e: WheelEvent): void {
      e.preventDefault()
      const factor = Math.exp(-e.deltaY * 0.0015)
      setScale((s) => clamp(s * factor, MIN_SCALE, MAX_SCALE))
    }

    function handleTouchMove(e: TouchEvent): void {
      if (e.touches.length === 2 && pinchRef.current) {
        e.preventDefault()
        const dist = touchDistance(e.touches)
        const next = clamp((dist / pinchRef.current.distance) * pinchRef.current.scale, MIN_SCALE, MAX_SCALE)
        setScale(next)
      } else if (e.touches.length === 1 && dragRef.current) {
        e.preventDefault()
        const t = e.touches[0]
        const dx = t.clientX - dragRef.current.startX
        const dy = t.clientY - dragRef.current.startY
        setOffset(
          clampOffsetForEl(
            el,
            scaleRef.current,
            dragRef.current.startOffsetX + dx,
            dragRef.current.startOffsetY + dy
          )
        )
      }
    }

    el.addEventListener('wheel', handleWheel, { passive: false })
    el.addEventListener('touchmove', handleTouchMove, { passive: false })
    return () => {
      el.removeEventListener('wheel', handleWheel)
      el.removeEventListener('touchmove', handleTouchMove)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url])

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent): void {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowRight' && hasNext) onIndexChange(index + 1)
      else if (e.key === 'ArrowLeft' && hasPrev) onIndexChange(index - 1)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [index, hasPrev, hasNext, onClose, onIndexChange])

  function onMediaTouchStart(e: React.TouchEvent): void {
    if (e.touches.length === 2) {
      pinchRef.current = { distance: touchDistance(e.touches), scale }
      dragRef.current = null
    } else if (e.touches.length === 1 && scale > 1) {
      const t = e.touches[0]
      dragRef.current = { startX: t.clientX, startY: t.clientY, startOffsetX: offset.x, startOffsetY: offset.y }
      pinchRef.current = null
    }
  }

  function onMediaTouchEnd(e: React.TouchEvent): void {
    if (e.touches.length < 2) pinchRef.current = null
    if (e.touches.length < 1) dragRef.current = null
  }

  function onMediaMouseDown(e: React.MouseEvent): void {
    if (scale <= 1) return
    if (file.kind === 'video') {
      // Leave the native controls bar alone — panning shouldn't swallow
      // clicks on play/seek/volume while the video is zoomed in.
      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
      if (e.clientY > rect.bottom - 40) return
    }
    e.stopPropagation()
    e.preventDefault()
    const startX = e.clientX
    const startY = e.clientY
    const startOffset = offset
    setDragging(true)
    function onMove(ev: MouseEvent): void {
      const dx = ev.clientX - startX
      const dy = ev.clientY - startY
      setOffset(clampOffsetForEl(mediaRef.current, scale, startOffset.x + dx, startOffset.y + dy))
    }
    function onUp(): void {
      setDragging(false)
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  function onMediaDoubleClick(e: React.MouseEvent): void {
    e.stopPropagation()
    if (scale > 1) {
      setScale(1)
      setOffset({ x: 0, y: 0 })
    } else {
      setScale(DOUBLE_CLICK_SCALE)
    }
  }

  const zoomable = !!url && file.kind !== 'audio'
  const mediaStyle: React.CSSProperties = {
    transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
    cursor: scale > 1 ? (dragging ? 'grabbing' : 'grab') : 'default',
    touchAction: 'none'
  }

  return (
    <div className="fixed inset-0 z-[80] flex flex-col bg-black/95" onClick={onClose}>
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
            ref={(el) => {
              mediaRef.current = el
            }}
            src={url}
            controls
            autoPlay
            className="max-h-full max-w-full"
            style={mediaStyle}
            onClick={(e) => e.stopPropagation()}
            onDoubleClick={onMediaDoubleClick}
            onMouseDown={onMediaMouseDown}
            onTouchStart={onMediaTouchStart}
            onTouchEnd={onMediaTouchEnd}
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
            ref={(el) => {
              mediaRef.current = el
            }}
            src={url}
            alt=""
            className="max-h-full max-w-full select-none object-contain"
            style={mediaStyle}
            onClick={(e) => e.stopPropagation()}
            onDoubleClick={onMediaDoubleClick}
            onMouseDown={onMediaMouseDown}
            onTouchStart={onMediaTouchStart}
            onTouchEnd={onMediaTouchEnd}
            draggable={false}
          />
        )}
        {zoomable && scale > 1 && (
          <span className="pointer-events-none absolute bottom-2 right-2 rounded-full bg-black/50 px-2 py-0.5 text-[11px] text-zinc-300">
            {Math.round(scale * 100)}%
          </span>
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
