/**
 * Compress-to-ZIP / Extract-All client (M12 Phase H).
 *
 * Kept out of `client.ts`'s `fsOps` namespace deliberately — `client.ts` and
 * `hooks.ts` are shared central files a parallel phase is also touching, so
 * this calls the exported `request<T>()` helper directly, following the
 * exact idiom `client.ts`'s own `fsOps` namespace uses.
 */
import { request } from './client'
import type { ExecutionReport } from './client'

export const archiveApi = {
  compress: (paths: string[], dest: string, dryRun = false) =>
    request<ExecutionReport>('POST', '/v1/fs/compress', { paths, dest, dry_run: dryRun }),

  extract: (zipPath: string, dest: string, dryRun = false) =>
    request<ExecutionReport>('POST', '/v1/fs/extract', { zip_path: zipPath, dest, dry_run: dryRun })
}
