import { useFaceThumbnailUrl } from '../api/hooks'

interface Props {
  libraryId: string
  faceId: number
  size?: number
  className?: string
}

export function FaceThumbnail({ libraryId, faceId, size = 192, className = '' }: Props): React.JSX.Element {
  const url = useFaceThumbnailUrl(libraryId, faceId, size)

  if (!url) {
    return (
      <div
        className={`flex items-center justify-center rounded-full bg-zinc-100 ${className}`}
        style={{ width: size, height: size }}
      >
        <svg
          className="h-1/2 w-1/2 text-zinc-300"
          fill="currentColor"
          viewBox="0 0 24 24"
        >
          <path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z" />
        </svg>
      </div>
    )
  }

  return (
    <img
      src={url}
      alt=""
      className={`rounded-full object-cover ${className}`}
      style={{ width: size, height: size }}
    />
  )
}
