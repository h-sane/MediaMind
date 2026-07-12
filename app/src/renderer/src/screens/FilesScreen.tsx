import { useMemo, useState } from 'react'
import { useAppStore } from '../stores/app'
import { useJobsStore, selectJobForLibrary } from '../stores/jobs'
import { useLibraries, useLibraryFiles } from '../api/hooks'
import { FileThumbnail } from '../components/FileThumbnail'
import { MediaViewer } from '../components/MediaViewer'
import type { FileEntry, Library } from '../api/client'

const MEDIA_KINDS = new Set(['image', 'gif', 'video', 'audio'])

interface Props {
  libraryId: string
}

/** Group files by their parent folder ('' = library root), root first. */
function groupByFolder(files: FileEntry[]): [string, FileEntry[]][] {
  const groups = new Map<string, FileEntry[]>()
  for (const f of files) {
    const idx = f.path.lastIndexOf('/')
    const folder = idx === -1 ? '' : f.path.slice(0, idx)
    const bucket = groups.get(folder)
    if (bucket) bucket.push(f)
    else groups.set(folder, [f])
  }
  return [...groups.entries()].sort(([a], [b]) => {
    if (a === '') return -1
    if (b === '') return 1
    return a.localeCompare(b)
  })
}

function fileName(path: string): string {
  const idx = path.lastIndexOf('/')
  return idx === -1 ? path : path.slice(idx + 1)
}

/**
 * The always-available "digicam"-style browser: every file in the library,
 * straight from the filesystem. Needs no scan, works during scans, and shows
 * the real folder structure — the filesystem is the source of truth.
 */
export function FilesScreen({ libraryId }: Props): React.JSX.Element {
  const back = useAppStore((s) => s.back)
  const jobs = useJobsStore((s) => s.jobs)
  const activeJob = selectJobForLibrary(jobs, libraryId)

  const { data: libraries } = useLibraries()
  const library = libraries?.find((l: Library) => l.id === libraryId)

  const { data, isPending, isError, isFetching, refetch } = useLibraryFiles(libraryId)

  const sections = useMemo(() => (data ? groupByFolder(data.files) : []), [data])
  const mediaFiles = useMemo(
    () => (data ? data.files.filter((f) => MEDIA_KINDS.has(f.kind)) : []),
    [data]
  )
  const mediaCount = mediaFiles.length

  const [viewerIndex, setViewerIndex] = useState<number | null>(null)

  return (
    <section className="mx-auto w-full max-w-5xl px-8 py-12">
      {/* Back nav */}
      <button
        onClick={back}
        className="mb-6 flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600"
      >
        ← Back to folder
      </button>

      {/* Header */}
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">
            {library ? library.name : 'Files'}
          </h2>
          <p className="mt-1 text-sm text-zinc-500">
            {data
              ? `${data.total.toLocaleString()} files · ${mediaCount.toLocaleString()} media files`
              : 'Everything in this folder, exactly as it is on disk.'}
          </p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="rounded-lg border border-zinc-200 px-4 py-2 text-sm text-zinc-600 transition hover:bg-zinc-50 disabled:opacity-50"
        >
          {isFetching ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {/* Browsing stays available during scans — just say so. */}
      {activeJob && (
        <p className="mb-6 rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-2 text-xs text-zinc-500">
          A {activeJob.type === 'faces' ? 'people' : 'duplicate'} scan is running — you can keep
          browsing, nothing here is blocked.
        </p>
      )}

      {isPending ? (
        <p className="text-sm text-zinc-400">Reading folder…</p>
      ) : isError ? (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          Could not read this folder. Is it still available?
        </p>
      ) : !data || data.total === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-300 py-16 text-center">
          <p className="text-sm text-zinc-500">This folder is empty.</p>
        </div>
      ) : (
        <div className="space-y-8">
          {sections.map(([folder, files]) => (
            <div key={folder || '/'}>
              <h3 className="mb-3 text-xs font-medium uppercase tracking-wide text-zinc-400">
                {folder === '' ? (library ? library.name : 'Folder') : folder}
                <span className="ml-2 font-normal normal-case text-zinc-300">
                  {files.length.toLocaleString()}
                </span>
              </h3>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(8rem,1fr))] gap-3">
                {files.map((f) => {
                  const isMedia = MEDIA_KINDS.has(f.kind)
                  return (
                    <figure key={f.path} title={f.path}>
                      <button
                        type="button"
                        onClick={() => {
                          if (isMedia) setViewerIndex(mediaFiles.findIndex((m) => m.path === f.path))
                        }}
                        disabled={!isMedia}
                        className={`block w-full ${isMedia ? 'cursor-pointer' : 'cursor-default'}`}
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
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {viewerIndex !== null && (
        <MediaViewer
          libraryId={libraryId}
          files={mediaFiles}
          index={viewerIndex}
          onClose={() => setViewerIndex(null)}
          onIndexChange={setViewerIndex}
        />
      )}
    </section>
  )
}
