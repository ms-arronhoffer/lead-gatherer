import client from './client'
import type { Lead, LeadsPage, LeadUpdate } from '../types/lead'

export interface LeadFilters {
  status?: string
  city?: string
  state?: string
  has_email?: boolean
  job_id?: string
  search?: string
  sort_by?: string
  sort_dir?: string
  page?: number
  page_size?: number
}

export const listLeads = (filters: LeadFilters = {}): Promise<LeadsPage> =>
  client.get<LeadsPage>('/leads', { params: filters }).then(r => r.data)

export const getLead = (id: string): Promise<Lead> =>
  client.get<Lead>(`/leads/${id}`).then(r => r.data)

export const updateLead = (id: string, data: LeadUpdate): Promise<Lead> =>
  client.patch<Lead>(`/leads/${id}`, data).then(r => r.data)

export const deleteLead = (id: string): Promise<void> =>
  client.delete(`/leads/${id}`).then(() => undefined)

export const exportLeadsCsv = (filters: LeadFilters = {}): void => {
  const params = new URLSearchParams(
    Object.entries(filters)
      .filter(([, v]) => v !== undefined && v !== null)
      .map(([k, v]) => [k, String(v)])
  ).toString()
  window.open(`/api/v1/leads/export/csv${params ? `?${params}` : ''}`, '_blank')
}
