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

/** All jobs of a given type, across all libraries, most recent first. */
export function selectJobsByType(jobs: Record<string, JobSnapshot>, type: string): JobSnapshot[] {
  return Object.values(jobs)
    .filter((j) => j.type === type)
    .sort((a, b) => b.created_at - a.created_at)
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

/** Most recent terminal (failed/cancelled) job for a library and type. */
export function selectFailedJobForLibrary(
  jobs: Record<string, JobSnapshot>,
  libraryId: string,
  type: string
): JobSnapshot | undefined {
  return Object.values(jobs)
    .filter(
      (j) =>
        j.library_id === libraryId &&
        j.type === type &&
        (j.state === 'failed' || j.state === 'cancelled')
    )
    .sort((a, b) => (b.finished_at ?? 0) - (a.finished_at ?? 0))[0]
}
