import { useMemo, useState } from 'react'
import { MediaViewer } from '../../components/MediaViewer'
import { useRecordRecentFile } from '../../api/hooks'
import { HOME_PATH, isRealFolder, useExplorerStore } from '../../stores/explorer'
import { useFolderDropTarget } from '../dnd/useFolderDropTarget'
import { ContentModeView } from './ContentModeView'
import { DetailsView } from './DetailsView'
import { GalleryView } from './GalleryView'
import { HomeView } from '../nav/HomeView'
import { IconGridView } from './IconGridView'
import { ListView } from './ListView'
import { TilesView } from './TilesView'
import { useDirectoryListing } from './useDirectoryListing'

export function ContentPane(): React.JSX.Element {
  const viewMode = useExplorerStore((s) => s.viewMode)
  const currentPath = useExplorerStore((s) => s.currentPath)
  const searchQuery = useExplorerStore((s) => s.searchQuery)
  const filterType = useExplorerStore((s) => s.filterType)
  const filterDate = useExplorerStore((s) => s.filterDate)
  const filterSize = useExplorerStore((s) => s.filterSize)
  const filtersActive = !!searchQuery || filterType !== 'all' || filterDate !== 'any' || filterSize !== 'any'
  const { entries, isPending, isError, isRoot } = useDirectoryListing()
  const [viewerIndex, setViewerIndex] = useState<number | null>(null)
  const recordRecent = useRecordRecentFile()
  // Dropping OS files onto empty background (not onto a specific folder
  // tile) copies them into the folder that's currently open. Home isn't a
  // real folder to drop into, same reasoning as every other file-op guard.
  const { ref: dropRef, isOver } = useFolderDropTarget(isRealFolder(currentPath) ? currentPath : null)

  const mediaFiles = useMemo(
    () =>
      entries
        .filter((e) => e.type === 'file')
        .map((e) => ({ path: e.path, kind: e.kind ?? 'other' })),
    [entries]
  )

  function openFile(path: string): void {
    const idx = mediaFiles.findIndex((f) => f.path === path)
    if (idx !== -1) {
      recordRecent.mutate(path)
      setViewerIndex(idx)
    }
  }

  if (currentPath === HOME_PATH) {
    return <HomeView />
  }

  return (
    <div
      ref={dropRef}
      className={`relative flex-1 overflow-hidden bg-white ${isOver ? 'ring-2 ring-inset ring-blue-400' : ''}`}
    >
      {isPending ? (
        <p className="p-6 text-sm text-zinc-400">Loading…</p>
      ) : isError ? (
        <p className="p-6 text-sm text-red-600">Could not read this location.</p>
      ) : entries.length === 0 ? (
        <div className="flex h-full items-center justify-center">
          <p className="text-sm text-zinc-400">
            {isRoot
              ? 'No drives found.'
              : filtersActive
                ? 'No items match the current search or filters.'
                : 'This folder is empty.'}
          </p>
        </div>
      ) : viewMode === 'icons' ? (
        <IconGridView entries={entries} onOpenFile={openFile} />
      ) : viewMode === 'list' ? (
        <ListView entries={entries} onOpenFile={openFile} />
      ) : viewMode === 'tiles' ? (
        <TilesView entries={entries} onOpenFile={openFile} />
      ) : viewMode === 'content' ? (
        <ContentModeView entries={entries} onOpenFile={openFile} />
      ) : viewMode === 'gallery' ? (
        <GalleryView entries={entries} onOpenFile={openFile} />
      ) : (
        <DetailsView entries={entries} onOpenFile={openFile} />
      )}

      {viewerIndex !== null && (
        <MediaViewer
          files={mediaFiles}
          index={viewerIndex}
          onClose={() => setViewerIndex(null)}
          onIndexChange={setViewerIndex}
        />
      )}
    </div>
  )
}
