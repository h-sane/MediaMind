import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { DuplicateFile, Person } from './client'

// ---------------------------------------------------------------------------
// Engine + libraries
// ---------------------------------------------------------------------------

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    retry: 20,
    retryDelay: 500,
    refetchInterval: 15_000
  })
}

export function useLibraries() {
  return useQuery({ queryKey: ['libraries'], queryFn: api.libraries.list })
}

export function useAddLibrary() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.libraries.add,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['libraries'] })
  })
}

export function useRemoveLibrary() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.libraries.remove,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['libraries'] })
  })
}

// ---------------------------------------------------------------------------
// Scans
// ---------------------------------------------------------------------------

export function useStartScan(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.scans.start(libraryId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scan', libraryId] })
  })
}

export function useStartFaceScan(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (providerId?: string) =>
      api.scans.start(libraryId, { type: 'faces', providerId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scan', libraryId] })
  })
}

export function useCancelScan(libraryId: string, jobId: string) {
  return useMutation({
    mutationFn: () => api.scans.cancel(libraryId, jobId)
  })
}

// ---------------------------------------------------------------------------
// Duplicates
// ---------------------------------------------------------------------------

export function useDuplicates(libraryId: string) {
  return useQuery({
    queryKey: ['duplicates', libraryId],
    queryFn: () => api.duplicates.list(libraryId),
    retry: false
  })
}

export function useResolve(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (resolutions: { file_id: number; action: 'keep' | 'trash' }[]) =>
      api.duplicates.resolve(libraryId, resolutions),
    onMutate: async (resolutions) => {
      await qc.cancelQueries({ queryKey: ['duplicates', libraryId] })
      const prev = qc.getQueryData(['duplicates', libraryId])
      qc.setQueryData(['duplicates', libraryId], (old: ReturnType<typeof api.duplicates.list> extends Promise<infer T> ? T : never) => {
        if (!old) return old
        return {
          ...old,
          groups: old.groups.map((g) => ({
            ...g,
            files: g.files.map((f: DuplicateFile) => {
              const res = resolutions.find((r) => r.file_id === f.id)
              return res ? { ...f, resolution: res.action } : f
            })
          }))
        }
      })
      return { prev }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(['duplicates', libraryId], ctx.prev)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['duplicates', libraryId] })
  })
}

export function useExecute(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ dryRun, expectedTrashCount }: { dryRun: boolean; expectedTrashCount: number }) =>
      api.duplicates.execute(libraryId, dryRun, expectedTrashCount),
    onSuccess: (_data, { dryRun }) => {
      if (!dryRun) qc.invalidateQueries({ queryKey: ['duplicates', libraryId] })
    }
  })
}

// ---------------------------------------------------------------------------
// Providers (M5)
// ---------------------------------------------------------------------------

export function useProviders() {
  return useQuery({
    queryKey: ['providers'],
    queryFn: api.providers.list,
    retry: false
  })
}

export function useDownloadProvider() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (providerId: string) => api.providers.download(providerId),
    onSettled: () => qc.invalidateQueries({ queryKey: ['providers'] })
  })
}

// ---------------------------------------------------------------------------
// Persons (M5)
// ---------------------------------------------------------------------------

export function usePersons(libraryId: string) {
  return useQuery({
    queryKey: ['persons', libraryId],
    queryFn: () => api.persons.list(libraryId),
    retry: false
  })
}

export function useRenamePerson(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ personId, name }: { personId: number; name: string | null }) =>
      api.persons.rename(libraryId, personId, name),
    onMutate: async ({ personId, name }) => {
      await qc.cancelQueries({ queryKey: ['persons', libraryId] })
      const prev = qc.getQueryData(['persons', libraryId])
      qc.setQueryData(['persons', libraryId], (old: ReturnType<typeof api.persons.list> extends Promise<infer T> ? T : never) => {
        if (!old) return old
        return {
          ...old,
          persons: old.persons.map((p: Person) =>
            p.id === personId ? { ...p, name } : p
          )
        }
      })
      return { prev }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(['persons', libraryId], ctx.prev)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['persons', libraryId] })
  })
}

export function useMergePersons(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ sourceId, targetId }: { sourceId: number; targetId: number }) =>
      api.persons.merge(libraryId, sourceId, targetId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['persons', libraryId] })
  })
}

export function usePersonMedia(libraryId: string, personId: number) {
  return useQuery({
    queryKey: ['person-media', libraryId, personId],
    queryFn: () => api.persons.media(libraryId, personId),
    enabled: personId > 0
  })
}

// ---------------------------------------------------------------------------
// Thumbnails (fetch with auth header → object URL, revoked on unmount)
// ---------------------------------------------------------------------------

export function useThumbnailUrl(libraryId: string, memberId: number): string | null {
  const [url, setUrl] = useState<string | null>(null)
  const urlRef = useRef<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api.duplicates
      .thumbnailUrl(libraryId, memberId)
      .then((objectUrl) => {
        if (!cancelled) {
          urlRef.current = objectUrl
          setUrl(objectUrl)
        } else {
          URL.revokeObjectURL(objectUrl)
        }
      })
      .catch(() => {})

    return () => {
      cancelled = true
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current)
        urlRef.current = null
      }
    }
  }, [libraryId, memberId])

  return url
}

// ---------------------------------------------------------------------------
// Organize (M6)
// ---------------------------------------------------------------------------

export function useOrganizePreview(libraryId: string) {
  return useQuery({
    queryKey: ['organize-preview', libraryId],
    queryFn: () => api.organize.preview(libraryId),
    retry: false
  })
}

export function useOrganizeExecute(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ dryRun, expectedPlanned }: { dryRun: boolean; expectedPlanned?: number }) =>
      api.organize.execute(libraryId, dryRun, expectedPlanned),
    onSuccess: (_data, vars) => {
      if (!vars.dryRun) {
        qc.invalidateQueries({ queryKey: ['organize-preview', libraryId] })
        qc.invalidateQueries({ queryKey: ['organize-audit', libraryId] })
      }
    }
  })
}

export function useOrganizeUndo(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.organize.undo(libraryId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['organize-preview', libraryId] })
      qc.invalidateQueries({ queryKey: ['organize-audit', libraryId] })
    }
  })
}

export function useOrganizeAudit(libraryId: string) {
  return useQuery({
    queryKey: ['organize-audit', libraryId],
    queryFn: () => api.organize.audit(libraryId),
    retry: false
  })
}

// ---------------------------------------------------------------------------
// Pending matches (M6)
// ---------------------------------------------------------------------------

export function usePendingMatches(libraryId: string) {
  return useQuery({
    queryKey: ['pending', libraryId],
    queryFn: () => api.pending.list(libraryId),
    retry: false
  })
}

export function useDecidePending(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (decisions: { pending_id: number; decision: 'confirmed' | 'rejected' }[]) =>
      api.pending.decide(libraryId, decisions),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pending', libraryId] })
      qc.invalidateQueries({ queryKey: ['persons', libraryId] })
    }
  })
}

// ---------------------------------------------------------------------------
// Multi-person review (M6 remainder)
// ---------------------------------------------------------------------------

export function useMultiPersonFiles(libraryId: string) {
  return useQuery({
    queryKey: ['multi-person', libraryId],
    queryFn: () => api.multiPerson.list(libraryId),
    retry: false
  })
}

export function useSetRouteChoices(libraryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (choices: { file_id: number; person_id: number }[]) =>
      api.multiPerson.setChoices(libraryId, choices),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['multi-person', libraryId] })
      qc.invalidateQueries({ queryKey: ['organize-preview', libraryId] })
    }
  })
}

export function useFaceThumbnailUrl(libraryId: string, faceId: number, size = 192): string | null {
  const [url, setUrl] = useState<string | null>(null)
  const urlRef = useRef<string | null>(null)

  useEffect(() => {
    let cancelled = false
    if (faceId <= 0) return
    api.persons
      .faceThumbnailUrl(libraryId, faceId, size)
      .then((objectUrl) => {
        if (!cancelled) {
          urlRef.current = objectUrl
          setUrl(objectUrl)
        } else {
          URL.revokeObjectURL(objectUrl)
        }
      })
      .catch(() => {})

    return () => {
      cancelled = true
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current)
        urlRef.current = null
      }
    }
  }, [libraryId, faceId, size])

  return url
}
