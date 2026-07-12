import { formatAttributes } from '../format'
import type { GroupKey } from '../../stores/explorer'
import type { DirEntry } from './useDirectoryListing'

export interface EntryGroup {
  key: string
  label: string
  entries: DirEntry[]
}

const DAY_MS = 24 * 60 * 60 * 1000
const KB = 1024
const MB = KB * 1024
const GB = MB * 1024

/** Explorer's own "Date modified" group labels, in chronological order —
 * used both to label a bucket and to rank groups for display (see
 * `groupEntries`), independent of whatever order `entries` arrived in. */
const DATE_BUCKET_ORDER = [
  'Today',
  'Yesterday',
  'Earlier this week',
  'Last week',
  'Earlier this month',
  'Last month',
  'Earlier this year',
  'Last year',
  'A long time ago',
  'Unknown'
]

const SIZE_BUCKET_ORDER = ['Tiny', 'Small', 'Medium', 'Large', 'Huge', 'Gigantic', 'Unknown']

function dateBucketLabel(unixSeconds?: number | null): string {
  if (unixSeconds === undefined || unixSeconds === null) return 'Unknown'
  const now = new Date()
  const date = new Date(unixSeconds * 1000)
  const startOfDay = (d: Date): number => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const diffDays = Math.round((startOfDay(now) - startOfDay(date)) / DAY_MS)

  if (diffDays <= 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return 'Earlier this week'
  if (diffDays < 14) return 'Last week'
  if (date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth()) return 'Earlier this month'
  const lastMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1)
  if (date.getFullYear() === lastMonth.getFullYear() && date.getMonth() === lastMonth.getMonth()) return 'Last month'
  if (date.getFullYear() === now.getFullYear()) return 'Earlier this year'
  if (date.getFullYear() === now.getFullYear() - 1) return 'Last year'
  return 'A long time ago'
}

function sizeBucketLabel(bytes?: number | null): string {
  if (bytes === undefined || bytes === null) return 'Unknown'
  if (bytes < 16 * KB) return 'Tiny'
  if (bytes < 1 * MB) return 'Small'
  if (bytes < 128 * MB) return 'Medium'
  if (bytes < 1 * GB) return 'Large'
  if (bytes < 4 * GB) return 'Huge'
  return 'Gigantic'
}

/** Folders and drives always form their own leading group regardless of
 * `groupBy` — a folder's "size"/"date modified" isn't meaningfully grouped
 * the same way a file's is, and this matches Explorer's own behavior of
 * always listing folders before any file group. */
const FOLDERS_KEY = '__folders__'

function bucketFor(entry: DirEntry, groupBy: GroupKey): { key: string; label: string } {
  if (entry.type !== 'file') {
    const label = entry.type === 'drive' ? 'Drives' : 'Folders'
    return { key: FOLDERS_KEY, label }
  }
  switch (groupBy) {
    case 'type': {
      const label =
        entry.kind === 'image'
          ? 'Images'
          : entry.kind === 'gif'
            ? 'GIFs'
            : entry.kind === 'video'
              ? 'Videos'
              : entry.kind === 'audio'
                ? 'Audio'
                : 'Other'
      return { key: label, label }
    }
    case 'date': {
      const label = dateBucketLabel(entry.mtime)
      return { key: label, label }
    }
    case 'created': {
      const label = dateBucketLabel(entry.created)
      return { key: label, label }
    }
    case 'accessed': {
      const label = dateBucketLabel(entry.accessed)
      return { key: label, label }
    }
    case 'size': {
      const label = sizeBucketLabel(entry.size)
      return { key: label, label }
    }
    case 'attributes': {
      const label = formatAttributes(entry.readOnly, entry.hidden, entry.system) || 'None'
      return { key: label, label }
    }
    case 'name':
    default: {
      const first = entry.name.charAt(0).toUpperCase()
      const label = /[A-Z]/.test(first) ? first : '#'
      return { key: label, label }
    }
  }
}

function rank(label: string, groupBy: GroupKey): number {
  if (groupBy === 'date' || groupBy === 'created' || groupBy === 'accessed') {
    const i = DATE_BUCKET_ORDER.indexOf(label)
    return i === -1 ? DATE_BUCKET_ORDER.length : i
  }
  if (groupBy === 'size') {
    const i = SIZE_BUCKET_ORDER.indexOf(label)
    return i === -1 ? SIZE_BUCKET_ORDER.length : i
  }
  return 0
}

/**
 * Partitions an already-sorted `entries` list (see
 * `useDirectoryListing`/`sortEntries`) into Explorer-style groups with
 * section labels. Group-by is independent of Sort-by: entries keep whatever
 * order the current sort produced within their group, but the *groups*
 * themselves are ordered on a scale that matches the grouped field (e.g.
 * chronologically for date fields), not on the incidental order they were
 * first encountered in — so grouping by date reads top-to-bottom as
 * Today/Yesterday/... regardless of whether the visible sort is by name.
 */
export function groupEntries(entries: DirEntry[], groupBy: GroupKey): EntryGroup[] {
  if (groupBy === 'none') return entries.length > 0 ? [{ key: '__all__', label: '', entries }] : []

  const groups: EntryGroup[] = []
  const byKey = new Map<string, EntryGroup>()
  for (const entry of entries) {
    const { key, label } = bucketFor(entry, groupBy)
    let group = byKey.get(key)
    if (!group) {
      group = { key, label, entries: [] }
      byKey.set(key, group)
      groups.push(group)
    }
    group.entries.push(entry)
  }

  groups.sort((a, b) => {
    if (a.key === FOLDERS_KEY) return -1
    if (b.key === FOLDERS_KEY) return 1
    if (groupBy === 'name' || groupBy === 'type' || groupBy === 'attributes') return a.label.localeCompare(b.label)
    return rank(a.label, groupBy) - rank(b.label, groupBy)
  })
  return groups
}
