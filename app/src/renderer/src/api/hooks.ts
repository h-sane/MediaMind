import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'

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
