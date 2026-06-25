import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  applySegmentTuning, createSegment, deleteSegment, getSegmentTuning, listSegments,
  previewSegment, rescoreAll, updateSegment,
} from '../api/segments'
import type { SegmentCreate, SegmentUpdate } from '../types/segment'

export const useSegments = () =>
  useQuery({ queryKey: ['segments'], queryFn: listSegments })

export const useSegmentTuning = () =>
  useQuery({ queryKey: ['segment-tuning'], queryFn: getSegmentTuning })

export const useApplySegmentTuning = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => applySegmentTuning(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['segments'] })
      qc.invalidateQueries({ queryKey: ['segment-tuning'] })
      qc.invalidateQueries({ queryKey: ['leads'] })
      qc.invalidateQueries({ queryKey: ['hot-leads'] })
    },
  })
}

export const useCreateSegment = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: SegmentCreate) => createSegment(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['segments'] })
      qc.invalidateQueries({ queryKey: ['leads'] })
    },
  })
}

export const useUpdateSegment = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: SegmentUpdate }) => updateSegment(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['segments'] })
      qc.invalidateQueries({ queryKey: ['leads'] })
    },
  })
}

export const useDeleteSegment = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteSegment(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['segments'] })
      qc.invalidateQueries({ queryKey: ['leads'] })
    },
  })
}

export const usePreviewSegment = () =>
  useMutation({ mutationFn: (data: SegmentCreate) => previewSegment(data) })

export const useRescoreAll = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => rescoreAll(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['leads'] }),
  })
}
