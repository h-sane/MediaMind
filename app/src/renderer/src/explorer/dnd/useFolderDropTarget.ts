import { useCallback, useEffect, useRef, useState } from 'react'
import { useFileOps } from '../useFileOps'
import { makeFolderDropTarget } from './entryDrag'

/**
 * Drop target for a folder that isn't a content-pane tile/row — a
 * FolderTree node or a Quick Access pin. Same move/copy semantics as
 * `useEntryDnd`'s drop side, without the drag side (tree nodes and pins
 * aren't drag sources themselves).
 */
export function useFolderDropTarget(path: string | null): {
  ref: (node: HTMLElement | null) => void
  isOver: boolean
} {
  const elRef = useRef<HTMLElement | null>(null)
  const [isOver, setIsOver] = useState(false)
  const { moveTo, copyTo } = useFileOps()

  useEffect(() => {
    const el = elRef.current
    if (!el || path === null) return
    return makeFolderDropTarget(el, path, {
      onDropInternal: (paths, copy) => (copy ? copyTo(paths, path) : moveTo(paths, path)),
      onDropExternal: (paths) => copyTo(paths, path),
      onHoverChange: setIsOver
    })
  }, [path, moveTo, copyTo])

  const ref = useCallback((node: HTMLElement | null) => {
    elRef.current = node
  }, [])

  return { ref, isOver }
}
