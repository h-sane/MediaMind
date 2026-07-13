import { create } from 'zustand'

export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'

export interface LogEntry {
  id: number
  ts: number // seconds since epoch, matches Python's record.created
  level: LogLevel
  logger: string
  message: string
}

const MAX_ENTRIES = 500

interface DevLogStore {
  open: boolean
  entries: LogEntry[]
  nextId: number
  toggleOpen: () => void
  push: (entry: Omit<LogEntry, 'id'>) => void
  clear: () => void
}

/** Ring buffer of backend/renderer log lines fed by the WS "log" channel
 * (see api/progress.ts) — backs the dev-only DevLogPanel. Capped at
 * MAX_ENTRIES so a noisy scan can't grow this unbounded. */
export const useDevLogStore = create<DevLogStore>((set) => ({
  open: false,
  entries: [],
  nextId: 1,
  toggleOpen: () => set((s) => ({ open: !s.open })),
  push: (entry) =>
    set((s) => {
      const entries = [...s.entries, { ...entry, id: s.nextId }]
      if (entries.length > MAX_ENTRIES) entries.splice(0, entries.length - MAX_ENTRIES)
      return { entries, nextId: s.nextId + 1 }
    }),
  clear: () => set({ entries: [] })
}))

/** Forwards a renderer-side error to both the persistent main-process log
 * file (existing `window.mediamind.logError`) and the in-app dev console, so
 * the panel shows a complete picture — backend activity over the WS "log"
 * channel (api/progress.ts) plus renderer crashes/failed requests. */
export function logDevError(source: string, message: string): void {
  window.mediamind.logError(source, message)
  useDevLogStore.getState().push({
    ts: Date.now() / 1000,
    level: 'ERROR',
    logger: `renderer.${source}`,
    message
  })
}
