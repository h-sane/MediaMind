import { useRef } from 'react'
import { useCtrlWheelZoom } from '../../hooks/useCtrlWheelZoom'
import { useExplorerStore } from '../../stores/explorer'
import type { IconSize } from '../../stores/explorer'

const SIZES: IconSize[] = ['small', 'medium', 'large', 'extra-large']

/** How much accumulated wheel delta counts as one icon-size step — high
 * enough that a single trackpad pinch notch or mouse-wheel click doesn't
 * jump more than one tier at a time. */
const STEP_THRESHOLD = 120

/**
 * Ctrl+scroll / trackpad-pinch zoom for Explorer's Icons and Gallery views —
 * cycles the same four-tier `IconSize` the View menu's "Ctrl+Shift+1-4"
 * shortcuts already use, so this is just another way to reach it.
 */
export function useIconSizeZoom(containerRef: React.RefObject<HTMLElement | null>): void {
  const iconSize = useExplorerStore((s) => s.iconSize)
  const setIconSize = useExplorerStore((s) => s.setIconSize)
  const iconSizeRef = useRef(iconSize)
  iconSizeRef.current = iconSize
  const accumRef = useRef(0)

  useCtrlWheelZoom(containerRef, (deltaY) => {
    accumRef.current += deltaY
    while (Math.abs(accumRef.current) >= STEP_THRESHOLD) {
      const dir = accumRef.current < 0 ? 1 : -1
      accumRef.current += dir > 0 ? STEP_THRESHOLD : -STEP_THRESHOLD
      const idx = SIZES.indexOf(iconSizeRef.current)
      const next = SIZES[clampIndex(idx + dir)]
      if (next !== iconSizeRef.current) {
        iconSizeRef.current = next
        setIconSize(next)
      }
    }
  })
}

function clampIndex(i: number): number {
  return Math.min(SIZES.length - 1, Math.max(0, i))
}
