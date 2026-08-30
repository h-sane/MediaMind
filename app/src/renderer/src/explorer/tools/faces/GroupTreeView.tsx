import { useMemo, useState } from 'react'
import { ChevronRight, Folder, Home } from 'lucide-react'
import { usePeopleTree } from '../../../api/hooks'
import type { PeopleGroup, Person } from '../../../api/client'
import { PersonCard } from './PersonCard'

interface Props {
  libraryId: string
  zoom: number
  onOpenPerson: (personId: number) => void
}

/** ADR-0007/0008 person-centric grouped browse. Groups mirror folder nesting;
 * a named Person is homed under the folder containing their Primary Location.
 * Deliberately minimal (the polished surface is Block 5): navigate groups,
 * open a person. Media never sits under a Group — drilling to a Person opens
 * their real files via the existing person view. */
export function GroupTreeView({ libraryId, zoom, onOpenPerson }: Props): React.JSX.Element {
  const { data, isLoading } = usePeopleTree(libraryId)
  const [path, setPath] = useState('')
  const [showAllBelow, setShowAllBelow] = useState(false)

  const current = useMemo(() => (data ? findGroup(data.root, path) : null), [data, path])

  // Path "" is root; each crumb is a cumulative posix path.
  const crumbs = path ? path.split('/') : []
  const crumbPaths = crumbs.map((_, i) => crumbs.slice(0, i + 1).join('/'))

  if (isLoading) return <p className="text-sm text-zinc-400">Loading…</p>
  if (!current) return <p className="text-sm text-zinc-400">No people organized into folders yet.</p>

  const persons = showAllBelow ? collectPersons(current) : current.persons

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <nav className="flex flex-wrap items-center gap-1 text-sm text-zinc-500">
          <button onClick={() => setPath('')} className="flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-zinc-100">
            <Home className="h-3.5 w-3.5" />
            People
          </button>
          {crumbs.map((name, i) => (
            <span key={crumbPaths[i]} className="flex items-center gap-1">
              <ChevronRight className="h-3.5 w-3.5 text-zinc-300" />
              <button onClick={() => setPath(crumbPaths[i])} className="rounded px-1.5 py-0.5 hover:bg-zinc-100">
                {name}
              </button>
            </span>
          ))}
        </nav>
        {current.subgroups.length > 0 && (
          <label className="flex cursor-pointer items-center gap-1.5 text-xs text-zinc-500">
            <input
              type="checkbox"
              checked={showAllBelow}
              onChange={(e) => setShowAllBelow(e.target.checked)}
              className="h-3.5 w-3.5"
            />
            Show everyone below ({current.total_persons})
          </label>
        )}
      </div>

      {!showAllBelow && current.subgroups.length > 0 && (
        <div className="mb-4 grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))' }}>
          {current.subgroups.map((g) => (
            <button
              key={g.path}
              onClick={() => setPath(g.path)}
              className="flex items-center gap-2.5 rounded-xl border border-zinc-200 px-3 py-2.5 text-left transition hover:border-zinc-300 hover:bg-zinc-50"
            >
              <Folder className="h-4 w-4 shrink-0 text-zinc-400" />
              <span className="min-w-0 flex-1 truncate text-sm text-zinc-700">{g.name}</span>
              <span className="shrink-0 text-xs text-zinc-400">{g.total_persons}</span>
            </button>
          ))}
        </div>
      )}

      {persons.length > 0 ? (
        <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${Math.round(130 * zoom)}px, 1fr))` }}>
          {persons.map((p: Person) => (
            <PersonCard
              key={p.id}
              person={p}
              libraryId={libraryId}
              selected={false}
              selectMode={false}
              zoom={zoom}
              onToggleSelect={() => {}}
              onOpen={onOpenPerson}
            />
          ))}
        </div>
      ) : (
        current.subgroups.length === 0 && (
          <p className="text-sm text-zinc-400">No named people here yet.</p>
        )
      )}
    </div>
  )
}

function findGroup(node: PeopleGroup, path: string): PeopleGroup | null {
  if (node.path === path) return node
  for (const g of node.subgroups) {
    const hit = findGroup(g, path)
    if (hit) return hit
  }
  return null
}

function collectPersons(node: PeopleGroup): Person[] {
  const out = [...node.persons]
  for (const g of node.subgroups) out.push(...collectPersons(g))
  return out.sort((a, b) => (a.name ?? '').localeCompare(b.name ?? ''))
}
