import { contextBridge, ipcRenderer, webUtils } from 'electron'
import type { BackendInfo, ShellOpenResult } from '../shared/types'

const api = {
  /** Engine connection details; null until the backend is up. */
  getBackendInfo: (): Promise<BackendInfo | null> => ipcRenderer.invoke('backend:info'),
  /** Resolves when the main process reports the engine is ready. */
  onBackendReady: (cb: (info: BackendInfo) => void): void => {
    ipcRenderer.on('backend:ready', (_event, info: BackendInfo) => cb(info))
  },
  /** Native directory picker; null if the user cancels. */
  pickFolder: (): Promise<string | null> => ipcRenderer.invoke('dialog:pick-folder'),
  /** Forward a renderer-side error to the main process's persistent log file. */
  logError: (source: string, message: string): void =>
    ipcRenderer.send('renderer:log-error', { source, message }),
  /** Real filesystem path for a `File` from a native OS drag (e.g. dragging
   * files in from Windows Explorer) — `File.path` was removed from Electron
   * for security in v32+; `webUtils.getPathForFile` is the replacement, and
   * only works from the preload/renderer side, never a synthetic File. */
  getPathForFile: (file: File): string => webUtils.getPathForFile(file),
  /** Reveals a path in the OS file manager, highlighting it. */
  shellReveal: (path: string): Promise<boolean> => ipcRenderer.invoke('shell:reveal', path),
  /** Opens a path with its default associated application. */
  shellOpenPath: (path: string): Promise<ShellOpenResult> => ipcRenderer.invoke('shell:open-path', path),
  /** Opens the native Windows "Open with" application chooser for a path. */
  shellOpenWith: (path: string): Promise<boolean> => ipcRenderer.invoke('shell:open-with', path),
  /** Opens the real OS Recycle Bin window (Windows only). */
  shellOpenRecycleBin: (): Promise<boolean> => ipcRenderer.invoke('shell:open-recycle-bin'),
  /** Copies quoted path(s) to the OS clipboard as plain text. */
  clipboardCopyPath: (paths: string[]): Promise<void> => ipcRenderer.invoke('clipboard:copy-path', paths),
  /** Writes real files to the OS clipboard (Windows `CF_HDROP`) so they can
   * be pasted into Explorer or another native app. */
  clipboardWriteFiles: (paths: string[]): Promise<boolean> =>
    ipcRenderer.invoke('clipboard:write-files', paths),
  /** The real OS Desktop folder path — used by "Send to > Desktop". */
  getDesktopPath: (): Promise<string> => ipcRenderer.invoke('paths:desktop')
}

export type MediaMindBridge = typeof api

contextBridge.exposeInMainWorld('mediamind', api)
