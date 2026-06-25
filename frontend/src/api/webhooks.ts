import client from './client'
import type { Webhook, WebhookCreate, WebhookDelivery, WebhookUpdate } from '../types/webhook'

export const listWebhooks = (): Promise<Webhook[]> =>
  client.get<Webhook[]>('/webhooks').then(r => r.data)

export const createWebhook = (data: WebhookCreate): Promise<Webhook> =>
  client.post<Webhook>('/webhooks', data).then(r => r.data)

export const updateWebhook = (id: string, data: WebhookUpdate): Promise<Webhook> =>
  client.patch<Webhook>(`/webhooks/${id}`, data).then(r => r.data)

export const deleteWebhook = (id: string): Promise<void> =>
  client.delete(`/webhooks/${id}`).then(() => undefined)

export const sendTestEvent = (id: string): Promise<void> =>
  client.post(`/webhooks/${id}/test`).then(() => undefined)

export const listDeliveries = (id: string, limit = 20): Promise<WebhookDelivery[]> =>
  client.get<WebhookDelivery[]>(`/webhooks/${id}/deliveries`, { params: { limit } }).then(r => r.data)
