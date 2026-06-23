import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listLeads, updateLead, deleteLead } from '../api/leads'
import type { LeadFilters } from '../api/leads'
import type { LeadUpdate } from '../types/lead'

export const useLeads = (filters: LeadFilters) =>
  useQuery({
    queryKey: ['leads', filters],
    queryFn: () => listLeads(filters),
  })

export const useUpdateLead = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: LeadUpdate }) => updateLead(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['leads'] }),
  })
}

export const useDeleteLead = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteLead(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['leads'] }),
  })
}
