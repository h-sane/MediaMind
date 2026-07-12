import { Grid2x2, Images, LayoutGrid, LayoutList, List, Rows3 } from 'lucide-react'
import type { GroupKey, SortKey, ViewMode } from '../../stores/explorer'

/** Sort/Group/View option data shared between `CommandBar.tsx` (the
 * command-bar dropdowns) and `context/ContextMenu.tsx` (the same three
 * pickers, nested as submenus on a background right-click, matching real
 * Explorer's own placement in both spots). */
export const SORT_LABELS: Record<SortKey, string> = {
  name: 'Name',
  date: 'Date modified',
  size: 'Size',
  type: 'Type',
  created: 'Date created',
  accessed: 'Date accessed',
  attributes: 'Attributes'
}

/** Group-by is a parallel, independent feature from Sort — same field
 * vocabulary plus "(None)" to turn grouping back off. */
export const GROUP_LABELS: Record<GroupKey, string> = {
  none: '(None)',
  ...SORT_LABELS
}

export const VIEW_OPTIONS: { mode: ViewMode; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { mode: 'icons', label: 'Large icons', icon: Grid2x2 },
  { mode: 'tiles', label: 'Tiles', icon: LayoutGrid },
  { mode: 'list', label: 'List', icon: List },
  { mode: 'details', label: 'Details', icon: Rows3 },
  { mode: 'content', label: 'Content', icon: LayoutList },
  { mode: 'gallery', label: 'Gallery', icon: Images }
]
