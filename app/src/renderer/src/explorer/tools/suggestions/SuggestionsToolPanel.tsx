import { Copy, CopyCheck, FolderPlus, Sparkles, UserCheck, X } from 'lucide-react'
import {
  useDecidePending,
  useDismissDiscoveredFolder,
  useDismissDuplicateFlag,
  useDiscoverySuggestions,
  useDuplicateFlags,
  useDuplicates,
  useLibraries,
  usePendingMatches,
  useRegisterDiscoveredFolder
} from '../../../api/hooks'
import { useExplorerStore, parentPath } from '../../../stores/explorer'
import { FaceThumbnail } from '../../../components/FaceThumbnail'
import type { DiscoverySuggestion, DuplicateFlag, PendingMatch } from '../../../api/client'

interface Props {
  libraryId: string
  folderPath: string
}

/** Library-relative path -> absolute, joined with this project's Windows-first
 * separator convention (matches `useFileOps.ts`'s `joinPath`). */
function toAbsolute(libraryRoot: string, relPath: string): string {
  const trimmed = libraryRoot.replace(/[\\/]+$/, '')
  return `${trimmed}\\${relPath.replace(/\//g, '\\')}`
}

// ---------------------------------------------------------------------------
// Duplicate flags section — incremental, advisory notices raised as files are
// ingested (Performance & Ingest V4 Phase 3), independent of the manual
// dedupe scan below. Nothing is trashed from here; "Show match" just jumps
// to the matched file's folder for the user to look and decide.
// ---------------------------------------------------------------------------

function DuplicateFlagsSection({ libraryId }: { libraryId: string }): React.JSX.Element | null {
  const { data: libraries } = useLibraries()
  const { data: flags, isLoading } = useDuplicateFlags(libraryId)
  const dismiss = useDismissDuplicateFlag(libraryId)
  const navigate = useExplorerStore((s) => s.navigate)
  const libraryRoot = libraries?.find((l) => l.id === libraryId)?.path

  if (isLoading || !flags || flags.length === 0) return null

  const showMatch = (flag: DuplicateFlag) => {
    if (!libraryRoot) return
    navigate(parentPath(toAbsolute(libraryRoot, flag.match_path)))
  }

  return (
    <section>
      <div className="mb-3 flex items-center gap-2">
        <Copy className="h-4 w-4 text-zinc-400" />
        <h3 className="text-sm font-semibold text-zinc-800">Possible duplicates</h3>
      </div>
      <div className="space-y-2">
        {flags.map((flag) => (
          <div
            key={flag.id}
            className="flex items-center justify-between gap-3 rounded-2xl border border-zinc-200 bg-white p-4"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-zinc-800">{flag.path.split(/[\\/]/).pop()}</p>
              <p className="mt-0.5 truncate text-xs text-zinc-500">
                {flag.match_type === 'exact' ? 'Exact match' : 'Near match'} of{' '}
                {flag.match_path.split(/[\\/]/).pop()}
              </p>
            </div>
            <div className="flex shrink-0 gap-2">
              <button
                onClick={() => showMatch(flag)}
                disabled={!libraryRoot}
                className="rounded-lg border border-zinc-200 px-3 py-1.5 text-sm text-zinc-600 transition hover:bg-zinc-50 disabled:opacity-50"
              >
                Show match
              </button>
              <button
                onClick={() => dismiss.mutate(flag.id)}
                disabled={dismiss.isPending}
                className="rounded-lg border border-zinc-200 px-2.5 py-1.5 text-zinc-500 transition hover:bg-zinc-50 disabled:opacity-50"
                title="Dismiss"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Discovery suggestions section — folders with lots of new media found
// outside any registered library (only populated when auto_scan_mode is
// 'system'). Registering turns the folder into a real library; dismissing
// just drops it from the list.
// ---------------------------------------------------------------------------

function DiscoverySuggestionsSection(): React.JSX.Element | null {
  const { data: suggestions, isLoading } = useDiscoverySuggestions()
  const register = useRegisterDiscoveredFolder()
  const dismiss = useDismissDiscoveredFolder()

  if (isLoading || !suggestions || suggestions.length === 0) return null

  const label = (s: DiscoverySuggestion) =>
    `${s.media_count} new ${s.media_count === 1 ? 'photo/video' : 'photos/videos'}`

  return (
    <section>
      <div className="mb-3 flex items-center gap-2">
        <FolderPlus className="h-4 w-4 text-zinc-400" />
        <h3 className="text-sm font-semibold text-zinc-800">Folders to add</h3>
      </div>
      <div className="space-y-2">
        {suggestions.map((s) => (
          <div
            key={s.folder}
            className="flex items-center justify-between gap-3 rounded-2xl border border-zinc-200 bg-white p-4"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-zinc-800">{s.folder}</p>
              <p className="mt-0.5 truncate text-xs text-zinc-500">{label(s)}</p>
            </div>
            <div className="flex shrink-0 gap-2">
              <button
                onClick={() => dismiss.mutate(s.folder)}
                disabled={dismiss.isPending}
                className="rounded-lg border border-zinc-200 px-2.5 py-1.5 text-zinc-500 transition hover:bg-zinc-50 disabled:opacity-50"
                title="Dismiss"
              >
                <X className="h-4 w-4" />
              </button>
              <button
                onClick={() => register.mutate(s.folder)}
                disabled={register.isPending}
                className="rounded-lg bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-zinc-700 disabled:opacity-50"
              >
                Add as library
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Pending face matches section — same underlying queue as the Facial
// Recognition tab's `PendingReviewPanel`; both read/write `usePendingMatches`
// / `useDecidePending` so confirming here keeps that panel in sync too.
// ---------------------------------------------------------------------------

function PendingMatchesSection({ libraryId }: { libraryId: string }): React.JSX.Element | null {
  const { data: matches, isLoading } = usePendingMatches(libraryId)
  const decide = useDecidePending(libraryId)

  if (isLoading || !matches || matches.length === 0) return null

  const onDecide = (match: PendingMatch, decision: 'confirmed' | 'rejected') => {
    decide.mutate([{ pending_id: match.id, decision }])
  }

  return (
    <section>
      <div className="mb-3 flex items-center gap-2">
        <UserCheck className="h-4 w-4 text-zinc-400" />
        <h3 className="text-sm font-semibold text-zinc-800">New photos to confirm</h3>
      </div>
      <div className="space-y-2">
        {matches.map((match) => (
          <div
            key={match.id}
            className="flex items-center gap-4 rounded-2xl border border-zinc-200 bg-white p-4"
          >
            <FaceThumbnail libraryId={libraryId} faceId={match.face_id} size={48} />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-zinc-800">
                Assign to <span className="text-zinc-900">{match.person_name}</span>?
              </p>
              <p className="mt-0.5 text-xs text-zinc-400">{Math.round(match.confidence * 100)}% confidence</p>
            </div>
            <div className="flex shrink-0 gap-2">
              <button
                onClick={() => onDecide(match, 'rejected')}
                disabled={decide.isPending}
                className="rounded-lg border border-zinc-200 px-3 py-1.5 text-sm text-zinc-600 transition hover:bg-zinc-50 disabled:opacity-50"
              >
                Reject
              </button>
              <button
                onClick={() => onDecide(match, 'confirmed')}
                disabled={decide.isPending}
                className="rounded-lg bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-zinc-700 disabled:opacity-50"
              >
                Confirm
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Duplicates section — a lean projection of the dedupe tool's own state.
// No separate scan/queue here; it just reads whatever the last dedupe scan
// produced and links over to the full review surface.
// ---------------------------------------------------------------------------

function DuplicatesSection({ libraryId }: { libraryId: string }): React.JSX.Element {
  const setToolMode = useExplorerStore((s) => s.setToolMode)
  const { data, isError, isLoading } = useDuplicates(libraryId)

  return (
    <section>
      <div className="mb-3 flex items-center gap-2">
        <CopyCheck className="h-4 w-4 text-zinc-400" />
        <h3 className="text-sm font-semibold text-zinc-800">Duplicates</h3>
      </div>

      {isLoading && <p className="text-sm text-zinc-400">Checking…</p>}

      {!isLoading && isError && (
        <div className="rounded-2xl border border-dashed border-zinc-300 p-4">
          <p className="text-sm text-zinc-500">No duplicate scan yet.</p>
          <button
            onClick={() => setToolMode('dedupe')}
            className="mt-2 rounded-lg border border-zinc-200 px-3 py-1.5 text-sm text-zinc-600 transition hover:bg-zinc-50"
          >
            Run duplicate detection
          </button>
        </div>
      )}

      {!isLoading && !isError && data && data.summary.groups === 0 && (
        <div className="rounded-2xl border border-zinc-200 bg-white p-4">
          <p className="text-sm text-zinc-500">No duplicates found in this folder.</p>
        </div>
      )}

      {!isLoading && !isError && data && data.summary.groups > 0 && (
        <div className="flex items-center justify-between rounded-2xl border border-zinc-200 bg-white p-4">
          <div>
            <p className="text-sm font-medium text-zinc-800">
              {data.summary.groups} duplicate {data.summary.groups === 1 ? 'group' : 'groups'}
            </p>
            <p className="mt-0.5 text-xs text-zinc-500">
              {data.summary.files} files · {formatBytes(data.summary.reclaimable_bytes)} reclaimable
            </p>
          </div>
          <button
            onClick={() => setToolMode('dedupe')}
            className="rounded-lg bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-zinc-700"
          >
            Review
          </button>
        </div>
      )}
    </section>
  )
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let n = bytes
  let i = 0
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024
    i++
  }
  return `${n.toFixed(n >= 10 || i === 0 ? 0 : 1)} ${units[i]}`
}

// ---------------------------------------------------------------------------
// Root panel
// ---------------------------------------------------------------------------

/**
 * Suggestions surface — shell-level, scoped to the currently open folder like
 * the dedupe/faces tools. Covers duplicates (both incrementally-flagged and
 * the old manual-scan groups) and pending face-match confirmations. Folder-
 * organization suggestions (person/group folder matches) moved to the Facial
 * Recognition tab, where they now surface directly as tiles on the person
 * they match instead of a separate accept/dismiss queue here.
 */
export function SuggestionsToolPanel({ libraryId, folderPath: _folderPath }: Props): React.JSX.Element {
  const { data: flags } = useDuplicateFlags(libraryId)
  const { data: pending } = usePendingMatches(libraryId)
  const { data: duplicates } = useDuplicates(libraryId)
  const { data: discovery } = useDiscoverySuggestions()

  const nothingToShow =
    (flags?.length ?? 0) === 0 &&
    (pending?.length ?? 0) === 0 &&
    (duplicates?.summary.groups ?? 0) === 0 &&
    (discovery?.length ?? 0) === 0

  return (
    <div className="h-full overflow-y-auto p-6 pb-24">
      <div className="mb-6">
        <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <Sparkles className="h-5 w-5 text-zinc-400" />
          Suggestions
        </h2>
        <p className="mt-1 text-sm text-zinc-500">
          Duplicates and pending face-match confirmations MediaMind noticed in this folder.
        </p>
      </div>

      {nothingToShow && (
        <div className="rounded-2xl border border-dashed border-zinc-300 py-16 text-center">
          <p className="text-sm text-zinc-500">No suggestions right now.</p>
        </div>
      )}

      <div className="space-y-8">
        <DiscoverySuggestionsSection />
        <DuplicateFlagsSection libraryId={libraryId} />
        <PendingMatchesSection libraryId={libraryId} />
        <DuplicatesSection libraryId={libraryId} />
      </div>
    </div>
  )
}
