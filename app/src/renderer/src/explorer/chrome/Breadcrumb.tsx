import { useState } from 'react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { ChevronDown, Folder, HardDrive, Home, Laptop } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import { useDrives } from '../../api/hooks'
import { HOME_PATH, useExplorerStore } from '../../stores/explorer'

interface Segment {
  label: string
  path: string | null
}

function buildSegments(
  path: string | null,
  driveLabel: (drivePath: string) => string | undefined
): Segment[] {
  // Home is its own root, parallel to (not nested under) "This PC" — a
  // single segment, same as real Explorer's own Home breadcrumb.
  if (path === HOME_PATH) return [{ label: 'Home', path: HOME_PATH }]
  const segments: Segment[] = [{ label: 'This PC', path: null }]
  if (!path) return segments

  const normalized = path.replace(/\//g, '\\')
  const driveMatch = normalized.match(/^([A-Za-z]:)\\?/)
  if (!driveMatch) {
    segments.push({ label: normalized, path: normalized })
    return segments
  }

  const drivePath = driveMatch[1] + '\\'
  segments.push({ label: driveLabel(drivePath) ?? driveMatch[1], path: drivePath })

  const rest = normalized.slice(driveMatch[0].length)
  if (!rest) return segments

  let acc = drivePath
  for (const part of rest.split('\\').filter(Boolean)) {
    acc = acc.endsWith('\\') ? acc + part : acc + '\\' + part
    segments.push({ label: part, path: acc })
  }
  return segments
}

/** Lazily-loaded dropdown of a breadcrumb segment's children, so you can
 * jump sideways into a subfolder without navigating through it first. */
function SegmentMenu({ path }: { path: string | null }): React.JSX.Element {
  const [open, setOpen] = useState(false)
  const navigate = useExplorerStore((s) => s.navigate)

  const drivesQuery = useDrives()
  const dirQuery = useQuery({
    queryKey: ['browse', path],
    queryFn: () => api.fs.list(path as string),
    enabled: open && path !== null
  })

  const entries: { label: string; path: string; icon: 'drive' | 'folder' }[] =
    path === null
      ? (drivesQuery.data ?? []).map((d) => ({ label: d.label, path: d.path, icon: 'drive' }))
      : (dirQuery.data?.folders ?? []).map((f) => ({ label: f.name, path: f.path, icon: 'folder' }))

  return (
    <DropdownMenu.Root open={open} onOpenChange={setOpen}>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className="flex h-6 w-5 shrink-0 items-center justify-center rounded text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600"
          aria-label="Show subfolders"
        >
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="start"
          sideOffset={4}
          className="z-50 max-h-72 w-56 overflow-y-auto rounded-lg border border-zinc-200 bg-white py-1 text-sm shadow-lg"
        >
          {entries.length === 0 ? (
            <div className="px-3 py-2 text-xs text-zinc-400">No subfolders</div>
          ) : (
            entries.map((e) => (
              <DropdownMenu.Item
                key={e.path}
                onSelect={() => navigate(e.path)}
                className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-zinc-700 outline-none hover:bg-zinc-100"
              >
                {e.icon === 'drive' ? (
                  <HardDrive className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
                ) : (
                  <Folder className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
                )}
                <span className="truncate">{e.label}</span>
              </DropdownMenu.Item>
            ))
          )}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}

export function Breadcrumb(): React.JSX.Element {
  const currentPath = useExplorerStore((s) => s.currentPath)
  const navigate = useExplorerStore((s) => s.navigate)
  const { data: drives } = useDrives()

  const driveLabel = (drivePath: string): string | undefined =>
    drives?.find((d) => d.path === drivePath)?.label

  const segments = buildSegments(currentPath, driveLabel)

  return (
    <div className="flex min-w-0 shrink items-center gap-0.5">
      {segments.map((seg, i) => {
        const isLast = i === segments.length - 1
        return (
          <span key={seg.path ?? 'this-pc'} className="flex min-w-0 items-center">
            <button
              type="button"
              onClick={() => navigate(seg.path)}
              className={`flex items-center gap-1.5 truncate rounded px-1.5 py-0.5 text-sm ${
                isLast ? 'font-medium text-zinc-900' : 'text-zinc-600 hover:bg-zinc-100'
              }`}
            >
              {seg.path === null && <Laptop className="h-3.5 w-3.5 shrink-0 text-zinc-400" />}
              {seg.path === HOME_PATH && <Home className="h-3.5 w-3.5 shrink-0 text-zinc-400" />}
              <span className="truncate">{seg.label}</span>
            </button>
            {!isLast && <SegmentMenu path={seg.path} />}
          </span>
        )
      })}
    </div>
  )
}
