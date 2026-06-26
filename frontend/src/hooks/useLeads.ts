import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listLeads, updateLead, deleteLead, getLead, revalidateLead, enrichLead, linkedinEnrichLead, assignLead, listLeadActivities, getSignalMetrics } from '../api/leads'
import type { LeadFilters } from '../api/leads'
import type { Lead, LeadsPage, LeadUpdate } from '../types/lead'

export const useLeads = (filters: LeadFilters) =>
  useQuery({
    queryKey: ['leads', filters],
    queryFn: () => listLeads(filters),
  })

// Default priority_score threshold above which a lead is considered "hot"
// (mirrors the backend `hot_lead_threshold` setting).
export const HOT_LEAD_THRESHOLD = 80

export const useHotLeads = (minScore: number = HOT_LEAD_THRESHOLD, pageSize = 100) =>
  useQuery({
    queryKey: ['hot-leads', minScore, pageSize],
    queryFn: () => listLeads({
      min_score: minScore,
      sort_by: 'priority_score',
      sort_dir: 'desc',
      page: 1,
      page_size: pageSize,
    }),
    refetchInterval: 30_000,
  })

export const useSignalMetrics = () =>
  useQuery({ queryKey: ['signal-metrics'], queryFn: getSignalMetrics })

export const useLead = (id: string | null) =>
  useQuery({
    queryKey: ['lead', id],
    queryFn: () => getLead(id as string),
    enabled: !!id,
  })

export const useUpdateLead = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: LeadUpdate }) => updateLead(id, data),
    onMutate: async ({ id, data }) => {
      await qc.cancelQueries({ queryKey: ['leads'] })
      await qc.cancelQueries({ queryKey: ['lead', id] })

      const prevLists = qc.getQueriesData<LeadsPage>({ queryKey: ['leads'] })
      const prevLead = qc.getQueryData<Lead>(['lead', id])

      qc.setQueriesData<LeadsPage>({ queryKey: ['leads'] }, old =>
        old ? { ...old, items: old.items.map(l => l.id === id ? { ...l, ...data } : l) } : old
      )
      if (prevLead) qc.setQueryData<Lead>(['lead', id], { ...prevLead, ...data })

      return { prevLists, prevLead }
    },
    onError: (_err, { id }, ctx) => {
      ctx?.prevLists.forEach(([key, val]) => qc.setQueryData(key, val))
      if (ctx?.prevLead) qc.setQueryData(['lead', id], ctx.prevLead)
    },
    onSettled: (_data, _err, { id }) => {
      qc.invalidateQueries({ queryKey: ['leads'] })
      qc.invalidateQueries({ queryKey: ['lead', id] })
    },
  })
}

export const useDeleteLead = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteLead(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['leads'] }),
  })
}

export const useRevalidateLead = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => revalidateLead(id),
    onSuccess: (lead) => {
      qc.setQueryData(['lead', lead.id], lead)
      qc.invalidateQueries({ queryKey: ['leads'] })
    },
  })
}

export const useEnrichLead = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => enrichLead(id),
    onSuccess: (_, id) => {
      // Refetch after a short delay so the worker has a chance to update the lead
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ['lead', id] })
        qc.invalidateQueries({ queryKey: ['leads'] })
        qc.invalidateQueries({ queryKey: ['lead-activities', id] })
      }, 5000)
    },
  })
}

export const useLinkedinEnrichLead = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => linkedinEnrichLead(id),
    onSuccess: (_, id) => {
      // LinkedIn enrichment is slow (browser automation); refetch after a longer delay.
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ['lead', id] })
        qc.invalidateQueries({ queryKey: ['leads'] })
        qc.invalidateQueries({ queryKey: ['lead-activities', id] })
      }, 15000)
    },
  })
}

export const useAssignLead = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, userId }: { id: string; userId: string | null }) => assignLead(id, userId),
    onSuccess: (lead) => {
      qc.setQueryData(['lead', lead.id], lead)
      qc.invalidateQueries({ queryKey: ['leads'] })
      qc.invalidateQueries({ queryKey: ['lead-activities', lead.id] })
    },
  })
}

export const useLeadActivities = (id: string | null) =>
  useQuery({
    queryKey: ['lead-activities', id],
    queryFn: () => listLeadActivities(id as string),
    enabled: !!id,
  })
