import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type DetailsColumnId = 'date' | 'type' | 'size' | 'created' | 'accessed' | 'attributes'

export const COLUMN_LABELS: Record<DetailsColumnId, string> = {
  date: 'Date modified',
  type: 'Type',
  size: 'Size',
  created: 'Date created',
  accessed: 'Date accessed',
  attributes: 'Attributes'
}

const ALL_COLUMNS: DetailsColumnId[] = ['date', 'type', 'size', 'created', 'accessed', 'attributes']
const DEFAULT_WIDTHS: Record<'name' | DetailsColumnId, number> = {
  name: 280,
  date: 160,
  type: 112,
  size: 96,
  created: 160,
  accessed: 160,
  attributes: 90
}
const MIN_WIDTH = 60

interface DetailsColumnsState {
  /** Order of the non-Name columns; Name is always first and fixed. */
  order: DetailsColumnId[]
  hidden: DetailsColumnId[]
  widths: Record<'name' | DetailsColumnId, number>
  reorder: (id: DetailsColumnId, beforeId: DetailsColumnId | null) => void
  toggleHidden: (id: DetailsColumnId) => void
  setWidth: (id: 'name' | DetailsColumnId, width: number) => void
}

/** Global, not per-folder — Explorer's own column layout is a view
 * template a user sets once, not something they expect to reconfigure per
 * folder (unlike view mode/sort, which Phase C already scoped per-folder). */
export const useDetailsColumnsStore = create<DetailsColumnsState>()(
  persist(
    (set) => ({
      order: ALL_COLUMNS,
      // Matches Explorer's own default column set (Name/Date modified/Type/
      // Size) — Date created, Date accessed and Attributes exist but are
      // opt-in via the column chooser, not shown out of the box.
      hidden: ['created', 'accessed', 'attributes'],
      widths: DEFAULT_WIDTHS,

      reorder: (id, beforeId) =>
        set((s) => {
          const rest = s.order.filter((c) => c !== id)
          if (beforeId === null) return { order: [...rest, id] }
          const idx = rest.indexOf(beforeId)
          if (idx === -1) return { order: [...rest, id] }
          return { order: [...rest.slice(0, idx), id, ...rest.slice(idx)] }
        }),

      toggleHidden: (id) =>
        set((s) => ({
          hidden: s.hidden.includes(id) ? s.hidden.filter((h) => h !== id) : [...s.hidden, id]
        })),

      setWidth: (id, width) => set((s) => ({ widths: { ...s.widths, [id]: Math.max(MIN_WIDTH, width) } }))
    }),
    {
      name: 'mediamind-details-columns',
      version: 2,
      // v1 predates Date created/Date accessed/Attributes — an existing user's persisted
      // `order`/`hidden` won't mention them at all, so without this they'd
      // be un-toggleable (ColumnChooser lists them, but DetailsView only
      // renders columns present in `order`). Bolt any missing columns onto
      // the end, hidden by default, same posture as a first-time install.
      migrate: (persisted) => {
        const state = persisted as DetailsColumnsState
        const missing = ALL_COLUMNS.filter((c) => !state.order.includes(c))
        if (missing.length === 0) return state
        return {
          ...state,
          order: [...state.order, ...missing],
          hidden: [...state.hidden, ...missing],
          widths: { ...DEFAULT_WIDTHS, ...state.widths }
        }
      }
    }
  )
)
