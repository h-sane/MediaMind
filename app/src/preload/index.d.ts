import type { BackendInfo } from '../shared/types'

interface MediaMindBridge {
  getBackendInfo: () => Promise<BackendInfo | null>
  onBackendReady: (cb: (info: BackendInfo) => void) => void
  pickFolder: () => Promise<string | null>
}

declare global {
  interface Window {
    mediamind: MediaMindBridge
  }
}

export {}
