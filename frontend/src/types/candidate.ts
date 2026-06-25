export interface LeadCandidate {
  id: string
  source: string
  source_ref: string | null
  company_name: string
  website: string | null
  category: string | null
  llm_summary: string | null
  llm_fit_score: number | null
  status: 'pending' | 'promoted' | 'dismissed'
  discovered_at: number
  reviewed_at: number | null
  promoted_lead_id: string | null
}

export interface CandidatesPage {
  total: number
  page: number
  page_size: number
  items: LeadCandidate[]
}

export interface HarvestRequest {
  query: string
  max_results?: number
}

export interface HarvestResponse {
  discovered: number
  skipped: number
}
