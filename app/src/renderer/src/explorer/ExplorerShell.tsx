import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { CommandBar } from './chrome/CommandBar'
import { FilterChips } from './chrome/FilterChips'
import { TabStrip } from './chrome/TabStrip'
import { TopChrome } from './chrome/TopChrome'
import { ContentPane } from './content/ContentPane'
import { RecentDeletionsDialog } from './deletions/RecentDeletionsDialog'
import { ConfirmDialog } from './interactions/ConfirmDialog'
import { useKeyboardShortcuts } from './interactions/useKeyboardShortcuts'
import { PaneResizer } from './layout/PaneResizer'
import { NavigationPane } from './nav/NavigationPane'
import { OpFailureToast } from './OpFailureToast'
import { PreviewPane } from './preview/PreviewPane'
import { PropertiesDialog } from './properties/PropertiesDialog'
import { FolderOptionsDialog } from './settings/FolderOptionsDialog'
import { StatusBar } from './StatusBar'
import { ToolWorkspace } from './tools/ToolWorkspace'
import { useFileOps } from './useFileOps'
import { useExplorerStore } from '../stores/explorer'
import { useFolderOptionsDialogStore } from '../stores/folderOptionsDialog'
import {
  NAV_PANE_MAX,
  NAV_PANE_MIN,
  PREVIEW_PANE_MAX,
  PREVIEW_PANE_MIN,
  usePaneLayoutStore
} from '../stores/paneLayout'
import { usePropertiesDialogStore } from '../stores/propertiesDialog'
import { useRecentDeletionsDialogStore } from '../stores/recentDeletionsDialog'

/**
 * MediaMind's primary UI layer: a Windows-Explorer-style shell restricted to
 * media-containing folders and media files. Everything else (dedupe, face
 * recognition, organize) is a later pass on top of this — see the Explorer
 * clone pivot plan.
 */
export function ExplorerShell(): React.JSX.Element {
  const currentPath = useExplorerStore((s) => s.currentPath)
  const filtersOpen = useExplorerStore((s) => s.filtersOpen)
  const previewPaneOpen = useExplorerStore((s) => s.previewPaneOpen)
  const toolMode = useExplorerStore((s) => s.toolMode)
  const qc = useQueryClient()
  const fileOps = useFileOps()
  const [confirmPermanentDelete, setConfirmPermanentDelete] = useState(false)
  const propertiesEntries = usePropertiesDialogStore((s) => s.entries)
  const closeProperties = usePropertiesDialogStore((s) => s.close)
  const recentDeletionsOpen = useRecentDeletionsDialogStore((s) => s.isOpen)
  const closeRecentDeletions = useRecentDeletionsDialogStore((s) => s.close)
  const folderOptionsOpen = useFolderOptionsDialogStore((s) => s.isOpen)
  const closeFolderOptions = useFolderOptionsDialogStore((s) => s.close)
  const setNavPaneWidth = usePaneLayoutStore((s) => s.setNavPaneWidth)
  const setPreviewPaneWidth = usePaneLayoutStore((s) => s.setPreviewPaneWidth)

  useKeyboardShortcuts({
    onRequestPermanentDelete: () => setConfirmPermanentDelete(true)
  })

  const refreshing = qc.isFetching({ queryKey: ['browse', currentPath] }) > 0
  const selectionCount = fileOps.selectedPaths.length

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden bg-white text-zinc-900">
      <TabStrip />
      <TopChrome
        onRefresh={() => {
          qc.invalidateQueries({ queryKey: ['browse'] })
          qc.invalidateQueries({ queryKey: ['fs-gallery'] })
        }}
        refreshing={refreshing}
      />
      <CommandBar />
      {filtersOpen && <FilterChips />}
      <div className="flex min-h-0 flex-1">
        <NavigationPane />
        <PaneResizer
          orientation="vertical"
          getValue={() => usePaneLayoutStore.getState().navPaneWidth}
          setValue={setNavPaneWidth}
          min={NAV_PANE_MIN}
          max={NAV_PANE_MAX}
        />
        {toolMode === 'none' ? <ContentPane /> : <ToolWorkspace />}
        {previewPaneOpen && toolMode === 'none' && (
          <>
            <PaneResizer
              orientation="vertical"
              getValue={() => usePaneLayoutStore.getState().previewPaneWidth}
              setValue={setPreviewPaneWidth}
              min={PREVIEW_PANE_MIN}
              max={PREVIEW_PANE_MAX}
              invert
            />
            <PreviewPane />
          </>
        )}
      </div>
      <StatusBar />
      <OpFailureToast />
      <ConfirmDialog
        open={confirmPermanentDelete}
        title="Permanently delete?"
        message={`Permanently delete ${selectionCount} item${selectionCount === 1 ? '' : 's'}? This can't be undone — it will not go to the Recycle Bin.`}
        confirmLabel="Delete permanently"
        onConfirm={() => {
          fileOps.deleteSelected(true)
          setConfirmPermanentDelete(false)
        }}
        onCancel={() => setConfirmPermanentDelete(false)}
      />
      <PropertiesDialog
        open={propertiesEntries !== null}
        entries={propertiesEntries ?? []}
        onClose={closeProperties}
      />
      <RecentDeletionsDialog open={recentDeletionsOpen} onClose={closeRecentDeletions} />
      <FolderOptionsDialog open={folderOptionsOpen} onClose={closeFolderOptions} />
    </div>
  )
}
