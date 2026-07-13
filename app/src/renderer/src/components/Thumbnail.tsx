import { useThumbnailUrl } from '../api/hooks'

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
  const url = useThumbnailUrl(libraryId, memberId, size)

  if (!url) {
    return (
      <div
        className={`animate-pulse rounded-lg bg-zinc-100 ${className}`}
        aria-label="Loading thumbnail"
      />
    )
  }

  return (
    <img
      src={url}
      alt={alt}
      draggable={false}
      className={`rounded-lg ${fit === 'cover' ? 'object-cover' : 'object-contain'} ${className}`}
    />
  )
}
