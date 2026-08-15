import { useEffect, useMemo, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import type { EntryGroup } from './grouping'
import type { DirEntry } from './useDirectoryListing'

export type GroupRow =
  | { kind: 'header'; key: string; label: string; count: number }
  | { kind: 'tiles'; key: string; entries: DirEntry[] }

const HEADER_HEIGHT = 28

/** Flattens grouped sections into a single indexed row list — a header row
 * per non-empty group label, followed by one row per `columns`-wide slice of
 * that group's entries — so a single virtualizer can window headers and
 * tile rows together instead of every view hand-rolling its own grouped
 * layout (see `docs/PERFORMANCE_AND_INGEST_V4_PLAN.md` Phase 5). */
export function flattenGroupsToRows(groups: EntryGroup[], columns: number): GroupRow[] {
  const rows: GroupRow[] = []
  for (const group of groups) {
    if (group.label) {
      rows.push({ kind: 'header', key: `${group.key}:h`, label: group.label, count: group.entries.length })
    }
    for (let i = 0; i < group.entries.length; i += columns) {
      rows.push({ kind: 'tiles', key: `${group.key}:${i}`, entries: group.entries.slice(i, i + columns) })
    }
  }
  return rows
}

interface Props {
  groups: EntryGroup[]
  columns: number
  cellHeight: number
  scrollRef: React.RefObject<HTMLDivElement | null>
  containerRef?: React.RefObject<HTMLDivElement | null>
  focusedPath?: string | null
  renderTile: (entry: DirEntry) => React.ReactNode
}

/** Windows a grouped grid (date/type/size/... section headers + tiles) the
 * same way `IconGridView`'s ungrouped branch windows a flat one
 * (`useVirtualizer` over row indices) — extended to a row list that mixes
 * header rows and tile rows. Sticky headers use the standard
 * virtualized-list trick: only the *active* section's header (the last one
 * at or above the current scroll offset) is rendered `position: sticky`;
 * every other row — including inactive headers — is absolutely positioned
 * at its real offset, so the sticky header is seamlessly replaced the
 * instant the next section's header scrolls up to meet it. */
export function GroupedVirtualGrid({
  groups,
  columns,
  cellHeight,
  scrollRef,
  containerRef,
  focusedPath,
  renderTile
}: Props): React.JSX.Element {
  const rows = useMemo(() => flattenGroupsToRows(groups, columns), [groups, columns])
  const stickyIndexes = useMemo(
    () => rows.reduce<number[]>((acc, row, i) => (row.kind === 'header' ? [...acc, i] : acc), []),
    [rows]
  )
  const activeStickyRef = useRef(0)

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: (i) => (rows[i].kind === 'header' ? HEADER_HEIGHT : cellHeight),
    overscan: 4
  })

  // Arrow-key focus can land on an entry the virtualizer hasn't mounted yet
  // (same problem IconGridView's ungrouped branch solves with scrollToIndex)
  // — find the focused entry's flattened row and scroll it into range.
  useEffect(() => {
    if (!focusedPath) return
    const idx = rows.findIndex((r) => r.kind === 'tiles' && r.entries.some((e) => e.path === focusedPath))
    if (idx !== -1) virtualizer.scrollToIndex(idx, { align: 'auto' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusedPath])

  const virtualItems = virtualizer.getVirtualItems()
  const startIndex = virtualItems[0]?.index ?? 0
  for (const idx of stickyIndexes) {
    if (idx <= startIndex) activeStickyRef.current = idx
    else break
  }
  const activeSticky = activeStickyRef.current
  const renderList = virtualItems.some((v) => v.index === activeSticky)
    ? virtualItems
    : [virtualizer.measurementsCache[activeSticky], ...virtualItems].filter(Boolean)

  return (
    <div
      ref={containerRef}
      style={{ height: virtualizer.getTotalSize(), position: 'relative', width: '100%' }}
    >
      {renderList.map((virtualRow) => {
        const row = rows[virtualRow.index]
        const isActiveSticky = virtualRow.index === activeSticky
        return (
          <div
            key={row.key}
            style={
              isActiveSticky
                ? { position: 'sticky', top: 0, zIndex: 10, width: '100%' }
                : {
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: `${virtualRow.size}px`,
                    transform: `translateY(${virtualRow.start}px)`
                  }
            }
          >
            {row.kind === 'header' ? (
              <div className="bg-white px-1 py-1 text-xs font-semibold text-zinc-500">
                {row.label} <span className="font-normal text-zinc-400">({row.count})</span>
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
                {row.entries.map((entry) => renderTile(entry))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
