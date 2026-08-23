import { useFolderFaces } from '../api/hooks'
import { useNearViewport } from '../hooks/useNearViewport'
import { FaceThumbnail } from './FaceThumbnail'

interface Props {
  /** Absolute folder path. */
  path: string
  /** Square box the composed faces (or fallback) fill. */
  size: number
  /** Rendered when the folder has no named people (outside a scanned library,
   * or nobody named yet) — normally the plain <Folder> icon. */
  fallback: React.ReactNode
  className?: string
}

/**
 * A folder's thumbnail as the named people inside it: overlapping face crops
 * (most-frequent first) with a "+N" badge when there are more than fit. Falls
 * back to the plain folder icon whenever the backend has no named people for
 * this folder. Fetch is gated on near-viewport so a large directory doesn't
 * fire one request per off-screen folder.
 */
export function FolderFaceThumbnail({ path, size, fallback, className = '' }: Props): React.JSX.Element {
  const [ref, visible] = useNearViewport<HTMLDivElement>()
  const { data } = useFolderFaces(path, visible)

  const libraryId = data?.library_id ?? null
  const persons = libraryId ? data!.persons : []
  const extra = data ? data.total_persons - persons.length : 0
  // Circles overlap by 40%, so N of them span faceSize * (1 + 0.6·(N-1)) — pick
  // faceSize so the whole stack fits the box no matter how many are shown.
  const shown = persons.length + (extra > 0 ? 1 : 0)
  const faceSize = Math.round(size / (1 + 0.6 * Math.max(0, shown - 1)))
  const overlap = Math.round(faceSize * 0.4)

  return (
    <div
      ref={ref}
      className={`flex items-center justify-center ${className}`}
      style={{ width: size, height: size }}
    >
      {libraryId && persons.length > 0 ? (
        <div className="flex items-center">
          {persons.map((p, i) => (
            <span
              key={p.person_id}
              className="inline-flex shrink-0"
              style={i === 0 ? undefined : { marginLeft: -overlap }}
            >
              <FaceThumbnail
                libraryId={libraryId}
                faceId={p.sample_face_id}
                size={faceSize}
                className="ring-2 ring-white"
              />
            </span>
          ))}
          {extra > 0 && (
            <div
              className="flex shrink-0 items-center justify-center rounded-full bg-zinc-200 font-medium text-zinc-600 ring-2 ring-white"
              style={{
                width: faceSize,
                height: faceSize,
                marginLeft: persons.length > 0 ? -overlap : 0,
                fontSize: Math.max(9, Math.round(faceSize * 0.32))
              }}
            >
              +{extra}
            </div>
          )}
        </div>
      ) : (
        fallback
      )}
    </div>
  )
}
