import { useThumbnailUrl } from '../api/hooks'

interface Props {
  libraryId: string
  memberId: number
  alt?: string
  className?: string
}

export function Thumbnail({ libraryId, memberId, alt = '', className = '' }: Props): React.JSX.Element {
  const url = useThumbnailUrl(libraryId, memberId)

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
      className={`rounded-lg object-cover ${className}`}
    />
  )
}
