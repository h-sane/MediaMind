import { useEffect } from 'react'
import { useExplorerStore } from '../../stores/explorer'
import { useSelectionStore } from '../../stores/selection'

/**
 * Thin binding between the selection store and a content view's current row
 * order. `orderedPaths` must be in visual order (top-to-bottom / row-major)
 * so shift-range and Ctrl+A match what the user sees.
 */
export function useSelectionModel(orderedPaths: string[]) {
  const selected = useSelectionStore((s) => s.selected)
  const click = useSelectionStore((s) => s.click)
  const setSelected = useSelectionStore((s) => s.setSelected)
  const selectAllAction = useSelectionStore((s) => s.selectAll)
  const clear = useSelectionStore((s) => s.clear)
  const focusedPath = useSelectionStore((s) => s.focusedPath)
  const currentPath = useExplorerStore((s) => s.currentPath)

  // Selection is scoped to the folder being viewed — navigating away always
  // starts fresh, matching Explorer.
  useEffect(() => {
    clear()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPath])

  function onItemClick(e: React.MouseEvent, path: string): void {
    click(path, { ctrl: e.ctrlKey || e.metaKey, shift: e.shiftKey }, orderedPaths)
  }

  function isSelected(path: string): boolean {
    return selected.has(path)
  }

  function isFocused(path: string): boolean {
    return focusedPath === path
  }

  return {
    selected,
    onItemClick,
    setSelected,
    selectAll: () => selectAllAction(orderedPaths),
    clear,
    isSelected,
    isFocused
  }
}
