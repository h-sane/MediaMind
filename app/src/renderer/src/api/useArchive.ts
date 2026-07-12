import { useMutation, useQueryClient } from '@tanstack/react-query'
import { archiveApi } from './archiveClient'

// ---------------------------------------------------------------------------
// Compress to ZIP / Extract All (M12 Phase H)
//
// Mirrors `hooks.ts`'s `useFsMove`/`useFsCopy` idiom exactly (mutationFn +
// folder-scoped invalidation) — kept in this separate file rather than
// `hooks.ts` itself, which a parallel phase is also editing.
// ---------------------------------------------------------------------------

export function useCompress() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ paths, dest, dryRun }: { paths: string[]; dest: string; dryRun?: boolean; folder: string }) =>
      archiveApi.compress(paths, dest, dryRun ?? false),
    onSuccess: (_data, { folder }) => {
      qc.invalidateQueries({ queryKey: ['browse', folder] })
      qc.invalidateQueries({ queryKey: ['fs-gallery', folder] })
    }
  })
}

export function useExtract() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      zipPath,
      dest,
      dryRun
    }: {
      zipPath: string
      dest: string
      dryRun?: boolean
      folder: string
    }) => archiveApi.extract(zipPath, dest, dryRun ?? false),
    onSuccess: (_data, { folder }) => {
      qc.invalidateQueries({ queryKey: ['browse', folder] })
      qc.invalidateQueries({ queryKey: ['fs-gallery', folder] })
    }
  })
}
