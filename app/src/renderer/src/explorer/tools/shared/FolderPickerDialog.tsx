import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, Folder, FolderPlus } from 'lucide-react'
import { api } from '../../../api/client'
import { useLibraries } from '../../../api/hooks'

interface Props {
  libraryId: string
  initialRel?: string
  onPick: (destFolderRel: string) => void
  onClose: () => void
}

function toRel(root: string, abs: string): string {
  const normRoot = root.replace(/[\\/]+$/, '').replace(/\\/g, '/')
  const normAbs = abs.replace(/\\/g, '/')
  if (normAbs === normRoot) return ''
  return normAbs.startsWith(normRoot + '/') ? normAbs.slice(normRoot.length + 1) : normAbs
}

/**
 * Folder picker scoped to one library's subtree — browses existing folders
 * via the same `/v1/fs/list` the Explorer nav tree uses, or types a new
 * subfolder name under wherever's currently open. Replaces the free-text
 * "type a relative path" input in MatchReviewModal/MaterializeReviewModal
 * (F5's guided-entry half; the server-side path validation in
 * `safe_dest_folder_rel` is unchanged and still the real guard).
 */
export function FolderPickerDialog({ libraryId, initialRel, onPick, onClose }: Props): React.JSX.Element {
  const { data: libraries } = useLibraries()
  const root = libraries?.find((l) => l.id === libraryId)?.path ?? ''

  const [currentAbs, setCurrentAbs] = useState(root)
  const [newFolderName, setNewFolderName] = useState('')

  useEffect(() => {
    if (!root) return
    // Land inside the initially-typed path if it resolves under this library,
    // otherwise start at the library root.
    if (initialRel) {
      const candidate = `${root.replace(/[\\/]+$/, '')}/${initialRel.replace(/\\/g, '/')}`
      setCurrentAbs(candidate)
    } else {
      setCurrentAbs(root)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [root])

  const { data: dir, isError } = useQuery({
    queryKey: ['fs-list', currentAbs],
    queryFn: () => api.fs.list(currentAbs),
    enabled: !!currentAbs,
    retry: false
  })

  // If the landed-on path doesn't exist (typo'd draft, or a folder that will
  // only be created on commit), fall back to the library root rather than
  // showing a dead end.
  useEffect(() => {
    if (isError && currentAbs !== root && root) setCurrentAbs(root)
  }, [isError, currentAbs, root])

  const relPath = useMemo(() => toRel(root, currentAbs), [root, currentAbs])
  const finalRel = newFolderName.trim()
    ? [relPath, newFolderName.trim()].filter(Boolean).join('/')
    : relPath

  const crumbs = relPath.split('/').filter(Boolean)

  const goToCrumb = (index: number) => {
    const rel = crumbs.slice(0, index + 1).join('/')
    setCurrentAbs(rel ? `${root.replace(/[\\/]+$/, '')}/${rel}` : root)
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50">
      <div className="flex h-[28rem] w-full max-w-md flex-col rounded-2xl border border-zinc-700 bg-zinc-900 p-5 shadow-2xl">
        <h3 className="mb-1 text-sm font-semibold text-white">Choose a folder</h3>
        <div className="mb-3 flex items-center gap-1 overflow-x-auto whitespace-nowrap text-xs text-zinc-400">
          <button onClick={() => setCurrentAbs(root)} className="hover:text-zinc-200">
            Library
          </button>
          {crumbs.map((c, i) => (
            <span key={i} className="flex items-center gap-1">
              <ChevronRight className="h-3 w-3" />
              <button onClick={() => goToCrumb(i)} className="hover:text-zinc-200">
                {c}
              </button>
            </span>
          ))}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-950">
          {(dir?.folders ?? []).length === 0 && (
            <p className="p-3 text-xs text-zinc-500">No subfolders here.</p>
          )}
          {(dir?.folders ?? []).map((f) => (
            <button
              key={f.path}
              onClick={() => setCurrentAbs(f.path)}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-zinc-200 hover:bg-zinc-800"
            >
              <Folder className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
              <span className="truncate">{f.name}</span>
            </button>
          ))}
        </div>

        <div className="mt-3 flex items-center gap-2">
          <FolderPlus className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
          <input
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            placeholder="New folder name (optional)"
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-zinc-500"
          />
        </div>

        <p className="mt-2 truncate text-xs text-zinc-500">
          Destination: <code className="text-zinc-300">{finalRel || '(library root)'}</code>
        </p>

        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800"
          >
            Cancel
          </button>
          <button
            onClick={() => onPick(finalRel)}
            disabled={!finalRel}
            className="rounded-lg bg-zinc-100 px-4 py-2 text-sm font-medium text-zinc-900 hover:bg-white disabled:opacity-50"
          >
            Select
          </button>
        </div>
      </div>
    </div>
  )
}
