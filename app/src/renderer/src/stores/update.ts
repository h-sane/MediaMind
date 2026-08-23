import { create } from 'zustand'

// Shared auto-update state, driven by the main process (see main/updater.ts).
// Two surfaces read it: the top-right UpdateBubble (dismissable) and the
// persistent sidebar button (stays until the update is applied). The user
// drives every step — nothing downloads or installs on its own.

type Phase = 'available' | 'downloading' | 'downloaded' | 'error'

interface UpdateStore {
  phase: Phase | null
  version: string
  percent: number
  error: string
  /** Bubble-only: dismissing hides the corner card but keeps the sidebar entry. */
  bubbleDismissed: boolean
  dismissBubble: () => void
  download: () => void
  install: () => void
}

export const useUpdateStore = create<UpdateStore>((set, get) => ({
  phase: null,
  version: '',
  percent: 0,
  error: '',
  bubbleDismissed: false,
  dismissBubble: () => set({ bubbleDismissed: true }),
  download: () => {
    if (get().phase !== 'available') return
    set({ phase: 'downloading', percent: 0, bubbleDismissed: false })
    void window.mediamind.downloadUpdate()
  },
  install: () => void window.mediamind.installUpdate()
}))

// Wire the main-process events once at module load. Preload is ready before the
// renderer bundle runs, so window.mediamind exists here.
window.mediamind.onUpdateAvailable((info) =>
  useUpdateStore.setState({ phase: 'available', version: info.version, bubbleDismissed: false })
)
window.mediamind.onUpdateProgress((info) => useUpdateStore.setState({ percent: info.percent }))
window.mediamind.onUpdateDownloaded((info) =>
  useUpdateStore.setState({ phase: 'downloaded', version: info.version, bubbleDismissed: false })
)
window.mediamind.onUpdateError((info) =>
  // Only surface an error if a download was in flight; a failed background
  // check shouldn't nag with a red card.
  useUpdateStore.setState((s) =>
    s.phase === 'downloading' ? { phase: 'error', error: info.message } : {}
  )
)
