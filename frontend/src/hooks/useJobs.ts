import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { createJob, listJobs, cancelJob } from '../api/jobs'
import type { JobConfig } from '../types/job'

export const useJobs = () =>
  useQuery({ queryKey: ['jobs'], queryFn: () => listJobs(), refetchInterval: 3000 })

export const useCreateJob = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (config: JobConfig) => createJob(config),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  })
}

export const useCancelJob = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => cancelJob(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  })
}
