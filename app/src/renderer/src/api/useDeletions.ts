import { useQuery } from '@tanstack/react-query'
import { deletionsApi } from './deletionsClient'

/** Only fetched while the "Recent deletions" panel is open — a plain history
 * read, no reason to keep it warm in the background otherwise. */
export function useRecentDeletions(active: boolean) {
  return useQuery({
    queryKey: ['fs-recent-deletions'],
    queryFn: () => deletionsApi.list(),
    enabled: active,
    staleTime: 5_000
  })
}
