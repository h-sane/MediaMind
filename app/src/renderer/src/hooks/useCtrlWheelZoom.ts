import { useEffect, useRef } from 'react'

/**
 * Fires `onZoom(deltaY)` for Ctrl+scroll-wheel and trackpad pinch — Chromium
 * reports a trackpad pinch gesture as a `wheel` event with `ctrlKey: true`,
 * so the two gestures share one code path. Suppresses the event so it
 * doesn't also trigger Electron/Chromium's own page zoom.
 *
 * Negative `deltaY` (scroll up / pinch-out, fingers spreading) means zoom
 * in; positive means zoom out — callers should follow that sign convention
 * to match every OS's pinch-zoom direction (see MediaViewer's own wheel
 * handler for the same convention).
 */
export function useCtrlWheelZoom(ref: React.RefObject<HTMLElement | null>, onZoom: (deltaY: number) => void): void {
  const onZoomRef = useRef(onZoom)
  useEffect(() => {
    onZoomRef.current = onZoom
  }, [onZoom])

  useEffect(() => {
    const el = ref.current
    if (!el) return
    function onWheel(e: WheelEvent): void {
      if (!e.ctrlKey) return
      e.preventDefault()
      onZoomRef.current(e.deltaY)
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}
