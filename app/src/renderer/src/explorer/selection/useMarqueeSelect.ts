import { useRef, useState } from 'react'
import type { MarqueeRect } from './MarqueeLayer'

interface Options {
  /** The scrolled content element (grows with the full listing, scrolls
   * inside the view's outer viewport) — coordinates are measured relative
   * to this element so they track scroll position for free, same as the
   * pre-existing per-view marquee code this replaces. */
  containerRef: React.RefObject<HTMLElement | null>
  onSelect: (paths: string[]) => void
  /** Plain background mousedown (no Ctrl/Cmd) — the caller clears the
   * existing selection, matching click-on-empty-space semantics. */
  onBackgroundMouseDown?: () => void
}

interface MarqueeSelect {
  marqueeRect: MarqueeRect | null
  onMouseDown: (e: React.MouseEvent) => void
  onMouseMove: (e: React.MouseEvent) => void
  onMouseUp: () => void
  onMouseLeave: () => void
}

/**
 * Rubber-band marquee selection shared across every content view (Icon,
 * Tiles, Details). Hit-testing is done against the actual rendered
 * `[data-entry-path]` elements' bounding boxes rather than each view's own
 * row/column arithmetic — the previous per-view formulas (row = index /
 * columns, tileTop = row * CELL_HEIGHT) assumed one uniform grid and broke
 * as soon as Group-by inserts sticky section headers between entries and
 * shifts row offsets. Reading real DOM geometry is correct regardless of
 * grid vs. list layout, column count, or grouping.
 */
export function useMarqueeSelect({ containerRef, onSelect, onBackgroundMouseDown }: Options): MarqueeSelect {
  const [drag, setDrag] = useState<{ startX: number; startY: number; x: number; y: number } | null>(null)
  const draggingRef = useRef(false)

  function contentCoords(clientX: number, clientY: number): { x: number; y: number } {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return { x: 0, y: 0 }
    return { x: clientX - rect.left, y: clientY - rect.top }
  }

  function onMouseDown(e: React.MouseEvent): void {
    if (e.button !== 0) return
    // React bubbles portalled events (Radix context menu items, rendered to
    // document.body) through the *React tree*, not the DOM tree — a click
    // on a menu item reaches this handler even though it's nowhere near
    // this DOM subtree. Bail out for entry tiles/rows and any portalled
    // popper content so a menu selection or an entry click never starts a
    // drag or clears the selection out from under it.
    const target = e.target as HTMLElement
    if (target.closest('[data-entry-path], [data-radix-popper-content-wrapper]')) return
    const { x, y } = contentCoords(e.clientX, e.clientY)
    draggingRef.current = true
    setDrag({ startX: x, startY: y, x, y })
    if (!e.ctrlKey && !e.metaKey) onBackgroundMouseDown?.()
  }

  function onMouseMove(e: React.MouseEvent): void {
    if (!draggingRef.current) return
    const { x, y } = contentCoords(e.clientX, e.clientY)
    setDrag((prev) => (prev ? { ...prev, x, y } : prev))
  }

  function endDrag(): void {
    if (!draggingRef.current || !drag) {
      draggingRef.current = false
      setDrag(null)
      return
    }
    draggingRef.current = false
    const left = Math.min(drag.startX, drag.x)
    const right = Math.max(drag.startX, drag.x)
    const top = Math.min(drag.startY, drag.y)
    const bottom = Math.max(drag.startY, drag.y)
    if (right - left > 3 || bottom - top > 3) {
      const container = containerRef.current
      const containerRect = container?.getBoundingClientRect()
      if (container && containerRect) {
        const hit: string[] = []
        container.querySelectorAll<HTMLElement>('[data-entry-path]').forEach((el) => {
          const r = el.getBoundingClientRect()
          const elLeft = r.left - containerRect.left
          const elTop = r.top - containerRect.top
          const elRight = elLeft + r.width
          const elBottom = elTop + r.height
          if (!(elRight < left || elLeft > right || elBottom < top || elTop > bottom)) {
            const path = el.getAttribute('data-entry-path')
            if (path) hit.push(path)
          }
        })
        onSelect(hit)
      }
    }
    setDrag(null)
  }

  const marqueeRect: MarqueeRect | null = drag
    ? {
        left: Math.min(drag.startX, drag.x),
        top: Math.min(drag.startY, drag.y),
        width: Math.abs(drag.x - drag.startX),
        height: Math.abs(drag.y - drag.startY)
      }
    : null

  return { marqueeRect, onMouseDown, onMouseMove, onMouseUp: endDrag, onMouseLeave: endDrag }
}
