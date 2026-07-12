import { useQuery } from '@tanstack/react-query'
import { galleryApi } from './galleryClient'

/**
 * Recursive, date-sorted media enumeration under `root`, only enabled while
 * `active` (Gallery view mode, on a real folder — see
 * `content/useDirectoryListing.ts`). Mirrors `useRecursiveSearch`'s
 * enabled-gated shape in `useSearch.ts`.
 */
export function useGalleryItems(root: string | null, active: boolean) {
  return useQuery({
    queryKey: ['fs-gallery', root],
    queryFn: ({ signal }) => galleryApi.list(root as string, signal),
    enabled: active && !!root,
    staleTime: 5_000
  })
}
