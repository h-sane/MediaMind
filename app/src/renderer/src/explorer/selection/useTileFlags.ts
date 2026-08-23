import { useClipboardStore } from '../../stores/clipboard'
import { useSelectionStore } from '../../stores/selection'

export interface TileFlags {
  isSelected: boolean
  isFocused: boolean
  isRenaming: boolean
  isCut: boolean
}

/**
 * Per-tile view state read straight from the stores, keyed on the tile's own
 * path. Subscribing here (rather than threading recomputed booleans down from
 * the parent) means a selection/focus/rename/cut change re-renders only the
 * tiles whose own flag actually flipped — the rest are `React.memo`'d with
 * otherwise-stable props and skip (EXPLORER_SPEED_V5 Phase 6 / F2).
 */
export function useTileFlags(path: string): TileFlags {
  const isSelected = useSelectionStore((s) => s.selected.has(path))
  const isFocused = useSelectionStore((s) => s.focusedPath === path)
  const isRenaming = useSelectionStore((s) => s.renamingPath === path)
  const isCut = useClipboardStore((s) => s.mode === 'cut' && s.paths.includes(path))
  return { isSelected, isFocused, isRenaming, isCut }
}
