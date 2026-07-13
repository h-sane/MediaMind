import { useRef } from 'react'

interface Props {
  orientation: 'vertical' | 'horizontal'
  /** Reads the pane's current committed size fresh at drag-start, so the
   * drag always resumes from the true current value instead of a
   * potentially-stale closed-over one. */
  getValue: () => number
  setValue: (next: number) => void
  min: number
  max: number
  /** True when the natural drag direction runs opposite the axis (e.g. a
   * handle on a pane's left edge, where dragging left — negative delta —
   * should *grow* the pane to its right). */
  invert?: boolean
}

/**
 * A thin drag-to-resize handle between two panes (nav pane / content /
 * preview pane, and the nav pane's own tree/Tools-rail split) — the feature
 * every pane in a real Explorer window has and this app's didn't. Renders as
 * a zero-net-width strip (negative margin balances its own width) so it
 * doesn't add layout space, but paints and hit-tests over an 8px band
 * straddling the boundary for an easy grab target.
 */
export function PaneResizer({ orientation, getValue, setValue, min, max, invert }: Props): React.JSX.Element {
  const dragRef = useRef<{ startPos: number; startValue: number } | null>(null)

  function pos(e: React.PointerEvent<HTMLDivElement>): number {
    return orientation === 'vertical' ? e.clientX : e.clientY
  }

  function handlePointerDown(e: React.PointerEvent<HTMLDivElement>): void {
    e.preventDefault()
    dragRef.current = { startPos: pos(e), startValue: getValue() }
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  function handlePointerMove(e: React.PointerEvent<HTMLDivElement>): void {
    const drag = dragRef.current
    if (!drag) return
    const rawDelta = pos(e) - drag.startPos
    const signedDelta = invert ? -rawDelta : rawDelta
    setValue(Math.min(max, Math.max(min, drag.startValue + signedDelta)))
  }

  function handlePointerUp(e: React.PointerEvent<HTMLDivElement>): void {
    dragRef.current = null
    e.currentTarget.releasePointerCapture(e.pointerId)
  }

  return (
    <div
      role="separator"
      aria-orientation={orientation}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      className={
        orientation === 'vertical'
          ? '-mx-1 z-10 w-2 shrink-0 cursor-col-resize bg-transparent hover:bg-blue-400/50 active:bg-blue-500/60'
          : '-my-1 z-10 h-2 shrink-0 cursor-row-resize bg-transparent hover:bg-blue-400/50 active:bg-blue-500/60'
      }
    />
  )
}
