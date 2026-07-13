import { useState } from 'react'
import { Folder, HardDrive, Music } from 'lucide-react'
import { useBrowseRawUrl, useFileMetadata } from '../../api/hooks'
import { FileThumbnail } from '../../components/FileThumbnail'
import { usePaneLayoutStore } from '../../stores/paneLayout'
import { useSelectionStore } from '../../stores/selection'
import { formatAttributes, formatDate, formatDuration, formatSize } from '../format'
import { useDirectoryListing } from '../content/useDirectoryListing'

type Tab = 'preview' | 'details'

/** Right-side collapsible pane (toggled from CommandBar's "Preview pane"
 * button), tabbed Preview/Details like real Explorer's own preview pane.
 * Preview shows a live thumbnail for images/GIFs, or inline `<video>`/
 * `<audio>` playback (via the existing `GET /v1/fs/raw` stream) for video/
 * audio. Details lists the full fact set — dimensions/duration/owner come
 * from `GET /v1/fs/metadata` (Phase E), everything else is already in the
 * directory listing so no extra request is needed for those fields. */
export function PreviewPane(): React.JSX.Element {
  const [tab, setTab] = useState<Tab>('preview')
  const selected = useSelectionStore((s) => s.selected)
  const { entries } = useDirectoryListing()
  const previewPaneWidth = usePaneLayoutStore((s) => s.previewPaneWidth)

  const singlePath = selected.size === 1 ? Array.from(selected)[0] : null
  const entry = singlePath ? entries.find((e) => e.path === singlePath) : undefined
  const isFile = entry?.type === 'file'
  // Called unconditionally (rules of hooks) — disabled whenever there's no
  // single file selection, so it never fires a request for that case.
  const metadataQuery = useFileMetadata(entry?.path ?? null, !!isFile)
  const isPlayable = isFile && (entry?.kind === 'video' || entry?.kind === 'audio')
  const rawResult = useBrowseRawUrl(entry?.path ?? '', !!isPlayable && tab === 'preview')

  if (selected.size === 0) {
    return (
      <aside
        style={{ width: previewPaneWidth }}
        className="flex h-full shrink-0 flex-col items-center justify-center border-l border-zinc-200 bg-zinc-50 p-4 text-center"
      >
        <p className="text-sm text-zinc-400">Select an item to see details.</p>
      </aside>
    )
  }

  if (selected.size > 1) {
    return (
      <aside
        style={{ width: previewPaneWidth }}
        className="flex h-full shrink-0 flex-col items-center justify-center border-l border-zinc-200 bg-zinc-50 p-4 text-center"
      >
        <p className="text-sm text-zinc-400">{selected.size} items selected.</p>
      </aside>
    )
  }

  if (!entry) {
    return <aside style={{ width: previewPaneWidth }} className="h-full shrink-0 border-l border-zinc-200 bg-zinc-50" />
  }

  return (
    <aside
      style={{ width: previewPaneWidth }}
      className="flex h-full shrink-0 flex-col border-l border-zinc-200 bg-zinc-50"
    >
      <div className="flex border-b border-zinc-200 px-2 pt-2">
        {(['preview', 'details'] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 text-xs capitalize ${
              tab === t
                ? 'border-b-2 border-blue-500 font-medium text-zinc-900'
                : 'text-zinc-500 hover:text-zinc-700'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {tab === 'preview' ? (
          <>
            {entry.kind === 'video' ? (
              <VideoPreview url={rawResult.url} failed={rawResult.failed} entry={entry} />
            ) : entry.kind === 'audio' ? (
              <AudioPreview url={rawResult.url} failed={rawResult.failed} />
            ) : isFile ? (
              <FileThumbnail path={entry.path} kind={entry.kind ?? 'other'} className="h-40 w-full" />
            ) : (
              <div className="flex h-40 w-full items-center justify-center rounded-lg bg-zinc-100">
                {entry.type === 'drive' ? (
                  <HardDrive className="h-14 w-14 text-zinc-300" />
                ) : (
                  <Folder className="h-14 w-14 text-amber-300" />
                )}
              </div>
            )}

            <h3 className="mt-3 break-words text-sm font-medium text-zinc-900">{entry.name}</h3>
          </>
        ) : (
          <dl className="space-y-1.5 text-xs text-zinc-500">
            <Row label="Full path" value={entry.path} />
            <Row label="Type" value={typeLabel(entry)} />
            {entry.size !== undefined && <Row label="Size" value={formatSize(entry.size)} />}
            {entry.created != null && <Row label="Created" value={formatDate(entry.created)} />}
            {entry.mtime !== undefined && <Row label="Modified" value={formatDate(entry.mtime)} />}
            {entry.accessed != null && <Row label="Accessed" value={formatDate(entry.accessed)} />}
            {isFile && metadataQuery.data?.width && metadataQuery.data?.height && (
              <Row label="Dimensions" value={`${metadataQuery.data.width} × ${metadataQuery.data.height}`} />
            )}
            {isFile && metadataQuery.data?.duration_seconds != null && (
              <Row label="Duration" value={formatDuration(metadataQuery.data.duration_seconds)} />
            )}
            {isFile && <Row label="Owner" value={metadataQuery.data?.owner ?? '—'} />}
            {(entry.readOnly || entry.hidden || entry.system) && (
              <Row label="Attributes" value={formatAttributes(entry.readOnly, entry.hidden, entry.system)} />
            )}
          </dl>
        )}
      </div>
    </aside>
  )
}

function VideoPreview({
  url,
  failed,
  entry
}: {
  url: string | null
  failed: boolean
  entry: { path: string; kind?: string }
}): React.JSX.Element {
  if (failed) {
    return (
      <div className="flex h-40 w-full items-center justify-center rounded-lg bg-zinc-100 text-center text-xs text-red-500">
        Could not load this file.
      </div>
    )
  }
  if (!url) {
    return <FileThumbnail path={entry.path} kind={entry.kind ?? 'video'} className="h-40 w-full" />
  }
  return <video src={url} controls className="h-40 w-full rounded-lg bg-black object-contain" />
}

function AudioPreview({ url, failed }: { url: string | null; failed: boolean }): React.JSX.Element {
  return (
    <div className="flex h-40 w-full flex-col items-center justify-center gap-2 rounded-lg bg-zinc-100 p-3">
      <Music className="h-12 w-12 text-zinc-300" />
      {failed ? (
        <p className="text-center text-xs text-red-500">Could not load this file.</p>
      ) : url ? (
        <audio src={url} controls className="w-full" />
      ) : (
        <p className="text-xs text-zinc-400">Loading…</p>
      )}
    </div>
  )
}

function typeLabel(entry: { type: string; kind?: string }): string {
  if (entry.type === 'drive') return 'Drive'
  if (entry.type === 'folder') return 'File folder'
  const kind = entry.kind ?? ''
  return kind.charAt(0).toUpperCase() + kind.slice(1)
}

function Row({ label, value }: { label: string; value: string }): React.JSX.Element {
  return (
    <div className="flex justify-between gap-2">
      <dt className="shrink-0 text-zinc-400">{label}</dt>
      <dd className="truncate text-right text-zinc-600" title={value}>
        {value}
      </dd>
    </div>
  )
}
