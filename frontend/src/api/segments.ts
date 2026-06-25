import client from './client'
import type {
  Segment, SegmentCreate, SegmentPreview, SegmentTuning, SegmentTuningApplied, SegmentUpdate,
} from '../types/segment'

export const listSegments = (): Promise<Segment[]> =>
  client.get<Segment[]>('/segments').then(r => r.data)

export const createSegment = (data: SegmentCreate): Promise<Segment> =>
  client.post<Segment>('/segments', data).then(r => r.data)

export const updateSegment = (id: string, data: SegmentUpdate): Promise<Segment> =>
  client.patch<Segment>(`/segments/${id}`, data).then(r => r.data)

export const deleteSegment = (id: string): Promise<void> =>
  client.delete(`/segments/${id}`).then(() => undefined)

export const previewSegment = (data: SegmentCreate): Promise<SegmentPreview> =>
  client.post<SegmentPreview>('/segments/preview', data).then(r => r.data)

export const rescoreAll = (): Promise<{ rescored: number }> =>
  client.post<{ rescored: number }>('/segments/rescore').then(r => r.data)

export const getSegmentTuning = (): Promise<SegmentTuning[]> =>
  client.get<SegmentTuning[]>('/segments/tuning').then(r => r.data)

export const applySegmentTuning = (): Promise<SegmentTuningApplied> =>
  client.post<SegmentTuningApplied>('/segments/tuning/apply').then(r => r.data)
