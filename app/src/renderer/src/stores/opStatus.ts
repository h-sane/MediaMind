import { create } from 'zustand'
import type { ExecutionReport } from '../api/client'

interface OpStatusStore {
  /** Set only when a move/copy/delete's report.ok is false — the shell
   * stays silent on success (per the safety design: the manifest is the
   * audit trail; the UI only interrupts the user when something failed). */
  lastFailure: ExecutionReport | null
  setLastFailure: (report: ExecutionReport | null) => void
  /** Plain-text feedback for actions that don't produce an ExecutionReport
   * (undo/redo's "Nothing to undo"/"Nothing to redo", shell hand-off
   * failures) — same silent-on-success rule, only shown for a failure. */
  lastMessage: string | null
  setLastMessage: (message: string | null) => void
  clear: () => void
}

export const useOpStatusStore = create<OpStatusStore>((set) => ({
  lastFailure: null,
  lastMessage: null,
  setLastFailure: (report) => set({ lastFailure: report }),
  setLastMessage: (message) => set({ lastMessage: message }),
  clear: () => set({ lastFailure: null, lastMessage: null })
}))
