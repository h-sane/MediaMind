import { useCallback, useEffect, useRef, useState } from 'react'
import { useSelectionStore } from '../../stores/selection'
import { useFileOps } from '../useFileOps'
import { makeDraggable, makeFolderDropTarget } from './entryDrag'
import type { DirEntry } from '../content/useDirectoryListing'

/**
 * Drag-and-drop for one content-pane entry. Every real filesystem entry
 * (not a drive) is draggable; only folders are drop targets. Dragging a
 * member of the current multi-selection carries the whole selection, not
 * just the one tile the gesture started on — matching Explorer.
 */
export function useEntryDnd(
  entry: DirEntry,
  orderedPaths: string[]
): { ref: (node: HTMLElement | null) => void; isDragging: boolean; isOver: boolean } {
  const elRef = useRef<HTMLElement | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isOver, setIsOver] = useState(false)
  const selected = useSelectionStore((s) => s.selected)
  const { moveTo, copyTo } = useFileOps()

  useEffect(() => {
    const el = elRef.current
    if (!el || entry.type === 'drive') return
    return makeDraggable(
      el,
      () => {
        const paths = selected.has(entry.path) ? orderedPaths.filter((p) => selected.has(p)) : [entry.path]
        const singleFolderPath = paths.length === 1 && entry.type === 'folder' ? entry.path : null
        return { paths, singleFolderPath }
      },
      setIsDragging
    )
  }, [entry.path, entry.type, selected, orderedPaths])

  useEffect(() => {
    const el = elRef.current
    if (!el || entry.type !== 'folder') return
    return makeFolderDropTarget(el, entry.path, {
      onDropInternal: (paths, copy) => (copy ? copyTo(paths, entry.path) : moveTo(paths, entry.path)),
      onDropExternal: (paths) => copyTo(paths, entry.path),
      onHoverChange: setIsOver
    })
  }, [entry.path, entry.type, moveTo, copyTo])

  const ref = useCallback((node: HTMLElement | null) => {
    elRef.current = node
  }, [])

  return { ref, isDragging, isOver }
}
