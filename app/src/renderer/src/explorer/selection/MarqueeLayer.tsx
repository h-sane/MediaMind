export interface MarqueeRect {
  left: number
  top: number
  width: number
  height: number
}

/** Purely presentational: draws the rubber-band rectangle at the given
 * content-space coordinates. Each virtualized view owns its own drag state
 * and geometry-based hit test (row/column math differs per view) and just
 * renders this as a child of its scrolled content so the rect tracks scroll
 * position for free. */
export function MarqueeLayer({ rect }: { rect: MarqueeRect | null }): React.JSX.Element | null {
  if (!rect) return null
  return (
    <div
      className="pointer-events-none absolute z-10 border border-blue-400 bg-blue-400/10"
      style={{ left: rect.left, top: rect.top, width: rect.width, height: rect.height }}
    />
  )
}
