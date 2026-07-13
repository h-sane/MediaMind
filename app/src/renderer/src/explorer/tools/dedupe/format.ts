export function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  if (b < 1024 * 1024 * 1024) return `${(b / (1024 * 1024)).toFixed(1)} MB`
  return `${(b / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

export function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric'
  })
}

/** `file.path` is relative to the scanned folder, forward-slash (see
 * `DuplicateFileOut` on the backend). The subfolder a copy lives in is the
 * one fact that lets a user tell two otherwise-identical tiles apart, so
 * every tile shows it — even when every file in a group shares the same
 * one, per Hussain's explicit ask. */
export function subfolderOf(path: string, rootLabel: string): string {
  const idx = path.lastIndexOf('/')
  return idx === -1 ? rootLabel : path.slice(0, idx)
}
