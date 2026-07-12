import { useQuery } from '@tanstack/react-query'
import { searchApi } from './searchClient'

/**
 * Recursive backend search under `root`, only enabled while `active` (the
 * user explicitly escalated past the fast single-folder filter — see
 * `explorer/chrome/SearchBox.tsx`). Mirrors the enabled-gated shape of
 * `useFileMetadata`/`useFolderStats` in `hooks.ts`.
 */
export function useRecursiveSearch(root: string | null, query: string, active: boolean) {
  return useQuery({
    queryKey: ['fs-search', root, query],
    queryFn: ({ signal }) => searchApi.search(root as string, query, signal),
    enabled: active && !!root && query.trim().length > 0,
    staleTime: 5_000
  })
}
