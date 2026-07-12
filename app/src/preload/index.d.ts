import type { BackendInfo, ShellOpenResult } from '../shared/types'

interface MediaMindBridge {
  getBackendInfo: () => Promise<BackendInfo | null>
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
}

declare global {
  interface Window {
    mediamind: MediaMindBridge
  }
}

export {}
