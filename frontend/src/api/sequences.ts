import client from './client'
import { acquireGraphTokenSilent } from '../auth/msal'
import type {
  BulkEnrollRequest, BulkEnrollResponse, Enrollment, OutboundMessage,
  PreviewRequest, PreviewResponse, Sequence, SequenceCreate, SequenceUpdate,
} from '../types/sequence'

async function graphHeaders(): Promise<Record<string, string>> {
  const tok = await acquireGraphTokenSilent()
  return tok ? { 'X-Graph-Token': tok } : {}
}

export const listSequences = (): Promise<Sequence[]> =>
  client.get<Sequence[]>('/sequences').then(r => r.data)

export const getSequence = (id: string): Promise<Sequence> =>
  client.get<Sequence>(`/sequences/${id}`).then(r => r.data)

export const createSequence = (body: SequenceCreate): Promise<Sequence> =>
  client.post<Sequence>('/sequences', body).then(r => r.data)

export const updateSequence = (id: string, body: SequenceUpdate): Promise<Sequence> =>
  client.patch<Sequence>(`/sequences/${id}`, body).then(r => r.data)

export const deleteSequence = (id: string): Promise<void> =>
  client.delete(`/sequences/${id}`).then(() => undefined)

export const bulkEnroll = async (id: string, body: BulkEnrollRequest): Promise<BulkEnrollResponse> => {
  const headers = await graphHeaders()
  return client.post<BulkEnrollResponse>(`/sequences/${id}/enroll`, body, { headers }).then(r => r.data)
}

export const listEnrollments = (id: string, status?: string): Promise<Enrollment[]> =>
  client.get<Enrollment[]>(`/sequences/${id}/enrollments`, { params: { status } }).then(r => r.data)

export const previewSequence = (body: PreviewRequest): Promise<PreviewResponse> =>
  client.post<PreviewResponse>('/sequences/preview', body).then(r => r.data)

export const listOutbound = (params: { status?: string; requires_approval?: boolean; limit?: number } = {}): Promise<OutboundMessage[]> =>
  client.get<OutboundMessage[]>('/sequences/outbound', { params }).then(r => r.data)

export const approveAndSend = async (id: string): Promise<OutboundMessage> => {
  const headers = await graphHeaders()
  return client.post<OutboundMessage>(`/sequences/outbound/${id}/approve-send`, undefined, { headers }).then(r => r.data)
}

export const cacheGraphToken = async (): Promise<void> => {
  const headers = await graphHeaders()
  if (!headers['X-Graph-Token']) return
  await client.post('/sequences/graph-token', undefined, { headers })
}
