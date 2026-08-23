import { useCallback, useEffect } from 'react'
import { useExplorerStore } from '../../stores/explorer'
import { useSelectionStore } from '../../stores/selection'

/**
 * Thin binding between the selection store and a content view's current row
 * order. `orderedPaths` must be in visual order (top-to-bottom / row-major)
 * so shift-range and Ctrl+A match what the user sees.
 *
 * Deliberately subscribes to no reactive selection slice (`selected` /
 * `focusedPath`) — per-tile state is read inside each tile via `useTileFlags`
 * (Phase 6 / F2), so a selection change no longer forces the whole view to
 * re-render. Only stable store actions are pulled here, and `onItemClick` is
 * memoised so `React.memo`'d tiles keep skipping across parent re-renders.
 */
export function useSelectionModel(orderedPaths: string[]) {
  const click = useSelectionStore((s) => s.click)
  const setSelected = useSelectionStore((s) => s.setSelected)
  const clear = useSelectionStore((s) => s.clear)
  const currentPath = useExplorerStore((s) => s.currentPath)

  // Selection is scoped to the folder being viewed — navigating away always
  // starts fresh, matching Explorer.
  useEffect(() => {
    clear()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPath])

  const onItemClick = useCallback(
    (e: React.MouseEvent, path: string): void => {
      click(path, { ctrl: e.ctrlKey || e.metaKey, shift: e.shiftKey }, orderedPaths)
    },
    [click, orderedPaths]
  )

  return { onItemClick, setSelected, clear }
}
