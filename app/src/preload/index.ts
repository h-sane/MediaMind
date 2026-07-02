import { contextBridge, ipcRenderer } from 'electron'
import type { BackendInfo } from '../shared/types'

const api = {
  /** Engine connection details; null until the backend is up. */
  getBackendInfo: (): Promise<BackendInfo | null> => ipcRenderer.invoke('backend:info'),
  /** Resolves when the main process reports the engine is ready. */
  onBackendReady: (cb: (info: BackendInfo) => void): void => {
    ipcRenderer.on('backend:ready', (_event, info: BackendInfo) => cb(info))
  },
  /** Native directory picker; null if the user cancels. */
  pickFolder: (): Promise<string | null> => ipcRenderer.invoke('dialog:pick-folder')
}

export type MediaMindBridge = typeof api

contextBridge.exposeInMainWorld('mediamind', api)
