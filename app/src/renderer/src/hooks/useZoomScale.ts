import { useState } from 'react'
import { useCtrlWheelZoom } from './useCtrlWheelZoom'

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

interface Options {
  initial?: number
  min?: number
  max?: number
  /** Same exponential-decay curve MediaViewer's own zoom uses, so every
   * pinch/scroll surface in the app feels equally sensitive. */
  sensitivity?: number
}

/**
 * Continuous Ctrl+scroll / pinch zoom for grids that don't have a
 * discrete size tier (unlike Explorer's Icons/Gallery views — see
 * `useIconSizeZoom`). Returns a multiplier callers scale tile size by.
 */
export function useZoomScale(
  ref: React.RefObject<HTMLElement | null>,
  { initial = 1, min = 0.5, max = 2.5, sensitivity = 0.0015 }: Options = {}
): [number, (scale: number) => void] {
  const [scale, setScale] = useState(initial)
  useCtrlWheelZoom(ref, (deltaY) => {
    setScale((s) => clamp(s * Math.exp(-deltaY * sensitivity), min, max))
  })
  return [scale, setScale]
}
