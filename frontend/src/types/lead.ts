export type LeadStatus = 'new' | 'contacted' | 'qualified' | 'rejected'

import type { User } from './user'
import type { Tag } from './tag'

export interface LeadEmail {
  id: string
  email: string
  source: string
  confidence: number
  mx_valid?: boolean | null
  role_based?: boolean
  disposable?: boolean
  validated_at?: number | null
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
  phone_normalized?: string | null
  phone_type?: string | null
  website: string | null
  place_types: string[]
  emails: LeadEmail[]
  contacts: LeadContact[]
  tags: Tag[]
  employee_count_min: number | null
  employee_count_max: number | null
  revenue_range: string | null
  location_count: number | null
  status: LeadStatus
  notes: string | null
  source: string
  scraped_at: number | null
  assigned_to_user_id?: string | null
  assignee?: User | null
  last_touched_at?: number | null
  last_touched_by_user_id?: string | null
  last_touched_by?: User | null
  score?: number | null
  fit_score?: number | null
  intent_score?: number | null
  priority_score?: number | null
  score_breakdown?: Record<string, unknown>
  matched_segment_ids?: string[]
  summary?: string | null
  summary_generated_at?: number | null
  fit_reasons?: FitReason[]
  fit_reasons_generated_at?: number | null
  signals?: LeadSignal[]
  created_at: number
  updated_at: number
}

export interface LeadSignal {
  id: string
  type: string
  strength: number
  source: string
  payload: Record<string, unknown>
  detected_at: number
}

export interface FitReason {
  segment_id: string
  segment_name: string
  rationale: string
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
  name?: string
  website?: string | null
  phone?: string | null
  address?: string | null
  city?: string | null
  state?: string | null
  place_types?: string[]
}

export interface LeadActivity {
  id: string
  lead_id: string
  user_id: string | null
  user?: User | null
  action: string
  payload: Record<string, unknown>
  created_at: number
}
