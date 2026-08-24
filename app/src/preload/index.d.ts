import type { BackendInfo, DataLocation, PurgeResult, ShellOpenResult } from '../shared/types'

interface MediaMindBridge {
  getBackendInfo: () => Promise<BackendInfo | null>
  isPackaged: () => Promise<boolean>
  onBackendReady: (cb: (info: BackendInfo) => void) => void
  pickFolder: () => Promise<string | null>
  logError: (source: string, message: string) => void
  getPathForFile: (file: File) => string
  shellReveal: (path: string) => Promise<boolean>
  shellOpenPath: (path: string) => Promise<ShellOpenResult>
  shellOpenWith: (path: string) => Promise<boolean>
  shellOpenRecycleBin: () => Promise<boolean>
  clipboardCopyPath: (paths: string[]) => Promise<void>
  clipboardWriteFiles: (paths: string[]) => Promise<boolean>
  getDesktopPath: () => Promise<string>
  onUpdateAvailable: (cb: (info: { version: string }) => void) => void
  onUpdateProgress: (cb: (info: { percent: number }) => void) => void
  onUpdateDownloaded: (cb: (info: { version: string }) => void) => void
  onUpdateError: (cb: (info: { message: string }) => void) => void
  downloadUpdate: () => Promise<void>
  installUpdate: () => Promise<void>
  dataLocations: () => Promise<DataLocation[]>
  purgeData: (skipUnreachable: boolean) => Promise<PurgeResult>
  relaunchApp: () => Promise<void>
}

declare global {
  interface Window {
    mediamind: MediaMindBridge
  }
}

export {}
