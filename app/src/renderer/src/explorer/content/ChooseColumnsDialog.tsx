import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { COLUMN_LABELS, useDetailsColumnsStore, type DetailsColumnId } from '../../stores/detailsColumns'

interface Props {
  open: boolean
  onClose: () => void
}

/**
 * Explorer's "Choose Details" dialog: every available column in one list,
 * each with a Show/Hide checkbox and Move Up/Move Down reordering — a more
 * discoverable, keyboard-friendly alternative to the header's drag-to-
 * reorder, reached via the column chooser dropdown's "More…" item.
 */
export function ChooseColumnsDialog({ open, onClose }: Props): React.JSX.Element | null {
  const order = useDetailsColumnsStore((s) => s.order)
  const hidden = useDetailsColumnsStore((s) => s.hidden)
  const toggleHidden = useDetailsColumnsStore((s) => s.toggleHidden)
  const reorder = useDetailsColumnsStore((s) => s.reorder)
  const [selected, setSelected] = useState<DetailsColumnId | null>(null)

  if (!open) return null

  const selectedIdx = selected ? order.indexOf(selected) : -1

  function moveUp(): void {
    if (selectedIdx <= 0) return
    const before = order[selectedIdx - 1]
    reorder(selected as DetailsColumnId, before)
  }

  function moveDown(): void {
    if (selectedIdx === -1 || selectedIdx >= order.length - 1) return
    const after = order[selectedIdx + 2] ?? null
    reorder(selected as DetailsColumnId, after)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div
        className="w-80 rounded-lg bg-white p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <h2 className="text-sm font-semibold text-zinc-900">Choose details</h2>
        <div className="mt-3 max-h-64 overflow-y-auto rounded-md border border-zinc-200">
          {order.map((id) => (
            <label
              key={id}
              onClick={() => setSelected(id)}
              className={`flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm ${
                selected === id ? 'bg-blue-50' : 'hover:bg-zinc-50'
              }`}
            >
              <input
                type="checkbox"
                checked={!hidden.includes(id)}
                onChange={() => toggleHidden(id)}
                onClick={(e) => e.stopPropagation()}
                className="h-3.5 w-3.5"
              />
              <span className="text-zinc-700">{COLUMN_LABELS[id]}</span>
            </label>
          ))}
        </div>
        <div className="mt-2 flex justify-end gap-1">
          <button
            type="button"
            onClick={moveUp}
            disabled={selectedIdx <= 0}
            title="Move up"
            className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100 disabled:pointer-events-none disabled:text-zinc-300"
          >
            <ChevronUp className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={moveDown}
            disabled={selectedIdx === -1 || selectedIdx >= order.length - 1}
            title="Move down"
            className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100 disabled:pointer-events-none disabled:text-zinc-300"
          >
            <ChevronDown className="h-4 w-4" />
          </button>
        </div>
        <div className="mt-4 flex justify-end">
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
