import { useCallback, useEffect, useRef, useState } from 'react'
import { Check, ChevronLeft, ChevronRight, Folder, X } from 'lucide-react'
import { useFileRawUrl } from '../../../api/hooks'
import { useZoomScale } from '../../../hooks/useZoomScale'
import { MediaViewer } from '../../../components/MediaViewer'
import { Thumbnail } from '../../../components/Thumbnail'
import { FileThumbnail } from '../../../components/FileThumbnail'
import { formatBytes, formatDate, subfolderOf } from './format'
import type { DuplicateFile, DuplicateGroup } from '../../../api/client'

// ---------------------------------------------------------------------------
// GalleryFileCard
// ---------------------------------------------------------------------------

function GalleryFileCard({
  file,
  libraryId,
  folderName,
  onToggle,
  onOpenSingle,
  onVideoRef,
  onVideoReady,
  onVideoPlay,
  onVideoPause,
  onVideoFailed
}: {
  file: DuplicateFile
  libraryId: string
  folderName: string
  onToggle: (id: number, current: DuplicateFile['resolution']) => void
  onOpenSingle: (file: DuplicateFile) => void
  onVideoRef: (fileId: number, el: HTMLVideoElement | null) => void
  onVideoReady: (fileId: number) => void
  onVideoPlay: (fileId: number) => void
  onVideoPause: (fileId: number) => void
  onVideoFailed: (fileId: number) => void
}): React.JSX.Element {
  const marked = file.resolution === 'trash'
  const location = subfolderOf(file.path, folderName)
  const isVideo = file.kind === 'video'
  const raw = useFileRawUrl(libraryId, file.path, isVideo)

  useEffect(() => {
    if (isVideo && raw.failed) onVideoFailed(file.id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [raw.failed])

  return (
    <div
      className={`flex flex-col overflow-hidden rounded-2xl border-2 transition ${
        marked ? 'border-red-500/70 bg-red-950/20' : 'border-zinc-700 bg-zinc-900'
      }`}
    >
      <div className="flex items-center gap-1.5 border-b border-zinc-800 px-3 py-2">
        <Folder className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
        <span className="truncate text-xs font-medium text-zinc-300" title={location}>
          {location}
        </span>
        {file.suggested_keep && (
          <span className="ml-auto shrink-0 rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
            Suggested keep
          </span>
        )}
      </div>

      <div
        className="relative aspect-video cursor-zoom-in overflow-hidden bg-black"
        title="Double-click for a full-screen view of just this file"
        onDoubleClick={() => onOpenSingle(file)}
      >
        {isVideo ? (
          raw.failed ? (
            <p className="absolute inset-0 flex items-center justify-center px-4 text-center text-xs text-red-400">
              Could not load this file.
            </p>
          ) : raw.url ? (
            <video
              ref={(el) => onVideoRef(file.id, el)}
              src={raw.url}
              controls
              // `absolute inset-0` (not h-full/w-full in flow) keeps a
              // portrait video's own intrinsic aspect ratio from leaking
              // into this grid cell's auto row-height calculation and
              // blowing the card out past the aspect-video box.
              className="absolute inset-0 h-full w-full object-contain"
              onLoadedData={() => onVideoReady(file.id)}
              onPlay={() => onVideoPlay(file.id)}
              onPause={() => onVideoPause(file.id)}
            />
          ) : (
            <div className="absolute inset-0">
              <FileThumbnail
                libraryId={libraryId}
                path={file.path}
                kind={file.kind}
                size={1024}
                fit="contain"
                className="h-full w-full"
              />
            </div>
          )
        ) : (
          <div className="absolute inset-0">
            <FileThumbnail
              libraryId={libraryId}
              path={file.path}
              kind={file.kind}
              size={1024}
              fit="contain"
              className="h-full w-full"
            />
          </div>
        )}
      </div>

      <div className="px-3 py-2">
        <p className="truncate text-sm font-medium text-zinc-100" title={file.path}>
          {file.path.split('/').pop()}
        </p>
        <p className="mt-0.5 text-xs text-zinc-500">
          {file.width > 0 ? `${file.width}×${file.height} · ` : ''}
          {formatBytes(file.size)} · {formatDate(file.mtime)}
        </p>
      </div>

      <div className="border-t border-zinc-800 p-3">
        <button
          type="button"
          onClick={() => onToggle(file.id, file.resolution)}
          className={`w-full rounded-xl py-2 text-sm font-medium transition ${
            marked ? 'bg-zinc-700 text-white hover:bg-zinc-600' : 'bg-red-600 text-white hover:bg-red-500'
          }`}
        >
          {marked ? 'Keep this file' : 'Mark for deletion'}
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// DuplicateGalleryModal
// ---------------------------------------------------------------------------

interface Props {
  groups: DuplicateGroup[]
  libraryId: string
  folderName: string
  initialGroupId: number
  onToggle: (fileId: number, current: DuplicateFile['resolution']) => void
  onClose: () => void
}

/** Fullscreen side-by-side comparison mode: a sidebar of every duplicate
 * group (click one to jump to it) and a main pane that lays every file in
 * the active group out together with its subfolder and a per-file "mark for
 * deletion" action — so the user never has to decide between two files
 * without knowing which folder each one lives in. */
export function DuplicateGalleryModal({
  groups,
  libraryId,
  folderName,
  initialGroupId,
  onToggle,
  onClose
}: Props): React.JSX.Element {
  const [activeGroupId, setActiveGroupId] = useState(initialGroupId)
  const [singleViewFile, setSingleViewFile] = useState<DuplicateFile | null>(null)
  const activeIndex = groups.findIndex((g) => g.id === activeGroupId)
  const activeGroup = groups[activeIndex] ?? groups[0]

  function goTo(index: number): void {
    if (index < 0 || index >= groups.length) return
    setActiveGroupId(groups[index].id)
  }

  // Every video in the currently open group plays automatically, together,
  // as soon as it's ready — no per-file play button. Because each
  // GalleryFileCard is keyed by file id, switching groups unmounts the old
  // group's <video> elements (stopping playback) and mounts fresh ones for
  // the new group (so revisiting a group always restarts from 0, in sync).
  const videoRefs = useRef<Map<number, HTMLVideoElement>>(new Map())
  const readyIdsRef = useRef<Set<number>>(new Set())
  const failedIdsRef = useRef<Set<number>>(new Set())
  const syncingRef = useRef(false)
  const expectedVideoIds = activeGroup.files.filter((f) => f.kind === 'video').map((f) => f.id)

  const playGroupSynced = useCallback(() => {
    const elements = expectedVideoIds
      .map((id) => videoRefs.current.get(id))
      .filter((el): el is HTMLVideoElement => !!el)
    if (elements.length === 0) return
    syncingRef.current = true
    elements.forEach((el) => {
      el.currentTime = 0
    })
    Promise.all(elements.map((el) => el.play().catch(() => {}))).finally(() => {
      syncingRef.current = false
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeGroupId])

  // A video that fails to load must not block the rest of the group from
  // autoplaying — only wait on the ones that can actually play.
  const pendingVideoIds = expectedVideoIds.filter((id) => !failedIdsRef.current.has(id))

  const onVideoRef = useCallback((fileId: number, el: HTMLVideoElement | null) => {
    if (el) {
      videoRefs.current.set(fileId, el)
    } else {
      videoRefs.current.delete(fileId)
      readyIdsRef.current.delete(fileId)
    }
  }, [])

  const onVideoReady = useCallback(
    (fileId: number) => {
      readyIdsRef.current.add(fileId)
      if (pendingVideoIds.length > 0 && pendingVideoIds.every((id) => readyIdsRef.current.has(id))) {
        playGroupSynced()
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeGroupId, playGroupSynced]
  )

  const onVideoFailed = useCallback(
    (fileId: number) => {
      failedIdsRef.current.add(fileId)
      const remaining = expectedVideoIds.filter((id) => !failedIdsRef.current.has(id))
      if (remaining.length > 0 && remaining.every((id) => readyIdsRef.current.has(id))) {
        playGroupSynced()
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeGroupId, playGroupSynced]
  )

  // Native play/pause on any one video (e.g. the user clicks its controls)
  // mirrors to the rest of the group, so comparing videos never requires
  // pressing play separately on each one.
  const onVideoPlay = useCallback((fileId: number) => {
    if (syncingRef.current) return
    syncingRef.current = true
    videoRefs.current.forEach((el, id) => {
      if (id !== fileId && el.paused) el.play().catch(() => {})
    })
    syncingRef.current = false
  }, [])

  const onVideoPause = useCallback((fileId: number) => {
    if (syncingRef.current) return
    syncingRef.current = true
    videoRefs.current.forEach((el, id) => {
      if (id !== fileId && !el.paused) el.pause()
    })
    syncingRef.current = false
  }, [])

  useEffect(() => {
    // The single-file viewer owns keyboard input (Escape/arrows) while it's
    // open, and stacks visually above this modal — this modal's own
    // shortcuts must stand down so Escape closes just the single view first.
    if (singleViewFile) return
    function onKey(e: KeyboardEvent): void {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowRight') goTo(activeIndex + 1)
      if (e.key === 'ArrowLeft') goTo(activeIndex - 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIndex, singleViewFile])

  const galleryScrollRef = useRef<HTMLDivElement>(null)
  const [zoom] = useZoomScale(galleryScrollRef, { min: 0.5, max: 2 })
  const cardMinWidth = Math.round(260 * zoom)

  return (
    <div className="fixed inset-0 z-[70] flex bg-zinc-950">
      <aside className="flex w-64 shrink-0 flex-col border-r border-zinc-800 bg-zinc-900">
        <div className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-white">Duplicates ({groups.length})</h2>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {groups.map((g, i) => {
            const resolved = g.files.every((f) => f.resolution !== null)
            const active = g.id === activeGroupId
            return (
              <button
                key={g.id}
                type="button"
                onClick={() => setActiveGroupId(g.id)}
                className={`mb-1 flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition ${
                  active ? 'bg-zinc-700' : 'hover:bg-zinc-800'
                }`}
              >
                <div className="h-10 w-10 shrink-0 overflow-hidden rounded-md bg-zinc-800">
                  <Thumbnail libraryId={libraryId} memberId={g.files[0].id} size={64} className="h-full w-full" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-zinc-200">
                    Group {i + 1} · {g.files.length} files
                  </p>
                  <p className="truncate text-[10px] text-zinc-500">
                    {g.match === 'exact' ? 'Exact copy' : 'Visually similar'}
                  </p>
                </div>
                {resolved && <Check className="h-3.5 w-3.5 shrink-0 text-emerald-400" />}
              </button>
            )
          })}
        </div>
      </aside>

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-3">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => goTo(activeIndex - 1)}
              disabled={activeIndex <= 0}
              className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-white disabled:opacity-30"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <span className="text-sm text-zinc-300">
              Group {activeIndex + 1} of {groups.length}
            </span>
            <button
              type="button"
              onClick={() => goTo(activeIndex + 1)}
              disabled={activeIndex >= groups.length - 1}
              className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-white disabled:opacity-30"
            >
              <ChevronRight className="h-5 w-5" />
            </button>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div ref={galleryScrollRef} className="flex-1 overflow-y-auto p-6">
          <div
            className="grid gap-4"
            style={{ gridTemplateColumns: `repeat(auto-fit, minmax(${cardMinWidth}px, 1fr))` }}
          >
            {activeGroup.files.map((f) => (
              <GalleryFileCard
                key={f.id}
                file={f}
                libraryId={libraryId}
                folderName={folderName}
                onToggle={onToggle}
                onOpenSingle={setSingleViewFile}
                onVideoRef={onVideoRef}
                onVideoReady={onVideoReady}
                onVideoPlay={onVideoPlay}
                onVideoPause={onVideoPause}
                onVideoFailed={onVideoFailed}
              />
            ))}
          </div>
        </div>
      </div>

      {singleViewFile && (
        <MediaViewer
          libraryId={libraryId}
          files={[{ path: singleViewFile.path, kind: singleViewFile.kind }]}
          index={0}
          onClose={() => setSingleViewFile(null)}
          onIndexChange={() => {}}
        />
      )}
    </div>
  )
}
