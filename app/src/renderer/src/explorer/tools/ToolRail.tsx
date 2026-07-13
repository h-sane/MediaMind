import { CopyCheck, ScanFace, X } from 'lucide-react'
import { useEnsureLibrary } from '../../api/hooks'
import { isRealFolder, useExplorerStore } from '../../stores/explorer'
import type { ToolMode } from '../../stores/explorer'
import { useJobsStore, selectJobForLibrary } from '../../stores/jobs'

const TOOLS: { mode: Exclude<ToolMode, 'none'>; label: string; icon: React.ComponentType<{ className?: string }>; jobType: 'dedupe' | 'faces' }[] = [
  { mode: 'dedupe', label: 'Duplicate Detection', icon: CopyCheck, jobType: 'dedupe' },
  { mode: 'faces', label: 'Facial Recognition', icon: ScanFace, jobType: 'faces' }
]

/**
 * Bottom section of `NavigationPane` — lists the media tools (dedupe, faces)
 * below the drive/folder tree, in the space that tree otherwise leaves empty.
 * Always mounted (chrome, not a toggle); its rows disable/enable/run/highlight
 * based on whether a real folder is open and whether a tool is active for it.
 */
export function ToolRail(): React.JSX.Element {
  const currentPath = useExplorerStore((s) => s.currentPath)
  const toolMode = useExplorerStore((s) => s.toolMode)
  const setToolMode = useExplorerStore((s) => s.setToolMode)
  const jobs = useJobsStore((s) => s.jobs)

  const folderOpen = isRealFolder(currentPath)
  // Same query key `useEnsureLibrary` uses elsewhere — reads the cache,
  // never issues a second POST for a folder already resolved by ToolWorkspace.
  const { data: library } = useEnsureLibrary(currentPath)

  return (
    <div className="flex shrink-0 flex-col border-t border-zinc-200 bg-zinc-50 py-1">
      <p className="px-3 pb-1 pt-1 text-[11px] font-medium uppercase tracking-wide text-zinc-400">Tools</p>
      {TOOLS.map(({ mode, label, icon: Icon, jobType }) => {
        const isActive = toolMode === mode
        const job = library ? selectJobForLibrary(jobs, library.id, jobType) : undefined
        const isRunning = !!job

        return (
          <button
            key={mode}
            type="button"
            disabled={!folderOpen}
            onClick={() => setToolMode(isActive ? 'none' : mode)}
            title={folderOpen ? label : 'Open a folder to use this tool'}
            className={`group flex w-full items-center gap-1.5 py-1.5 pl-3 pr-2 text-left text-sm disabled:text-zinc-300 ${
              isActive ? 'bg-blue-50 text-blue-700' : 'text-zinc-700 hover:bg-zinc-100'
            }`}
          >
            <Icon className={`h-4 w-4 shrink-0 ${isActive ? 'text-blue-600' : 'text-zinc-400'}`} />
            <span className="flex-1 truncate">{label}</span>
            {isRunning && (
              <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-blue-500" title="Running…" />
            )}
            {isActive && (
              <span
                role="button"
                tabIndex={-1}
                onClick={(e) => {
                  e.stopPropagation()
                  setToolMode('none')
                }}
                title="Return to browsing"
                className="shrink-0 rounded p-0.5 text-blue-400 hover:bg-blue-100 hover:text-blue-700"
              >
                <X className="h-3.5 w-3.5" />
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
