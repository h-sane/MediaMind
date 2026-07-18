import { useFacesPrep, useCreateUnsortedFolder } from '../../../api/hooks'

interface Props {
  libraryId: string
  onReady: () => void
}

/** Pre-scan gate shown once before Setup (not on every rescan) — checks
 * whether the folder is loose raw files or already has named subfolders, and
 * offers to move top-level loose files into an `Unsorted/` folder first. */
export function PrepPanel({ libraryId, onReady }: Props): React.JSX.Element {
  const { data: prep, isLoading, isError } = useFacesPrep(libraryId)
  const createUnsorted = useCreateUnsortedFolder(libraryId)

  const handleMove = () => {
    createUnsorted.mutate({ dry_run: false }, { onSuccess: onReady })
  }

  return (
    <div className="flex h-full flex-col items-center justify-center p-6">
      {isLoading && <p className="text-sm text-zinc-400">Checking this folder…</p>}
      {isError && <p className="text-sm text-red-600">Could not check this folder.</p>}

      {prep && !prep.has_subfolders && (
        <div className="w-full max-w-md rounded-2xl border border-zinc-200 bg-white p-6 text-center shadow-sm">
          <h2 className="text-lg font-semibold tracking-tight">This folder is ready to scan</h2>
          <p className="mt-1 text-sm text-zinc-500">
            {prep.top_level_loose_count} photo{prep.top_level_loose_count !== 1 ? 's' : ''} sitting at the top
            level, no existing organization to worry about.
          </p>
          <button
            onClick={onReady}
            className="mt-5 w-full rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-700"
          >
            Continue
          </button>
        </div>
      )}

      {prep && prep.has_subfolders && prep.recommend_unsorted && (
        <div className="w-full max-w-md rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold tracking-tight">This folder looks partially organized</h2>
          <p className="mt-2 text-sm text-zinc-500">
            Found {prep.named_subfolder_count} organized folder{prep.named_subfolder_count !== 1 ? 's' : ''} and{' '}
            {prep.top_level_loose_count} photo{prep.top_level_loose_count !== 1 ? 's' : ''} sitting loose at the
            top level. Move the loose ones into an Unsorted folder so the scan can sort them into the right
            place?
          </p>

          {createUnsorted.isError && (
            <p className="mt-3 text-sm text-red-600">{createUnsorted.error.message}</p>
          )}

          <div className="mt-5 flex flex-col gap-2">
            <button
              onClick={handleMove}
              disabled={createUnsorted.isPending}
              className="w-full rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {createUnsorted.isPending ? 'Moving…' : 'Move into Unsorted/'}
            </button>
            <button
              onClick={onReady}
              disabled={createUnsorted.isPending}
              className="text-xs text-zinc-400 underline hover:text-zinc-600"
            >
              Skip for now
            </button>
          </div>
        </div>
      )}

      {prep && prep.has_subfolders && !prep.recommend_unsorted && (
        <div className="w-full max-w-md rounded-2xl border border-zinc-200 bg-white p-6 text-center shadow-sm">
          <h2 className="text-lg font-semibold tracking-tight">This folder already looks organized</h2>
          <p className="mt-1 text-sm text-zinc-500">
            {prep.named_subfolder_count} folder{prep.named_subfolder_count !== 1 ? 's' : ''} found, nothing loose
            to sort first.
          </p>
          <button
            onClick={onReady}
            className="mt-5 w-full rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-700"
          >
            Continue
          </button>
        </div>
      )}
    </div>
  )
}
