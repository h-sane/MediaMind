/**
 * One-line kill switch for the in-app dev log console (see stores/devLog.ts,
 * components/DevLogPanel.tsx). Flip to `false` to remove the toggle button
 * and panel from the app entirely — no code path touches the DOM when this
 * is off. Also auto-disabled in any packaged build regardless of this flag
 * (see App.tsx), so this only needs flipping for local dev.
 */
export const DEV_LOG_PANEL_ENABLED = true
