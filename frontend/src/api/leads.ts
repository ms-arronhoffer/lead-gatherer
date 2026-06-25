import client from './client'
import type { Lead, LeadActivity, LeadsPage, LeadUpdate } from '../types/lead'

export interface LeadFilters {
  status?: string
  city?: string
  state?: string
  has_email?: boolean
  job_id?: string
  search?: string
  assigned_to?: string
  min_score?: number
  max_score?: number
  segment_id?: string
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

export const assignLead = (id: string, userId: string | null): Promise<Lead> =>
  client.put<Lead>(`/leads/${id}/assign`, { user_id: userId }).then(r => r.data)

export const listLeadActivities = (id: string): Promise<LeadActivity[]> =>
  client.get<LeadActivity[]>(`/leads/${id}/activities`).then(r => r.data)

export const deleteLead = (id: string): Promise<void> =>
  client.delete(`/leads/${id}`).then(() => undefined)

export const revalidateLead = (id: string): Promise<Lead> =>
  client.post<Lead>(`/leads/${id}/revalidate`).then(r => r.data)

export const enrichLead = (id: string): Promise<{ status: string; lead_id: string }> =>
  client.post<{ status: string; lead_id: string }>(`/leads/${id}/enrich`).then(r => r.data)

export const exportLeadsCsv = (filters: LeadFilters = {}): void => {
  const params = new URLSearchParams(
    Object.entries(filters)
      .filter(([, v]) => v !== undefined && v !== null)
      .map(([k, v]) => [k, String(v)])
  ).toString()
  window.open(`/api/v1/leads/export/csv${params ? `?${params}` : ''}`, '_blank')
}
