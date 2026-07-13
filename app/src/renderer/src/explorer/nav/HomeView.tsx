import { useState } from 'react'
import { Folder } from 'lucide-react'
import { FileThumbnail } from '../../components/FileThumbnail'
import { MediaViewer } from '../../components/MediaViewer'
import { useQuickAccess, useRecentFiles, useRecordRecentFile, useSettings } from '../../api/hooks'
import { useExplorerStore } from '../../stores/explorer'
import { useFolderDropTarget } from '../dnd/useFolderDropTarget'
import { formatDate, formatSize } from '../format'
import type { QuickAccessEntry, RecentFile } from '../../api/client'

/** One pinned-folder tile — a drop target for moving/copying into it, same
 * as a pin row in the nav pane (`QuickAccess.tsx`), just laid out as a card
 * instead of a list row. */
function PinTile({ pin, onNavigate }: { pin: QuickAccessEntry; onNavigate: (path: string) => void }): React.JSX.Element {
  const { ref, isOver } = useFolderDropTarget(pin.path)

  return (
    <button
      ref={ref}
      type="button"
      onClick={() => onNavigate(pin.path)}
      title={pin.path}
      className={`flex min-w-0 items-center gap-2.5 rounded-lg border p-2.5 text-left ${
        isOver ? 'border-blue-400 bg-blue-50 ring-1 ring-inset ring-blue-400' : 'border-zinc-200 hover:bg-zinc-50'
      }`}
    >
      <Folder className="h-8 w-8 shrink-0 text-amber-400" fill="currentColor" strokeWidth={1} />
      <span className="min-w-0 truncate text-sm text-zinc-700">{pin.name}</span>
    </button>
  )
}

/** One recently-opened file tile — clicking it re-opens the file full-screen
 * (same `MediaViewer` the content pane uses) and refreshes its recency. */
function RecentTile({ file, onOpen }: { file: RecentFile; onOpen: (path: string) => void }): React.JSX.Element {
  return (
    <button
      type="button"
      onClick={() => onOpen(file.path)}
      title={file.path}
      className="flex min-w-0 flex-col gap-1.5 rounded-lg border border-zinc-200 p-2 text-left hover:bg-zinc-50"
    >
      <FileThumbnail path={file.path} kind={file.kind} className="aspect-video w-full" />
      <span className="min-w-0 truncate text-sm text-zinc-700">{file.name}</span>
      <span className="truncate text-xs text-zinc-400">
        {formatDate(file.opened_at)}
        {file.size ? ` · ${formatSize(file.size)}` : ''}
      </span>
    </button>
  )
}

/**
 * The Explorer shell's default landing page (Phase N) — pinned folders and
 * recently-opened files, like real Explorer's own Home. Reached by
 * navigating to `HOME_PATH`; unlike every other `currentPath` value this
 * isn't a folder listing, so it renders its own layout instead of one of
 * `ContentPane`'s view modes.
 */
export function HomeView(): React.JSX.Element {
  const { data: quickAccess } = useQuickAccess()
  const { data: recent } = useRecentFiles()
  const { data: settings } = useSettings()
  const navigate = useExplorerStore((s) => s.navigate)
  const recordRecent = useRecordRecentFile()
  const [viewerIndex, setViewerIndex] = useState<number | null>(null)

  const pins = quickAccess?.pins ?? []
  const recentFilesEnabled = settings?.recent_files_enabled ?? true
  const recentFiles = recent?.files ?? []
  const viewerFiles = recentFiles.map((f) => ({ path: f.path, kind: f.kind }))

  function openRecent(path: string): void {
    const idx = recentFiles.findIndex((f) => f.path === path)
    if (idx === -1) return
    recordRecent.mutate(path)
    setViewerIndex(idx)
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <section>
        <h2 className="mb-2 text-sm font-medium text-zinc-500">Quick access</h2>
        {pins.length === 0 ? (
          <p className="text-sm text-zinc-400">
            No pinned folders yet — right-click a folder and choose "Pin to Quick access".
          </p>
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-2">
            {pins.map((p) => (
              <PinTile key={p.path} pin={p} onNavigate={navigate} />
            ))}
          </div>
        )}
      </section>

      <section className="mt-6">
        <h2 className="mb-2 text-sm font-medium text-zinc-500">Recent files</h2>
        {!recentFilesEnabled ? (
          <p className="text-sm text-zinc-400">
            Recent files is turned off — enable it in Folder Options to see files you open here.
          </p>
        ) : recentFiles.length === 0 ? (
          <p className="text-sm text-zinc-400">Files you open will show up here.</p>
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3">
            {recentFiles.map((f) => (
              <RecentTile key={f.path} file={f} onOpen={openRecent} />
            ))}
          </div>
        )}
      </section>

      {viewerIndex !== null && (
        <MediaViewer
          files={viewerFiles}
          index={viewerIndex}
          onClose={() => setViewerIndex(null)}
          onIndexChange={setViewerIndex}
        />
      )}
    </div>
  )
}
