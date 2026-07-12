import { useDiskUsage } from '../api/hooks'
import type { DiskUsage } from '../api/client'
import { HOME_PATH, isRealFolder, useExplorerStore } from '../stores/explorer'
import { useSelectionStore } from '../stores/selection'
import { useDirectoryListing } from './content/useDirectoryListing'
import { formatSize } from './format'

function DiskGauge({ usage }: { usage: DiskUsage }): React.JSX.Element {
  const pct = usage.total_bytes > 0 ? (usage.used_bytes / usage.total_bytes) * 100 : 0
  const low = pct >= 90 // matches Explorer's own low-space warning color

  return (
    <div className="flex shrink-0 items-center gap-1.5">
      <div className="h-2 w-24 overflow-hidden rounded-full bg-zinc-200">
        <div
          className={`h-full rounded-full ${low ? 'bg-red-500' : 'bg-blue-500'}`}
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </div>
      <span className="whitespace-nowrap">
        {formatSize(usage.free_bytes)} free of {formatSize(usage.total_bytes)}
      </span>
    </div>
  )
}

/** Bottom status bar: total item count in the current view, selection size
 * when anything is selected, and a disk-usage gauge for the current drive
 * (only while browsing an actual folder — "This PC" shows the drive list
 * itself, so there's no single disk to gauge there). Hidden entirely on
 * Home — it isn't a folder listing, so there's no item count to show. */
export function StatusBar(): React.JSX.Element | null {
  const { entries } = useDirectoryListing()
  const selectionCount = useSelectionStore((s) => s.selected.size)
  const currentPath = useExplorerStore((s) => s.currentPath)
  const diskUsageQuery = useDiskUsage(currentPath, isRealFolder(currentPath))

  if (currentPath === HOME_PATH) return null

  return (
    <div className="flex shrink-0 items-center justify-between border-t border-zinc-200 bg-zinc-50 px-3 py-1 text-xs text-zinc-500">
      <div className="flex items-center gap-3">
        <span>
          {entries.length} item{entries.length === 1 ? '' : 's'}
        </span>
        {selectionCount > 0 && <span>{selectionCount} selected</span>}
      </div>
      {diskUsageQuery.data && <DiskGauge usage={diskUsageQuery.data} />}
    </div>
  )
}
