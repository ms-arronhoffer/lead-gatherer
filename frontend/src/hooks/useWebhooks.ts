import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listWebhooks, createWebhook, updateWebhook, deleteWebhook,
  sendTestEvent, listDeliveries,
} from '../api/webhooks'
import type { WebhookCreate, WebhookUpdate } from '../types/webhook'

export const useWebhooks = () =>
  useQuery({ queryKey: ['webhooks'], queryFn: listWebhooks })

export const useCreateWebhook = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: WebhookCreate) => createWebhook(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['webhooks'] }),
  })
}

export const useUpdateWebhook = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: WebhookUpdate }) => updateWebhook(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['webhooks'] }),
  })
}

export const useDeleteWebhook = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteWebhook(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['webhooks'] }),
  })
}

export const useSendTestEvent = () =>
  useMutation({ mutationFn: (id: string) => sendTestEvent(id) })

export const useDeliveries = (id: string | null) =>
  useQuery({
    queryKey: ['webhook-deliveries', id],
    queryFn: () => listDeliveries(id as string),
    enabled: !!id,
    refetchInterval: id ? 5000 : false,
  })
