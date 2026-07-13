import { create } from 'zustand'
import { persist } from 'zustand/middleware'

const DEFAULT_NAV_PANE_WIDTH = 256 // matches the nav pane's old fixed `w-64`
const DEFAULT_PREVIEW_PANE_WIDTH = 288 // matches the preview pane's old fixed `w-72`
const DEFAULT_TOOL_RAIL_HEIGHT = 88 // ~ToolRail's natural content height (header + 2 rows)

export const NAV_PANE_MIN = 180
export const NAV_PANE_MAX = 480
export const PREVIEW_PANE_MIN = 220
export const PREVIEW_PANE_MAX = 560
export const TOOL_RAIL_MIN = 48
export const TOOL_RAIL_MAX = 400

interface PaneLayoutStore {
  navPaneWidth: number
  previewPaneWidth: number
  toolRailHeight: number
  setNavPaneWidth: (width: number) => void
  setPreviewPaneWidth: (width: number) => void
  setToolRailHeight: (height: number) => void
}

/** Drag-to-resize sizes for the Explorer shell's split panes — the nav
 * pane's width, the preview pane's width, and the nav pane's own internal
 * split between the folder tree and the Tools rail (`ToolRail.tsx`). Global
 * chrome layout (not per-tab state like `stores/explorer.ts`), persisted
 * across restarts the same way real Explorer remembers pane sizes. */
export const usePaneLayoutStore = create<PaneLayoutStore>()(
  persist(
    (set) => ({
      navPaneWidth: DEFAULT_NAV_PANE_WIDTH,
      previewPaneWidth: DEFAULT_PREVIEW_PANE_WIDTH,
      toolRailHeight: DEFAULT_TOOL_RAIL_HEIGHT,
      setNavPaneWidth: (width) => set({ navPaneWidth: Math.min(NAV_PANE_MAX, Math.max(NAV_PANE_MIN, width)) }),
      setPreviewPaneWidth: (width) =>
        set({ previewPaneWidth: Math.min(PREVIEW_PANE_MAX, Math.max(PREVIEW_PANE_MIN, width)) }),
      setToolRailHeight: (height) => set({ toolRailHeight: Math.min(TOOL_RAIL_MAX, Math.max(TOOL_RAIL_MIN, height)) })
    }),
    { name: 'mediamind-pane-layout' }
  )
)
