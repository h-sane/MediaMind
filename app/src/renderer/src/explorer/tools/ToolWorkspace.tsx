import { useEnsureLibrary } from '../../api/hooks'
import { isRealFolder, useExplorerStore } from '../../stores/explorer'
import { DedupeToolPanel } from './dedupe/DedupeToolPanel'
import { FacesToolPanel } from './faces/FacesToolPanel'

/**
 * Occupies the same slot `ContentPane` normally does (see `ExplorerShell.tsx`)
 * while a tool selected from `ToolRail` is active. Resolves the current
 * folder to a `libraryId` (registering it as one on first use — see
 * `useEnsureLibrary`) and hands off to the active tool's panel.
 */
export function ToolWorkspace(): React.JSX.Element {
  const currentPath = useExplorerStore((s) => s.currentPath)
  const toolMode = useExplorerStore((s) => s.toolMode)
  const { data: library, isPending, isError } = useEnsureLibrary(currentPath)

  if (!isRealFolder(currentPath)) {
    // Defensive only — ToolRail disables tool buttons off a real folder, so
    // toolMode should already be 'none' here (CLEARED_NAV_STATE resets it on
    // navigate). Nothing to work on if this is ever reached anyway.
    return <div className="relative flex-1 overflow-hidden bg-white" />
  }

  return (
    <div className="relative flex-1 overflow-hidden bg-white">
      {isPending ? (
        <p className="p-6 text-sm text-zinc-400">Preparing folder…</p>
      ) : isError || !library ? (
        <p className="p-6 text-sm text-red-600">Could not prepare this folder.</p>
      ) : toolMode === 'dedupe' ? (
        <DedupeToolPanel libraryId={library.id} folderPath={currentPath} />
      ) : toolMode === 'faces' ? (
        <FacesToolPanel libraryId={library.id} folderPath={currentPath} />
      ) : null}
    </div>
  )
}
