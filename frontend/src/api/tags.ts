import client from './client'
import type { Lead } from '../types/lead'
import type { TagCreate, TagDetail, TagUpdate } from '../types/tag'

export const listTags = (): Promise<TagDetail[]> =>
  client.get<TagDetail[]>('/tags').then(r => r.data)

export const createTag = (data: TagCreate): Promise<TagDetail> =>
  client.post<TagDetail>('/tags', data).then(r => r.data)

export const updateTag = (id: string, data: TagUpdate): Promise<TagDetail> =>
  client.patch<TagDetail>(`/tags/${id}`, data).then(r => r.data)

export const deleteTag = (id: string): Promise<void> =>
  client.delete(`/tags/${id}`).then(() => undefined)

export const setLeadTags = (leadId: string, tagIds: string[]): Promise<Lead> =>
  client.put<Lead>(`/leads/${leadId}/tags`, { tag_ids: tagIds }).then(r => r.data)
