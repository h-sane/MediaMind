export function formatSize(bytes?: number | null): string {
  if (bytes === undefined || bytes === null) return ''
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i++
  }
  return `${value.toFixed(1)} ${units[i]}`
}

export function formatDate(mtime?: number | null): string {
  if (!mtime) return ''
  return new Date(mtime * 1000).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  })
}

export function formatDuration(seconds?: number | null): string {
  if (seconds === undefined || seconds === null) return ''
  const total = Math.round(seconds)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

/** Explorer's own single-letter attribute shorthand (Read-only/Hidden/System),
 * in that fixed order regardless of which are set. */
export function formatAttributes(
  readOnly?: boolean | null,
  hidden?: boolean | null,
  system?: boolean | null
): string {
  let s = ''
  if (readOnly) s += 'R'
  if (hidden) s += 'H'
  if (system) s += 'S'
  return s
}
