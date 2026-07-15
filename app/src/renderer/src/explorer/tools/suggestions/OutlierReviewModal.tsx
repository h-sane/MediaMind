import { useState } from 'react'
import { Check } from 'lucide-react'
import { useSetBindingOutliers } from '../../../api/hooks'
import { MediaViewer } from '../../../components/MediaViewer'
import { FileThumbnail } from '../../../components/FileThumbnail'
import { FullscreenModalShell } from '../shared/FullscreenModalShell'
import type { FolderBinding, OutlierFile } from '../../../api/client'

function fileName(path: string): string {
  const idx = path.lastIndexOf('/')
  return idx === -1 ? path : path.slice(idx + 1)
}

function OutlierCard({
  file,
  libraryId,
  selected,
  onToggle,
  onOpenSingle
}: {
  file: OutlierFile
  libraryId: string
  selected: boolean
  onToggle: () => void
  onOpenSingle: () => void
}): React.JSX.Element {
  return (
    <div
      className={`flex flex-col overflow-hidden rounded-2xl border-2 transition ${
        selected ? 'border-emerald-500/70 bg-emerald-950/20' : 'border-zinc-700 bg-zinc-900'
      }`}
    >
      <button
        type="button"
        onClick={(e) => {
          // Same detail>1 guard as the dedupe FileTile: a double-click's
          // second click event shouldn't also flip the toggle on its way
          // to opening the full-screen view below.
          if (e.detail > 1) return
          onToggle()
        }}
        onDoubleClick={onOpenSingle}
        title={selected ? 'Approved to move — click to keep frozen' : 'Click to approve, double-click for full screen'}
        className="relative aspect-video w-full cursor-pointer bg-black"
      >
        <FileThumbnail
          libraryId={libraryId}
          path={file.path}
          kind={file.kind}
          size={1024}
          fit="contain"
          className="h-full w-full"
        />
        <span
          className={`pointer-events-none absolute left-2 top-2 flex h-6 w-6 items-center justify-center rounded-full border-2 transition ${
            selected ? 'border-emerald-500 bg-emerald-500 text-white' : 'border-white/80 bg-black/30'
          }`}
        >
          {selected && <Check className="h-3.5 w-3.5" />}
        </span>
      </button>

      <div className="px-3 py-2">
        <p className="truncate text-sm font-medium text-zinc-100" title={file.path}>
          {fileName(file.path)}
        </p>
      </div>

      <div className="border-t border-zinc-800 p-3">
        <button
          type="button"
          onClick={onToggle}
          className={`w-full rounded-xl py-2 text-sm font-medium transition ${
            selected ? 'bg-zinc-700 text-white hover:bg-zinc-600' : 'bg-emerald-600 text-white hover:bg-emerald-500'
          }`}
        >
          {selected ? 'Keep frozen instead' : 'Approve to move'}
        </button>
      </div>
    </div>
  )
}

interface Props {
  libraryId: string
  binding: FolderBinding
  onClose: () => void
}

/**
 * Reviews the detected-but-unapproved outlier files in a respected folder —
 * files that don't match the folder's bound person(s) and so stay frozen by
 * default. Approving one here adds it to the binding's
 * `accepted_outlier_file_ids`, letting it route normally on the next
 * organize sweep while the rest of the folder stays put.
 */
export function OutlierReviewModal({ libraryId, binding, onClose }: Props): React.JSX.Element {
  const [selected, setSelected] = useState<Set<number>>(
    () => new Set(binding.outliers.filter((o) => o.accepted).map((o) => o.file_id))
  )
  const [singleViewIndex, setSingleViewIndex] = useState<number | null>(null)
  const setOutliers = useSetBindingOutliers(libraryId)

  function toggle(fileId: number): void {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(fileId)) next.delete(fileId)
      else next.add(fileId)
      return next
    })
  }

  function handleSave(): void {
    setOutliers.mutate(
      { bindingId: binding.id, fileIds: Array.from(selected) },
      { onSuccess: onClose }
    )
  }

  const changed =
    selected.size !== binding.outliers.filter((o) => o.accepted).length ||
    binding.outliers.some((o) => o.accepted !== selected.has(o.file_id))

  return (
    <>
      <FullscreenModalShell
        onClose={onClose}
        suppressEscape={singleViewIndex !== null}
        headerLeft={
          <div>
            <h2 className="text-sm font-semibold text-white">{binding.folder_rel}</h2>
            <p className="text-xs text-zinc-400">
              {binding.outliers.length} outlier {binding.outliers.length === 1 ? 'file' : 'files'} —
              approve the ones that should move despite this folder being respected
            </p>
          </div>
        }
      >
        <div className="p-6 pb-28">
          <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
            {binding.outliers.map((f, i) => (
              <OutlierCard
                key={f.file_id}
                file={f}
                libraryId={libraryId}
                selected={selected.has(f.file_id)}
                onToggle={() => toggle(f.file_id)}
                onOpenSingle={() => setSingleViewIndex(i)}
              />
            ))}
          </div>
        </div>

        <div className="fixed bottom-0 left-0 right-0 border-t border-zinc-800 bg-zinc-900/95 px-8 py-4 backdrop-blur">
          <div className="mx-auto flex max-w-4xl items-center justify-between">
            <p className="text-sm text-zinc-300">
              {selected.size} of {binding.outliers.length} approved to move
            </p>
            <div className="flex items-center gap-2">
              {setOutliers.isError && (
                <span className="text-sm text-red-400">Could not save — try again.</span>
              )}
              <button
                type="button"
                onClick={onClose}
                className="rounded-xl border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={setOutliers.isPending || !changed}
                className="rounded-xl bg-zinc-100 px-5 py-2 text-sm font-medium text-zinc-900 transition hover:bg-white disabled:opacity-50"
              >
                {setOutliers.isPending ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      </FullscreenModalShell>

      {singleViewIndex !== null && (
        <MediaViewer
          libraryId={libraryId}
          files={binding.outliers.map((f) => ({ path: f.path, kind: f.kind }))}
          index={singleViewIndex}
          onClose={() => setSingleViewIndex(null)}
          onIndexChange={setSingleViewIndex}
        />
      )}
    </>
  )
}
