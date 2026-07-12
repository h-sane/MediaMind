/** Types shared between the main, preload, and renderer processes. */

export interface BackendInfo {
  port: number
  token: string
}

/** Result of a `shell.openPath()` hand-off: `null` on success, an OS error
 * string (e.g. "No application is associated...") on failure. */
export type ShellOpenResult = string | null
