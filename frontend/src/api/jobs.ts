import client from './client'
import type { Job, JobConfig } from '../types/job'

export const createJob = (config: JobConfig): Promise<Job> =>
  client.post<Job>('/jobs', { config }).then(r => r.data)

export const listJobs = (page = 1): Promise<Job[]> =>
  client.get<Job[]>('/jobs', { params: { page } }).then(r => r.data)

export const getJob = (id: string): Promise<Job> =>
  client.get<Job>(`/jobs/${id}`).then(r => r.data)

export const cancelJob = (id: string): Promise<void> =>
  client.delete(`/jobs/${id}`).then(() => undefined)

export const retryJob = (id: string): Promise<Job> =>
  client.post<Job>(`/jobs/${id}/retry`).then(r => r.data)
