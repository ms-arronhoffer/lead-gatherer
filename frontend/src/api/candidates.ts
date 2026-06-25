import client from './client'
import type { CandidatesPage, HarvestRequest, HarvestResponse, LeadCandidate } from '../types/candidate'
import type { Lead } from '../types/lead'

export interface CandidateFilters {
  status?: string
  source?: string
  min_fit?: number
  page?: number
  page_size?: number
}

export const listCandidates = (filters: CandidateFilters = {}): Promise<CandidatesPage> =>
  client.get<CandidatesPage>('/candidates', { params: filters }).then(r => r.data)

export const harvestUrls = (body: HarvestRequest): Promise<HarvestResponse> =>
  client.post<HarvestResponse>('/candidates/harvest', body).then(r => r.data)

export const promoteCandidate = (id: string): Promise<Lead> =>
  client.post<Lead>(`/candidates/${id}/promote`).then(r => r.data)

export const dismissCandidate = (id: string): Promise<LeadCandidate> =>
  client.post<LeadCandidate>(`/candidates/${id}/dismiss`).then(r => r.data)

export const deleteCandidate = (id: string): Promise<void> =>
  client.delete(`/candidates/${id}`).then(() => undefined)
