import { useThumbnailUrl } from '../api/hooks'
import { useNearViewport } from '../hooks/useNearViewport'

interface Props {
  libraryId: string
  memberId: number
  alt?: string
  className?: string
  size?: number
  fit?: 'cover' | 'contain'
}

export function Thumbnail({
  libraryId,
  memberId,
  alt = '',
  className = '',
  size = 256,
  fit = 'cover'
}: Props): React.JSX.Element {
  const [ref, visible] = useNearViewport<HTMLDivElement>()
  const url = useThumbnailUrl(libraryId, memberId, size, visible)

  return (
    <div ref={ref} className={className}>
      {url ? (
        <img
          src={url}
          alt={alt}
          draggable={false}
          className={`h-full w-full rounded-lg ${fit === 'cover' ? 'object-cover' : 'object-contain'}`}
        />
      ) : (
        <div className="h-full w-full animate-pulse rounded-lg bg-zinc-100" aria-label="Loading thumbnail" />
      )}
    </div>
  )
}
