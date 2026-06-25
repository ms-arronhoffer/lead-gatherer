import { useMemo, useState } from 'react'
import {
  Avatar, Box, Card, CardContent, Chip, CircularProgress, FormControl,
  InputLabel, MenuItem, Select, Stack, TextField, Tooltip, Typography,
} from '@mui/material'
import {
  DndContext, PointerSensor, useSensor, useSensors,
  useDraggable, useDroppable, type DragEndEvent,
} from '@dnd-kit/core'
import { useLeads, useUpdateLead } from '../hooks/useLeads'
import type { Lead, LeadStatus } from '../types/lead'
import type { LeadFilters } from '../api/leads'

const COLUMNS: { status: LeadStatus; label: string; color: 'default' | 'primary' | 'success' | 'error' }[] = [
  { status: 'new', label: 'New', color: 'default' },
  { status: 'contacted', label: 'Contacted', color: 'primary' },
  { status: 'qualified', label: 'Qualified', color: 'success' },
  { status: 'rejected', label: 'Rejected', color: 'error' },
]

export default function KanbanPage() {
  const [filters, setFilters] = useState<LeadFilters>({
    page: 1,
    page_size: 200,
    sort_by: 'score',
    sort_dir: 'desc',
  })
  const { data, isLoading } = useLeads(filters)
  const { mutate: updateLead } = useUpdateLead()

  // Require small movement before activating drag so card clicks still work cleanly.
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }))

  const setFilter = (key: keyof LeadFilters, value: unknown) =>
    setFilters(f => ({ ...f, [key]: value, page: 1 }))

  const grouped = useMemo(() => {
    const out: Record<LeadStatus, Lead[]> = { new: [], contacted: [], qualified: [], rejected: [] }
    for (const l of data?.items ?? []) out[l.status].push(l)
    return out
  }, [data])

  const onDragEnd = (e: DragEndEvent) => {
    const { active, over } = e
    if (!over) return
    const fromStatus = active.data.current?.status as LeadStatus | undefined
    const toStatus = over.id as LeadStatus
    if (!fromStatus || fromStatus === toStatus) return
    updateLead({ id: String(active.id), data: { status: toStatus } })
  }

  return (
    <Box>
      <Typography variant="h5" sx={{ mb: 2 }}>Lead Triage Board</Typography>

      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap">
        <TextField
          label="Search name"
          size="small"
          value={filters.search ?? ''}
          onChange={e => setFilter('search', e.target.value || undefined)}
          sx={{ width: 200 }}
        />
        <TextField
          label="City"
          size="small"
          value={filters.city ?? ''}
          onChange={e => setFilter('city', e.target.value || undefined)}
          sx={{ width: 140 }}
        />
        <TextField
          label="State"
          size="small"
          value={filters.state ?? ''}
          onChange={e => setFilter('state', e.target.value || undefined)}
          sx={{ width: 80 }}
        />
        <FormControl size="small" sx={{ width: 140 }}>
          <InputLabel>Has Email</InputLabel>
          <Select
            value={filters.has_email === undefined ? '' : String(filters.has_email)}
            label="Has Email"
            onChange={e => setFilter('has_email', e.target.value === '' ? undefined : e.target.value === 'true')}
          >
            <MenuItem value="">Any</MenuItem>
            <MenuItem value="true">Yes</MenuItem>
            <MenuItem value="false">No</MenuItem>
          </Select>
        </FormControl>
        <TextField
          label="Min score"
          type="number"
          size="small"
          value={filters.min_score ?? ''}
          onChange={e => setFilter('min_score', e.target.value === '' ? undefined : Number(e.target.value))}
          sx={{ width: 110 }}
        />
      </Stack>

      {isLoading && <CircularProgress size={24} />}

      <DndContext sensors={sensors} onDragEnd={onDragEnd}>
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 2, alignItems: 'start' }}>
          {COLUMNS.map(col => (
            <Column
              key={col.status}
              status={col.status}
              label={col.label}
              color={col.color}
              leads={grouped[col.status]}
            />
          ))}
        </Box>
      </DndContext>
    </Box>
  )
}

function Column({
  status, label, color, leads,
}: {
  status: LeadStatus
  label: string
  color: 'default' | 'primary' | 'success' | 'error'
  leads: Lead[]
}) {
  const { isOver, setNodeRef } = useDroppable({ id: status })

  return (
    <Box
      ref={setNodeRef}
      sx={{
        bgcolor: isOver ? 'action.hover' : 'background.default',
        border: '1px dashed',
        borderColor: isOver ? 'primary.main' : 'divider',
        borderRadius: 1,
        p: 1,
        minHeight: 200,
      }}
    >
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <Chip label={label} size="small" color={color} />
        <Typography variant="caption" color="text.secondary">{leads.length}</Typography>
      </Stack>
      <Stack spacing={1}>
        {leads.map(lead => <LeadCard key={lead.id} lead={lead} />)}
      </Stack>
    </Box>
  )
}

function LeadCard({ lead }: { lead: Lead }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: lead.id,
    data: { status: lead.status },
  })
  const style: React.CSSProperties = {
    transform: transform ? `translate3d(${transform.x}px, ${transform.y}px, 0)` : undefined,
    opacity: isDragging ? 0.5 : 1,
    cursor: isDragging ? 'grabbing' : 'grab',
    touchAction: 'none',
  }

  return (
    <Card
      ref={setNodeRef}
      variant="outlined"
      style={style}
      {...listeners}
      {...attributes}
    >
      <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
          <Typography variant="body2" sx={{ flex: 1, fontWeight: 500 }} noWrap>
            {lead.name}
          </Typography>
          {lead.score !== null && lead.score !== undefined && (
            <Chip
              label={lead.score}
              size="small"
              color={lead.score >= 70 ? 'success' : lead.score >= 40 ? 'warning' : 'default'}
            />
          )}
        </Stack>
        <Typography variant="caption" color="text.secondary" noWrap display="block">
          {[lead.city, lead.state].filter(Boolean).join(', ') || '—'}
        </Typography>
        <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mt: 0.5 }}>
          {lead.emails.length > 0 && (
            <Chip label={`${lead.emails.length} email${lead.emails.length === 1 ? '' : 's'}`} size="small" variant="outlined" />
          )}
          <Box sx={{ flex: 1 }} />
          {lead.assignee && (
            <Tooltip title={lead.assignee.display_name || lead.assignee.email}>
              <Avatar sx={{ width: 22, height: 22, fontSize: 10, bgcolor: 'primary.dark' }}>
                {initials(lead.assignee.display_name || lead.assignee.email)}
              </Avatar>
            </Tooltip>
          )}
        </Stack>
      </CardContent>
    </Card>
  )
}

function initials(base: string): string {
  const parts = base.trim().split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return base.slice(0, 2).toUpperCase()
}
