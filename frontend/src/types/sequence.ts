export interface SequenceStep {
  day_offset: number
  subject_template: string
  body_template: string
  requires_approval: boolean
}

export interface Sequence {
  id: string
  name: string
  description: string | null
  steps: SequenceStep[]
  owner_user_id: string | null
  enabled: boolean
  created_at: number
  updated_at: number
}

export interface SequenceCreate {
  name: string
  description?: string | null
  steps: SequenceStep[]
  enabled?: boolean
}

export interface SequenceUpdate {
  name?: string
  description?: string | null
  steps?: SequenceStep[]
  enabled?: boolean
}

export interface Enrollment {
  id: string
  lead_id: string
  sequence_id: string
  enrolled_by_user_id: string
  step_idx: number
  status: string
  next_send_at: number | null
  started_at: number
  completed_at: number | null
}

export interface OutboundMessage {
  id: string
  enrollment_id: string
  lead_id: string
  user_id: string
  step_idx: number
  to_email: string
  subject: string
  body: string
  requires_approval: boolean
  status: string
  sent_at: number | null
  graph_message_id: string | null
  graph_conversation_id: string | null
  reply_at: number | null
  bounce_at: number | null
  error: string | null
  created_at: number
}

export interface PreviewRequest {
  sequence_id: string
  lead_id: string
  step_idx?: number
}

export interface PreviewResponse {
  subject: string
  body: string
  opener: string
  to_email: string | null
}

export interface BulkEnrollRequest {
  sequence_id: string
  lead_ids: string[]
}

export interface BulkEnrollResponse {
  enrolled: number
  skipped: number
}
