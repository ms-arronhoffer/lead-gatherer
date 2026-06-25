export interface SegmentRules {
  has_email?: boolean
  has_phone?: boolean
  has_website?: boolean
  mx_valid_email?: boolean
  non_role_email?: boolean
  min_employee_count?: number
  max_employee_count?: number
  revenue_range_in?: string[]
  status_in?: string[]
  assigned?: boolean
  unassigned?: boolean
  tags_any?: string[]
  tags_all?: string[]
  place_types_any?: string[]
  place_types_all?: string[]
}

export interface Segment {
  id: string
  name: string
  description: string | null
  weight: number
  rules: SegmentRules
  enabled: boolean
  created_at: number
  updated_at: number
}

export interface SegmentCreate {
  name: string
  description?: string | null
  weight: number
  rules: SegmentRules
  enabled: boolean
}

export interface SegmentUpdate {
  name?: string
  description?: string | null
  weight?: number
  rules?: SegmentRules
  enabled?: boolean
}

export interface SegmentPreview {
  matches: number
  total: number
}
