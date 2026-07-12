import { useExplorerStore } from '../../stores/explorer'
import type { FilterDate, FilterSize, FilterType } from '../../stores/explorer'

const TYPE_OPTIONS: { value: FilterType; label: string }[] = [
  { value: 'all', label: 'All types' },
  { value: 'image', label: 'Images' },
  { value: 'gif', label: 'GIFs' },
  { value: 'video', label: 'Videos' },
  { value: 'audio', label: 'Audio' }
]

const DATE_OPTIONS: { value: FilterDate; label: string }[] = [
  { value: 'any', label: 'Any time' },
  { value: 'today', label: 'Today' },
  { value: 'week', label: 'This week' },
  { value: 'month', label: 'This month' },
  { value: 'older', label: 'Older' }
]

const SIZE_OPTIONS: { value: FilterSize; label: string }[] = [
  { value: 'any', label: 'Any size' },
  { value: 'small', label: 'Small (<1 MB)' },
  { value: 'medium', label: 'Medium (1-10 MB)' },
  { value: 'large', label: 'Large (>10 MB)' }
]

function ChipGroup<T extends string>({
  options,
  value,
  onChange
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
}): React.JSX.Element {
  return (
    <div className="flex flex-wrap items-center gap-1">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`rounded-full border px-2.5 py-1 text-xs ${
            value === opt.value
              ? 'border-blue-200 bg-blue-50 text-blue-700'
              : 'border-zinc-200 text-zinc-600 hover:bg-zinc-100'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

/** Type/Date/Size filter chips, adapted from Explorer's own filter row to
 * MediaMind's media-only file set. Only rendered while the CommandBar's
 * Filters toggle is on; applies to files only (see useDirectoryListing's
 * filterEntries for why folders are exempt). */
export function FilterChips(): React.JSX.Element {
  const filterType = useExplorerStore((s) => s.filterType)
  const filterDate = useExplorerStore((s) => s.filterDate)
  const filterSize = useExplorerStore((s) => s.filterSize)
  const setFilterType = useExplorerStore((s) => s.setFilterType)
  const setFilterDate = useExplorerStore((s) => s.setFilterDate)
  const setFilterSize = useExplorerStore((s) => s.setFilterSize)

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-zinc-200 px-3 py-2">
      <ChipGroup options={TYPE_OPTIONS} value={filterType} onChange={setFilterType} />
      <div className="h-4 w-px bg-zinc-200" />
      <ChipGroup options={DATE_OPTIONS} value={filterDate} onChange={setFilterDate} />
      <div className="h-4 w-px bg-zinc-200" />
      <ChipGroup options={SIZE_OPTIONS} value={filterSize} onChange={setFilterSize} />
    </div>
  )
}
