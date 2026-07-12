import { useMemo, useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { Folder, X } from 'lucide-react'
import { api } from '../../api/client'
import { useFileMetadata } from '../../api/hooks'
import { FileThumbnail } from '../../components/FileThumbnail'
import { useExplorerStore } from '../../stores/explorer'
import { formatDate, formatDuration, formatSize } from '../format'
import type { DirEntry } from '../content/useDirectoryListing'

interface Props {
  open: boolean
  onClose: () => void
  /** Snapshot of the selected entries at the moment Properties was
   * requested — drives are meaningless here (no file-facts exist for a
   * drive root) so the caller filters them out before opening. */
  entries: DirEntry[]
}

type Tab = 'general' | 'details'

function Row({ label, value }: { label: string; value: string }): React.JSX.Element {
  return (
    <div className="flex justify-between gap-3 py-1">
      <dt className="shrink-0 text-zinc-400">{label}</dt>
      <dd className="truncate text-right text-zinc-700" title={value}>
        {value}
      </dd>
    </div>
  )
}

function AttributeCheckbox({ label, checked }: { label: string; checked: boolean | null | undefined }): React.JSX.Element {
  return (
    <label className="flex items-center gap-2 text-zinc-600">
      <input type="checkbox" checked={!!checked} disabled className="h-3.5 w-3.5" />
      {label}
    </label>
  )
}

function parentOf(path: string): string {
  const idx = Math.max(path.lastIndexOf('\\'), path.lastIndexOf('/'))
  return idx > 0 ? path.slice(0, idx) : path
}

/**
 * Explorer's Properties dialog (`Alt+Enter`). Single-file/folder facts come
 * straight off the already-fetched `DirEntry` (Phase G's bulk-listing
 * extension) plus `useFileMetadata` for the file-only fields (dimensions/
 * duration/owner) that stay too expensive to fetch for every row. A
 * multi-selection aggregates size/count across every selected folder via
 * `useQueries` against `folder-stats`, the same "unknown, computing" polling
 * shape the single-folder case already uses.
 */
export function PropertiesDialog({ open, onClose, entries }: Props): React.JSX.Element | null {
  const [tab, setTab] = useState<Tab>('general')
  const currentPath = useExplorerStore((s) => s.currentPath)

  const folderPaths = useMemo(() => entries.filter((e) => e.type === 'folder').map((e) => e.path), [entries])
  const folderStatsQueries = useQueries({
    queries: folderPaths.map((path) => ({
      queryKey: ['folder-stats', path],
      queryFn: () => api.fs.folderStats(path),
      enabled: open,
      refetchInterval: (query: { state: { data?: { item_count: number | null } } }) =>
        query.state.data?.item_count === null ? 1500 : false
    }))
  })

  const isSingle = entries.length === 1
  const singleEntry = isSingle ? entries[0] : null
  const isSingleFile = singleEntry?.type === 'file'
  const metadataQuery = useFileMetadata(singleEntry?.path ?? null, open && !!isSingleFile)

  if (!open || entries.length === 0) return null

  let totalBytes = 0
  let totalItems = 0
  let sizePending = false
  for (const entry of entries) {
    if (entry.type === 'file') {
      totalBytes += entry.size ?? 0
      totalItems += 1
    }
  }
  for (const q of folderStatsQueries) {
    if (q.data?.total_bytes != null) totalBytes += q.data.total_bytes
    else sizePending = true
    if (q.data?.item_count != null) totalItems += q.data.item_count
    else sizePending = true
  }

  const sizeDisplay = sizePending
    ? 'Calculating…'
    : `${formatSize(totalBytes)} (${totalBytes.toLocaleString()} bytes)`

  const typeDisplay = isSingle
    ? singleEntry!.type === 'folder'
      ? 'File folder'
      : (singleEntry!.kind ?? 'File')
    : entries.every((e) => e.type === 'folder')
      ? 'File folders'
      : entries.every((e) => e.type === 'file')
        ? 'Files'
        : 'Multiple types'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div
        className="flex max-h-[80vh] w-96 flex-col rounded-lg bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-2.5">
          <h2 className="text-sm font-semibold text-zinc-900">
            {isSingle ? `${singleEntry!.name} Properties` : `${entries.length} Items Properties`}
          </h2>
          <button type="button" onClick={onClose} className="rounded p-1 text-zinc-400 hover:bg-zinc-100">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex border-b border-zinc-200 px-2">
          {(['general', 'details'] as Tab[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 text-sm capitalize ${
                tab === t ? 'border-b-2 border-blue-500 font-medium text-zinc-900' : 'text-zinc-500 hover:text-zinc-700'
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3">
          {tab === 'general' ? (
            <>
              <div className="flex justify-center py-2">
                {isSingle && isSingleFile ? (
                  <FileThumbnail path={singleEntry!.path} kind={singleEntry!.kind ?? 'other'} className="h-16 w-16" />
                ) : (
                  <Folder className="h-14 w-14 text-amber-300" />
                )}
              </div>
              <dl className="text-xs">
                <Row label="Type" value={typeDisplay} />
                <Row label="Location" value={isSingle ? parentOf(singleEntry!.path) : (currentPath ?? '')} />
                <Row label="Size" value={sizeDisplay} />
                {folderPaths.length > 0 && (
                  <Row label="Contains" value={sizePending ? 'Calculating…' : `${totalItems} items`} />
                )}
                {isSingle && (
                  <>
                    <Row label="Created" value={formatDate(singleEntry!.created)} />
                    <Row label="Modified" value={formatDate(singleEntry!.mtime)} />
                    <Row label="Accessed" value={formatDate(singleEntry!.accessed)} />
                  </>
                )}
              </dl>
              {isSingle && (
                <div className="mt-3 flex gap-4 border-t border-zinc-100 pt-3 text-xs">
                  <AttributeCheckbox label="Read-only" checked={singleEntry!.readOnly} />
                  <AttributeCheckbox label="Hidden" checked={singleEntry!.hidden} />
                  <AttributeCheckbox label="System" checked={singleEntry!.system} />
                </div>
              )}
            </>
          ) : (
            <dl className="text-xs">
              {isSingle ? (
                <>
                  <Row label="Full path" value={singleEntry!.path} />
                  {isSingleFile && metadataQuery.data?.width != null && metadataQuery.data?.height != null && (
                    <Row label="Dimensions" value={`${metadataQuery.data.width} × ${metadataQuery.data.height}`} />
                  )}
                  {isSingleFile && metadataQuery.data?.duration_seconds != null && (
                    <Row label="Duration" value={formatDuration(metadataQuery.data.duration_seconds)} />
                  )}
                  {isSingleFile && <Row label="Owner" value={metadataQuery.data?.owner ?? '—'} />}
                </>
              ) : (
                <p className="text-zinc-400">No additional details for a multi-item selection.</p>
              )}
            </dl>
          )}
        </div>

        <div className="flex justify-end border-t border-zinc-200 px-4 py-2.5">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm text-white hover:bg-zinc-800"
          >
            OK
          </button>
        </div>
      </div>
    </div>
  )
}
