import { useMemo, useState } from 'react'
import { useAppStore } from '../stores/app'
import { usePersons, usePersonMedia } from '../api/hooks'
import { FileThumbnail } from '../components/FileThumbnail'
import { MediaViewer } from '../components/MediaViewer'

interface Props {
  libraryId: string
  personId: number
}

function fileName(path: string): string {
  const idx = path.lastIndexOf('/')
  return idx === -1 ? path : path.slice(idx + 1)
}

/**
 * All media for one person, opened from their card in the People grid. Reuses
 * the same thumbnail/viewer components as the plain file browser — this is
 * still just the real files on disk, filtered to the ones this person is in.
 */
export function PersonDetail({ libraryId, personId }: Props): React.JSX.Element {
  const back = useAppStore((s) => s.back)
  const { data: personsData } = usePersons(libraryId)
  const person = personsData?.persons.find((p) => p.id === personId)

  const { data: media, isLoading, isError } = usePersonMedia(libraryId, personId)
  const files = useMemo(() => media ?? [], [media])

  const [viewerIndex, setViewerIndex] = useState<number | null>(null)

  const displayName = person?.name ?? person?.auto_label ?? 'Person'

  return (
    <section className="mx-auto w-full max-w-5xl px-8 py-12">
      <button
        onClick={back}
        className="mb-6 flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600"
      >
        ← Back to people
      </button>

      <div className="mb-6">
        <h2 className="text-lg font-semibold tracking-tight">{displayName}</h2>
        <p className="mt-1 text-sm text-zinc-500">
          {files.length} {files.length === 1 ? 'photo/video' : 'photos/videos'}
        </p>
      </div>

      {isLoading && <p className="text-sm text-zinc-400">Loading…</p>}

      {isError && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          Could not load this person's media.
        </p>
      )}

      {!isLoading && !isError && files.length === 0 && (
        <div className="rounded-2xl border border-dashed border-zinc-300 py-16 text-center">
          <p className="text-sm text-zinc-500">No media found for this person.</p>
        </div>
      )}

      {files.length > 0 && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(8rem,1fr))] gap-3">
          {files.map((f, i) => (
            <figure key={f.file_id} title={f.path}>
              <button
                type="button"
                onClick={() => setViewerIndex(i)}
                className="block w-full cursor-pointer"
              >
                <FileThumbnail
                  libraryId={libraryId}
                  path={f.path}
                  kind={f.kind}
                  className="aspect-square w-full"
                />
              </button>
              <figcaption className="mt-1 truncate text-center text-[11px] text-zinc-500">
                {fileName(f.path)}
              </figcaption>
            </figure>
          ))}
        </div>
      )}

      {viewerIndex !== null && (
        <MediaViewer
          libraryId={libraryId}
          files={files}
          index={viewerIndex}
          onClose={() => setViewerIndex(null)}
          onIndexChange={setViewerIndex}
        />
      )}
    </section>
  )
}
