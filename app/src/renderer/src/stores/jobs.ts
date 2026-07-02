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

export function selectJobForLibrary(jobs: Record<string, JobSnapshot>, libraryId: string): JobSnapshot | undefined {
  return Object.values(jobs).find(
    (j) => j.library_id === libraryId && (j.state === 'queued' || j.state === 'running')
  )
}
