import { useCallback } from 'react'
import {
  useFsCopy,
  useFsCreateShortcut,
  useFsDelete,
  useFsMove,
  useFsNewFolder,
  useFsRedo,
  useFsRename,
  useFsUndo
} from '../api/hooks'
import { useCompress, useExtract } from '../api/useArchive'
import { useClipboardStore } from '../stores/clipboard'
import { isRealFolder, useExplorerStore } from '../stores/explorer'
import { useOpStatusStore } from '../stores/opStatus'
import { usePropertiesDialogStore } from '../stores/propertiesDialog'
import { useSelectionStore } from '../stores/selection'
import { useDirectoryListing } from './content/useDirectoryListing'
import type { ExecutionReport } from '../api/client'

/** Join a folder path with a leaf name using this project's Windows-first
 * separator convention (matches `Breadcrumb.tsx`/`FolderTree.tsx`). */
function joinPath(folder: string, name: string): string {
  const trimmed = folder.replace(/[\\/]+$/, '')
  return `${trimmed}\\${name}`
}

/** Strip the last path segment's extension, e.g. "photo.jpg" -> "photo". */
function stripExtension(name: string): string {
  const idx = name.lastIndexOf('.')
  return idx > 0 ? name.slice(0, idx) : name
}

function baseName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path
}

/**
 * Single orchestration point for every Explorer write action — the command
 * bar, the context menu, and the keyboard shortcuts all call into this
 * instead of duplicating the cut/copy/paste/rename/delete wiring three ways.
 */
export function useFileOps() {
  const currentPath = useExplorerStore((s) => s.currentPath)

  const selected = useSelectionStore((s) => s.selected)
  const clearSelection = useSelectionStore((s) => s.clear)
  const beginRename = useSelectionStore((s) => s.beginRename)

  const clipboardMode = useClipboardStore((s) => s.mode)
  const clipboardPaths = useClipboardStore((s) => s.paths)
  const clipboardSourceFolder = useClipboardStore((s) => s.sourceFolder)
  const setCut = useClipboardStore((s) => s.setCut)
  const setCopy = useClipboardStore((s) => s.setCopy)
  const clearClipboard = useClipboardStore((s) => s.clear)

  const setLastFailure = useOpStatusStore((s) => s.setLastFailure)
  const setLastMessage = useOpStatusStore((s) => s.setLastMessage)
  const openProperties = usePropertiesDialogStore((s) => s.open)

  const { entries } = useDirectoryListing()

  const newFolderMutation = useFsNewFolder()
  const renameMutation = useFsRename()
  const deleteMutation = useFsDelete()
  const moveMutation = useFsMove()
  const copyMutation = useFsCopy()
  const undoMutation = useFsUndo()
  const redoMutation = useFsRedo()
  const compressMutation = useCompress()
  const extractMutation = useExtract()
  const createShortcutMutation = useFsCreateShortcut()

  const selectedPaths = Array.from(selected)

  function reportIfFailed(report: ExecutionReport): void {
    if (!report.ok) setLastFailure(report)
  }

  const newFolder = useCallback(() => {
    if (!isRealFolder(currentPath)) return
    newFolderMutation.mutate({ parent: currentPath })
  }, [currentPath, newFolderMutation])

  const cut = useCallback(() => {
    if (selectedPaths.length === 0 || !isRealFolder(currentPath)) return
    setCut(selectedPaths, currentPath)
    void window.mediamind.clipboardWriteFiles(selectedPaths)
  }, [selectedPaths, currentPath, setCut])

  const copy = useCallback(() => {
    if (selectedPaths.length === 0 || !isRealFolder(currentPath)) return
    setCopy(selectedPaths, currentPath)
    void window.mediamind.clipboardWriteFiles(selectedPaths)
  }, [selectedPaths, currentPath, setCopy])

  const paste = useCallback(() => {
    if (!isRealFolder(currentPath) || clipboardPaths.length === 0 || clipboardSourceFolder === null) return
    if (clipboardMode === 'cut') {
      moveMutation.mutate(
        { sources: clipboardPaths, dest: currentPath, sourceFolder: clipboardSourceFolder },
        { onSuccess: reportIfFailed }
      )
      clearClipboard()
    } else if (clipboardMode === 'copy') {
      copyMutation.mutate({ sources: clipboardPaths, dest: currentPath }, { onSuccess: reportIfFailed })
    }
  }, [currentPath, clipboardMode, clipboardPaths, clipboardSourceFolder, moveMutation, copyMutation, clearClipboard])

  const renameSelected = useCallback(() => {
    if (selectedPaths.length !== 1) return
    beginRename(selectedPaths[0])
  }, [selectedPaths, beginRename])

  const deleteSelected = useCallback(
    (permanent: boolean) => {
      if (selectedPaths.length === 0 || !isRealFolder(currentPath)) return
      deleteMutation.mutate(
        { paths: selectedPaths, permanent, folder: currentPath },
        { onSuccess: reportIfFailed }
      )
      clearSelection()
    },
    [selectedPaths, currentPath, deleteMutation, clearSelection]
  )

  const undo = useCallback(() => {
    undoMutation.mutate(undefined, {
      onSuccess: (result) => {
        if (!result.ok) setLastMessage(result.message)
      }
    })
  }, [undoMutation, setLastMessage])

  const redo = useCallback(() => {
    redoMutation.mutate(undefined, {
      onSuccess: (result) => {
        if (!result.ok) setLastMessage(result.message)
      }
    })
  }, [redoMutation, setLastMessage])

  // Direct move/copy for drag-and-drop — bypasses the clipboard entirely
  // (a drag-and-drop gesture is a single self-contained action, unlike
  // cut/copy which stage a pending choice the user pastes later).
  const moveTo = useCallback(
    (paths: string[], dest: string) => {
      if (paths.length === 0 || !isRealFolder(currentPath)) return
      moveMutation.mutate({ sources: paths, dest, sourceFolder: currentPath }, { onSuccess: reportIfFailed })
    },
    [currentPath, moveMutation]
  )

  const copyTo = useCallback(
    (paths: string[], dest: string) => {
      if (paths.length === 0) return
      copyMutation.mutate({ sources: paths, dest }, { onSuccess: reportIfFailed })
    },
    [copyMutation]
  )

  // Compress selected items into a new zip beside them (dry_run left to a
  // future caller — this action layer performs the real op directly, same
  // as move/copy/delete above; Phase L wires the UI trigger for it).
  const compressSelected = useCallback(() => {
    if (selectedPaths.length === 0 || !isRealFolder(currentPath)) return
    const archiveName =
      selectedPaths.length === 1 ? stripExtension(baseName(selectedPaths[0])) : baseName(currentPath)
    const dest = joinPath(currentPath, `${archiveName}.zip`)
    compressMutation.mutate(
      { paths: selectedPaths, dest, folder: currentPath },
      { onSuccess: reportIfFailed }
    )
  }, [selectedPaths, currentPath, compressMutation])

  // Extract the single selected zip into a new same-named subfolder,
  // mirroring Explorer's "Extract All..." default target.
  const extractSelected = useCallback(() => {
    if (selectedPaths.length !== 1 || !isRealFolder(currentPath)) return
    const zipPath = selectedPaths[0]
    const dest = joinPath(currentPath, stripExtension(baseName(zipPath)))
    extractMutation.mutate({ zipPath, dest, folder: currentPath }, { onSuccess: reportIfFailed })
  }, [selectedPaths, currentPath, extractMutation])

  // Create-shortcut ("Create shortcut" and "Send to > Desktop"): one .lnk
  // per selected item, either beside its source or in the real OS Desktop
  // folder (resolved via the main process — only it knows that path).
  const createShortcut = useCallback(
    async (where: 'here' | 'desktop') => {
      if (selectedPaths.length === 0 || !isRealFolder(currentPath)) return
      const destFolder = where === 'desktop' ? await window.mediamind.getDesktopPath() : currentPath
      for (const target of selectedPaths) {
        createShortcutMutation.mutate(
          { target, destFolder },
          { onError: (err) => setLastMessage(err instanceof Error ? err.message : String(err)) }
        )
      }
    },
    [selectedPaths, currentPath, createShortcutMutation, setLastMessage]
  )

  // OS-shell hand-offs (Phase F's bridge) — none of these touch anything
  // MediaMind manages, so they're plain IPC calls, not mutations.
  const revealSelected = useCallback(() => {
    if (selectedPaths.length === 0) return
    void window.mediamind.shellReveal(selectedPaths[0]).then((ok) => {
      if (!ok) setLastMessage('Could not reveal this item — it may no longer exist.')
    })
  }, [selectedPaths, setLastMessage])

  const openWithSelected = useCallback(() => {
    if (selectedPaths.length === 0) return
    void window.mediamind.shellOpenWith(selectedPaths[0]).then((ok) => {
      if (!ok) setLastMessage('"Open with" is only available on Windows.')
    })
  }, [selectedPaths, setLastMessage])

  const copyPathSelected = useCallback(() => {
    if (selectedPaths.length === 0) return
    void window.mediamind.clipboardCopyPath(selectedPaths)
  }, [selectedPaths])

  const selectedEntries = entries.filter((e) => selected.has(e.path))

  const openPropertiesForSelection = useCallback(() => {
    const targets = selectedEntries.filter((e) => e.type !== 'drive')
    if (targets.length > 0) openProperties(targets)
  }, [selectedEntries, openProperties])

  function isCut(path: string): boolean {
    return clipboardMode === 'cut' && clipboardPaths.includes(path)
  }

  const canExtract =
    selectedPaths.length === 1 && selectedPaths[0].toLowerCase().endsWith('.zip')
  const canOpenWith = selectedEntries.length === 1 && selectedEntries[0].type === 'file'
  const canCreateShortcut = selectedPaths.length > 0 && selectedEntries.every((e) => e.type !== 'drive')

  return {
    currentPath,
    selectedPaths,
    canNewFolder: isRealFolder(currentPath),
    canCutCopy: selectedPaths.length > 0,
    canPaste: isRealFolder(currentPath) && clipboardPaths.length > 0,
    canRename: selectedPaths.length === 1,
    canDelete: selectedPaths.length > 0,
    canCompress: selectedPaths.length > 0,
    canExtract,
    canOpenWith,
    canReveal: selectedPaths.length === 1,
    canCopyPath: selectedPaths.length > 0,
    canCreateShortcut,
    canProperties: selectedEntries.filter((e) => e.type !== 'drive').length > 0,
    clipboardMode,
    isCut,
    newFolder,
    cut,
    copy,
    paste,
    renameSelected,
    deleteSelected,
    moveTo,
    copyTo,
    compressSelected,
    extractSelected,
    createShortcut,
    revealSelected,
    openWithSelected,
    copyPathSelected,
    openPropertiesForSelection,
    undo,
    redo
  }
}
