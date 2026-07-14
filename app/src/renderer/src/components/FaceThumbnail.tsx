import { useFaceThumbnailUrl } from '../api/hooks'
import { useNearViewport } from '../hooks/useNearViewport'

interface Props {
  libraryId: string
  faceId: number
  size?: number
  className?: string
}

export function FaceThumbnail({ libraryId, faceId, size = 192, className = '' }: Props): React.JSX.Element {
  const [ref, visible] = useNearViewport<HTMLDivElement>()
  const url = useFaceThumbnailUrl(libraryId, faceId, size, visible)

  return (
    <div
      ref={ref}
      className={`overflow-hidden rounded-full ${className}`}
      style={{ width: size, height: size }}
    >
      {url ? (
        <img src={url} alt="" className="h-full w-full rounded-full object-cover" />
      ) : (
        <div className="flex h-full w-full items-center justify-center bg-zinc-100">
          <svg className="h-1/2 w-1/2 text-zinc-300" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z" />
          </svg>
        </div>
      )}
    </div>
  )
}
