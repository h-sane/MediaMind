import { combine } from '@atlaskit/pragmatic-drag-and-drop/combine'
import { draggable, dropTargetForElements } from '@atlaskit/pragmatic-drag-and-drop/element/adapter'
import { dropTargetForExternal } from '@atlaskit/pragmatic-drag-and-drop/external/adapter'
import { containsFiles, getFiles } from '@atlaskit/pragmatic-drag-and-drop/external/file'

/** Custom data key carried by an internal (in-app) entry drag, distinguishing
 * it from an external OS file drag on the same drop targets. */
const ENTRY_DRAG_TYPE = 'mediamind/entries'

interface EntryDragData {
  [key: string]: unknown
  [ENTRY_DRAG_TYPE]: true
  paths: string[]
  /** Set only when exactly one folder (not a file, not a multi-selection)
   * is being dragged — the one case Quick Access's drag-to-pin accepts. */
  singleFolderPath: string | null
}

function isEntryDragData(data: Record<string, unknown>): data is EntryDragData {
  return data[ENTRY_DRAG_TYPE] === true
}

/** Makes `element` draggable, carrying whatever `getPaths()` returns at drag
 * start (the caller decides: the whole selection, or just this one entry). */
export function makeDraggable(
  element: HTMLElement,
  getPaths: () => { paths: string[]; singleFolderPath: string | null },
  onDragStateChange: (dragging: boolean) => void
): () => void {
  return draggable({
    element,
    getInitialData: () => ({ [ENTRY_DRAG_TYPE]: true, ...getPaths() }),
    onDragStart: () => onDragStateChange(true),
    onDrop: () => onDragStateChange(false)
  })
}

/** Real filesystem paths for OS files dropped in from outside the app
 * (Windows Explorer, desktop, etc.) via the preload's `webUtils` bridge. */
function resolveExternalPaths(source: Parameters<typeof getFiles>[0]['source']): string[] {
  return getFiles({ source })
    .map((f) => window.mediamind.getPathForFile(f))
    .filter((p): p is string => !!p)
}

/** Makes `element` a drag-to-pin target: dropping a single dragged folder
 * pins it to Quick Access instead of moving/copying it. Multi-selection
 * drags and file drags are ignored — Quick Access only pins folders, one
 * at a time, same as its context-menu "Pin to Quick access" action. */
export function makePinDropTarget(
  element: HTMLElement,
  handlers: { onPin: (path: string) => void; onHoverChange: (over: boolean) => void }
): () => void {
  return dropTargetForElements({
    element,
    canDrop: ({ source }) => isEntryDragData(source.data) && source.data.singleFolderPath !== null,
    onDragEnter: () => handlers.onHoverChange(true),
    onDragLeave: () => handlers.onHoverChange(false),
    onDrop: ({ source }) => {
      handlers.onHoverChange(false)
      if (!isEntryDragData(source.data) || source.data.singleFolderPath === null) return
      handlers.onPin(source.data.singleFolderPath)
    }
  })
}

/** Makes `element` a combined drop target for both internal entry drags
 * (move, or copy when Ctrl is held at drop time — matching Explorer's own
 * modifier convention) and external OS file drags (always copy — dropping
 * something in from outside the app should never delete it from wherever it
 * came from). Returns a single cleanup function for both adapters. */
export function makeFolderDropTarget(
  element: HTMLElement,
  destPath: string,
  handlers: {
    onDropInternal: (paths: string[], copy: boolean) => void
    onDropExternal: (paths: string[]) => void
    onHoverChange: (over: boolean) => void
  }
): () => void {
  return combine(
    dropTargetForElements({
      element,
      canDrop: ({ source }) => isEntryDragData(source.data) && !source.data.paths.includes(destPath),
      onDragEnter: () => handlers.onHoverChange(true),
      onDragLeave: () => handlers.onHoverChange(false),
      onDrop: ({ source, location }) => {
        handlers.onHoverChange(false)
        if (!isEntryDragData(source.data)) return
        handlers.onDropInternal(source.data.paths, location.current.input.ctrlKey)
      }
    }),
    dropTargetForExternal({
      element,
      canDrop: containsFiles,
      onDragEnter: () => handlers.onHoverChange(true),
      onDragLeave: () => handlers.onHoverChange(false),
      onDrop: ({ source }) => {
        handlers.onHoverChange(false)
        const paths = resolveExternalPaths(source)
        if (paths.length > 0) handlers.onDropExternal(paths)
      }
    })
  )
}
