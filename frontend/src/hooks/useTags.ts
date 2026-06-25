import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createTag, deleteTag, listTags, setLeadTags, updateTag } from '../api/tags'
import type { TagCreate, TagUpdate } from '../types/tag'

export const useTags = () =>
  useQuery({ queryKey: ['tags'], queryFn: listTags })

export const useCreateTag = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: TagCreate) => createTag(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tags'] }),
  })
}

export const useUpdateTag = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: TagUpdate }) => updateTag(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tags'] })
      qc.invalidateQueries({ queryKey: ['leads'] })
    },
  })
}

export const useDeleteTag = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteTag(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tags'] })
      qc.invalidateQueries({ queryKey: ['leads'] })
    },
  })
}

export const useSetLeadTags = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ leadId, tagIds }: { leadId: string; tagIds: string[] }) =>
      setLeadTags(leadId, tagIds),
    onSuccess: (_data, { leadId }) => {
      qc.invalidateQueries({ queryKey: ['lead', leadId] })
      qc.invalidateQueries({ queryKey: ['leads'] })
      qc.invalidateQueries({ queryKey: ['leadActivities', leadId] })
    },
  })
}
