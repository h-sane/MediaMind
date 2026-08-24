/** Types shared between the main, preload, and renderer processes. */

export interface BackendInfo {
  port: number
  token: string
}

/** Result of a `shell.openPath()` hand-off: `null` on success, an OS error
 * string (e.g. "No application is associated...") on failure. */
export type ShellOpenResult = string | null

/** One deletable piece of MediaMind's stored data — either a library's own
 * `.mediamind/` folder (which travels on the user's own drive) or the central
 * app-data store. `reachable` is false when a library's drive isn't currently
 * connected (e.g. an unmounted Cryptomator vault), so it can't be deleted now. */
export interface DataLocation {
  kind: 'library' | 'central'
  /** Display label (library name, or "App data"). */
  label: string
  /** The folder that would be deleted. */
  path: string
  /** Whether the drive holding it is currently connected. */
  reachable: boolean
}

/** Outcome of a purge attempt. `done: false` with a non-empty `unreachable`
 * means the caller must decide: connect those drives and retry, or skip them
 * and call again with `skipUnreachable: true`. */
export interface PurgeResult {
  done: boolean
  deleted: string[]
  failed: { path: string; error: string }[]
  unreachable: string[]
}
