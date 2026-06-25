export type DiscoverySource = 'google_places' | 'brave' | 'osm'

export interface JobConfig {
  category: string
  location: string
  max_results: number
  sources: DiscoverySource[]
  employee_min?: number | null
  employee_max?: number | null
  revenue_range?: string | null
  enable_website_scraping: boolean
  enable_serp_enrichment: boolean
}

export interface Job {
  id: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  phase: string | null
  config: JobConfig
  total_places: number
  processed_places: number
  leads_found: number
  error_message: string | null
  created_at: number
  updated_at: number
  progress_pct: number
  attempt?: number
  checkpoint?: Record<string, unknown>
}

export interface JobProgressEvent {
  job_id: string
  status: string
  phase: string | null
  processed_places: number
  total_places: number
  leads_found: number
  progress_pct: number
}
