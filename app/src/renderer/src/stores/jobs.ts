import { create } from 'zustand'
import type { JobSnapshot } from '../api/client'

interface JobsStore {
  jobs: Record<string, JobSnapshot>
  upsert: (job: JobSnapshot) => void
}

export const useJobsStore = create<JobsStore>((set) => ({
  jobs: {},
  upsert: (job) => set((state) => ({ jobs: { ...state.jobs, [job.id]: job } }))
}))

/** Active (queued or running) job for a library, optionally filtered by type. */
export function selectJobForLibrary(
  jobs: Record<string, JobSnapshot>,
  libraryId: string,
  type?: string
): JobSnapshot | undefined {
  return Object.values(jobs).find(
    (j) =>
      j.library_id === libraryId &&
      (j.state === 'queued' || j.state === 'running') &&
      (type === undefined || j.type === type)
  )
}

/** Most recent job (any state) for a given type, across all libraries. */
export function selectJobByType(
  jobs: Record<string, JobSnapshot>,
  type: string
): JobSnapshot | undefined {
  return Object.values(jobs)
    .filter((j) => j.type === type)
    .sort((a, b) => b.created_at - a.created_at)[0]
}
