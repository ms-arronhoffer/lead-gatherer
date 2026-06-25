export type WebhookEvent = 'lead.created' | 'lead.updated' | 'lead.status_changed'

export const WEBHOOK_EVENTS: WebhookEvent[] = [
  'lead.created',
  'lead.updated',
  'lead.status_changed',
]

export interface Webhook {
  id: string
  url: string
  secret: string
  events: WebhookEvent[]
  enabled: boolean
  description: string | null
  created_at: number
  updated_at: number
}

export interface WebhookDelivery {
  id: string
  webhook_id: string
  event: WebhookEvent
  payload: Record<string, unknown>
  status: 'pending' | 'delivered' | 'failed'
  attempt: number
  status_code: number | null
  error: string | null
  next_retry_at: number | null
  delivered_at: number | null
  created_at: number
}

export interface WebhookCreate {
  url: string
  events: WebhookEvent[]
  enabled?: boolean
  description?: string | null
}

export interface WebhookUpdate {
  url?: string
  events?: WebhookEvent[]
  enabled?: boolean
  description?: string | null
}
