/**
 * "Recent deletions" history client (Phase P item 4). Kept out of
 * `client.ts`/`hooks.ts` deliberately — same reasoning as `archiveClient.ts`:
 * this calls the exported `request<T>()` helper directly rather than
 * touching those shared, frozen modules.
 */
import { request } from './client'

export interface RecentDeletion {
  path: string
  permanent: boolean // true = gone for good; false = sent to the OS Recycle Bin
  ts: number
}

export interface RecentDeletionsResponse {
  deletions: RecentDeletion[]
}

export const deletionsApi = {
  list: () => request<RecentDeletionsResponse>('GET', '/v1/fs/recent-deletions')
}
