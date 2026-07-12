import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useExplorerStore } from '../../stores/explorer'
import type { IconSize } from '../../stores/explorer'
import { useSelectionStore } from '../../stores/selection'
import { useDirectoryListing } from '../content/useDirectoryListing'
import { useFileOps } from '../useFileOps'

const ICON_SIZES: IconSize[] = ['extra-large', 'large', 'medium', 'small']

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable
}

interface Options {
  /** Shift+Delete is the one destructive-without-recovery path — the hook
   * requests a confirmation from its caller rather than deleting directly. */
  onRequestPermanentDelete: () => void
}

/** Global Explorer keyboard shortcuts, mounted once in ExplorerShell. Every
 * binding bails out over an editable target (address bar edit mode, the
 * rename input) so Backspace/Delete/Ctrl+A there behave like normal text
 * editing instead of firing a file op or navigation. */
export function useKeyboardShortcuts({ onRequestPermanentDelete }: Options): void {
  const back = useExplorerStore((s) => s.back)
  const forward = useExplorerStore((s) => s.forward)
  const up = useExplorerStore((s) => s.up)
  const searchQuery = useExplorerStore((s) => s.searchQuery)
  const startRecursiveSearch = useExplorerStore((s) => s.startRecursiveSearch)
  const contentColumns = useExplorerStore((s) => s.contentColumns)
  const setIconSize = useExplorerStore((s) => s.setIconSize)
  const activeTabId = useExplorerStore((s) => s.activeTabId)
  const newTab = useExplorerStore((s) => s.newTab)
  const closeTab = useExplorerStore((s) => s.closeTab)
  const cycleTab = useExplorerStore((s) => s.cycleTab)
  const selectAllAction = useSelectionStore((s) => s.selectAll)
  const clearSelection = useSelectionStore((s) => s.clear)
  const focusedPath = useSelectionStore((s) => s.focusedPath)
  const anchorPath = useSelectionStore((s) => s.anchorPath)
  const moveFocus = useSelectionStore((s) => s.moveFocus)
  const typeAhead = useSelectionStore((s) => s.typeAhead)
  const qc = useQueryClient()
  const { entries } = useDirectoryListing()
  const fileOps = useFileOps()

  useEffect(() => {
    function handler(e: KeyboardEvent): void {
      if (isEditableTarget(e.target)) return
      const key = e.key.toLowerCase()

      if (e.altKey && e.key === 'Enter') {
        e.preventDefault()
        fileOps.openPropertiesForSelection()
      } else if (e.altKey && e.key === 'ArrowLeft') {
        e.preventDefault()
        back()
      } else if (e.altKey && e.key === 'ArrowRight') {
        e.preventDefault()
        forward()
      } else if ((e.altKey && e.key === 'ArrowUp') || e.key === 'Backspace') {
        e.preventDefault()
        up()
      } else if (
        !e.altKey &&
        (e.key === 'ArrowUp' || e.key === 'ArrowDown' || e.key === 'ArrowLeft' || e.key === 'ArrowRight')
      ) {
        // Roving keyboard focus: Up/Down jump a full row (using the active
        // view's reported column count — 1 for single-column views, so this
        // degrades to "previous/next entry" there), Left/Right move by one
        // entry. Ctrl/Shift modifiers are forwarded to `moveFocus`, which
        // applies the same focus-only / range-extend semantics as a mouse
        // click's Ctrl/Shift.
        if (entries.length === 0) return
        e.preventDefault()
        const orderedPaths = entries.map((entry) => entry.path)
        const startPath = focusedPath ?? anchorPath
        const startIdx = startPath ? orderedPaths.indexOf(startPath) : -1
        const delta =
          e.key === 'ArrowDown' ? contentColumns : e.key === 'ArrowUp' ? -contentColumns : e.key === 'ArrowRight' ? 1 : -1
        const nextIdx = Math.max(0, Math.min(orderedPaths.length - 1, (startIdx === -1 ? 0 : startIdx) + delta))
        moveFocus(orderedPaths[nextIdx], { ctrl: e.ctrlKey, shift: e.shiftKey }, orderedPaths)
      } else if (e.ctrlKey && e.shiftKey && ['1', '2', '3', '4'].includes(e.key)) {
        e.preventDefault()
        setIconSize(ICON_SIZES[Number(e.key) - 1])
      } else if (e.ctrlKey && !e.shiftKey && key === 't') {
        // New tab, opened at the active tab's current folder (Phase K — matches Explorer's own Ctrl+T).
        e.preventDefault()
        newTab()
      } else if (e.ctrlKey && !e.shiftKey && key === 'w') {
        e.preventDefault()
        closeTab(activeTabId)
      } else if (e.ctrlKey && e.key === 'Tab') {
        // Ctrl+Tab / Ctrl+Shift+Tab cycles tabs forward/backward, wrapping.
        e.preventDefault()
        cycleTab(e.shiftKey ? -1 : 1)
      } else if (e.ctrlKey && key === 'a') {
        e.preventDefault()
        selectAllAction(entries.map((entry) => entry.path))
      } else if (e.key === 'F2') {
        e.preventDefault()
        fileOps.renameSelected()
      } else if (e.key === 'Delete' && e.shiftKey) {
        e.preventDefault()
        if (fileOps.canDelete) onRequestPermanentDelete()
      } else if (e.key === 'Delete') {
        e.preventDefault()
        fileOps.deleteSelected(false)
      } else if (e.key === 'F5') {
        e.preventDefault()
        qc.invalidateQueries({ queryKey: ['browse'] })
        qc.invalidateQueries({ queryKey: ['fs-gallery'] })
      } else if (e.ctrlKey && key === 'x') {
        e.preventDefault()
        fileOps.cut()
      } else if (e.ctrlKey && key === 'c') {
        e.preventDefault()
        fileOps.copy()
      } else if (e.ctrlKey && key === 'v') {
        e.preventDefault()
        fileOps.paste()
      } else if (e.ctrlKey && key === 'z') {
        e.preventDefault()
        fileOps.undo()
      } else if (e.ctrlKey && key === 'y') {
        e.preventDefault()
        fileOps.redo()
      } else if (e.ctrlKey && e.shiftKey && key === 'n') {
        e.preventDefault()
        if (fileOps.canNewFolder) fileOps.newFolder()
      } else if (e.ctrlKey && e.shiftKey && key === 'f') {
        // "Search again in subfolders" — escalates whatever is already
        // typed into a recursive backend search (Phase I) without requiring
        // focus to be in the search box (Enter there does the same thing).
        e.preventDefault()
        if (searchQuery.trim()) startRecursiveSearch()
      } else if ((e.ctrlKey && (key === 'f' || key === 'e')) || e.key === 'F3') {
        e.preventDefault()
        document.getElementById('explorer-search-input')?.focus()
      } else if (e.key === 'Escape') {
        clearSelection()
      } else if (!e.ctrlKey && !e.altKey && !e.metaKey && e.key.length === 1 && e.key !== ' ') {
        // Type-ahead-to-select: any other single printable character not
        // already bound above (every modifier-combo shortcut is checked
        // first, so this only ever catches a bare/shifted letter or digit).
        if (entries.length > 0) {
          e.preventDefault()
          typeAhead(
            e.key,
            entries.map((entry) => ({ path: entry.path, name: entry.name }))
          )
        }
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [
    back,
    forward,
    up,
    searchQuery,
    startRecursiveSearch,
    contentColumns,
    setIconSize,
    activeTabId,
    newTab,
    closeTab,
    cycleTab,
    selectAllAction,
    clearSelection,
    focusedPath,
    anchorPath,
    moveFocus,
    typeAhead,
    qc,
    entries,
    fileOps,
    onRequestPermanentDelete
  ])
}
