export type LeadStatus = 'new' | 'contacted' | 'qualified' | 'rejected'

export interface LeadEmail {
  id: string
  email: string
  source: string
  confidence: number
}

export interface LeadContact {
  id: string
  name: string | null
  title: string | null
  phone: string | null
  email: string | null
  source: string
}

export interface Lead {
  id: string
  place_id: string | null
  name: string
  address: string | null
  city: string | null
  state: string | null
  phone: string | null
  website: string | null
  place_types: string[]
  emails: LeadEmail[]
  contacts: LeadContact[]
  employee_count_min: number | null
  employee_count_max: number | null
  revenue_range: string | null
  location_count: number | null
  status: LeadStatus
  notes: string | null
  source: string
  scraped_at: number | null
  created_at: number
  updated_at: number
}

export interface LeadsPage {
  total: number
  page: number
  page_size: number
  items: Lead[]
}

export interface LeadUpdate {
  status?: LeadStatus
  notes?: string
  employee_count_min?: number
  employee_count_max?: number
  revenue_range?: string
}
