import { useState } from 'react'
import {
  Box, Stack, TextField, Select, MenuItem, FormControl, InputLabel,
  Button, Chip, Typography, Pagination, Link, Table, TableHead,
  TableRow, TableCell, TableBody, TableSortLabel, CircularProgress,
} from '@mui/material'
import DownloadIcon from '@mui/icons-material/Download'
import { useLeads, useUpdateLead } from '../../hooks/useLeads'
import { exportLeadsCsv } from '../../api/leads'
import type { Lead, LeadStatus } from '../../types/lead'
import type { LeadFilters } from '../../api/leads'

const STATUS_COLORS: Record<LeadStatus, 'default' | 'primary' | 'success' | 'error'> = {
  new: 'default',
  contacted: 'primary',
  qualified: 'success',
  rejected: 'error',
}

const STATUSES: LeadStatus[] = ['new', 'contacted', 'qualified', 'rejected']

export default function LeadsTable() {
  const [filters, setFilters] = useState<LeadFilters>({
    page: 1,
    page_size: 50,
    sort_by: 'created_at',
    sort_dir: 'desc',
  })

  const { data, isLoading } = useLeads(filters)
  const { mutate: updateLead } = useUpdateLead()

  const setFilter = (key: keyof LeadFilters, value: unknown) =>
    setFilters(f => ({ ...f, [key]: value, page: 1 }))

  const toggleSort = (col: string) => {
    if (filters.sort_by === col) {
      setFilters(f => ({ ...f, sort_dir: f.sort_dir === 'desc' ? 'asc' : 'desc' }))
    } else {
      setFilters(f => ({ ...f, sort_by: col, sort_dir: 'desc' }))
    }
  }

  const totalPages = data ? Math.ceil(data.total / (filters.page_size ?? 50)) : 1

  return (
    <Box>
      {/* Filter bar */}
      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap">
        <TextField
          label="Search name"
          size="small"
          value={filters.search ?? ''}
          onChange={e => setFilter('search', e.target.value || undefined)}
          sx={{ width: 200 }}
        />
        <FormControl size="small" sx={{ width: 140 }}>
          <InputLabel>Status</InputLabel>
          <Select
            value={filters.status ?? ''}
            label="Status"
            onChange={e => setFilter('status', e.target.value || undefined)}
          >
            <MenuItem value="">All</MenuItem>
            {STATUSES.map(s => <MenuItem key={s} value={s}>{s}</MenuItem>)}
          </Select>
        </FormControl>
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
        <Box sx={{ flex: 1 }} />
        <Button
          variant="outlined"
          startIcon={<DownloadIcon />}
          onClick={() => exportLeadsCsv(filters)}
        >
          Export CSV
        </Button>
      </Stack>

      {isLoading && <CircularProgress size={24} />}

      {data && (
        <>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {data.total} leads
          </Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                {['name', 'city', 'state'].map(col => (
                  <TableCell key={col}>
                    <TableSortLabel
                      active={filters.sort_by === col}
                      direction={filters.sort_by === col ? filters.sort_dir as 'asc' | 'desc' : 'asc'}
                      onClick={() => toggleSort(col)}
                    >
                      {col.charAt(0).toUpperCase() + col.slice(1)}
                    </TableSortLabel>
                  </TableCell>
                ))}
                <TableCell>Phone</TableCell>
                <TableCell>Emails</TableCell>
                <TableCell>Website</TableCell>
                <TableCell>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.items.map(lead => (
                <LeadRow key={lead.id} lead={lead} onStatusChange={(id, status) =>
                  updateLead({ id, data: { status } })
                } />
              ))}
            </TableBody>
          </Table>
          <Box sx={{ mt: 2, display: 'flex', justifyContent: 'center' }}>
            <Pagination
              count={totalPages}
              page={filters.page ?? 1}
              onChange={(_, p) => setFilters(f => ({ ...f, page: p }))}
            />
          </Box>
        </>
      )}
    </Box>
  )
}

function LeadRow({ lead, onStatusChange }: { lead: Lead; onStatusChange: (id: string, s: LeadStatus) => void }) {
  return (
    <TableRow hover>
      <TableCell>{lead.name}</TableCell>
      <TableCell>{lead.city}</TableCell>
      <TableCell>{lead.state}</TableCell>
      <TableCell>{lead.phone}</TableCell>
      <TableCell>
        <Stack direction="row" spacing={0.5} flexWrap="wrap">
          {lead.emails.slice(0, 2).map(e => (
            <Chip key={e.id} label={e.email} size="small" variant="outlined" />
          ))}
          {lead.emails.length > 2 && <Chip label={`+${lead.emails.length - 2}`} size="small" />}
        </Stack>
      </TableCell>
      <TableCell>
        {lead.website && (
          <Link href={lead.website} target="_blank" rel="noreferrer" underline="hover">
            {new URL(lead.website).hostname.replace('www.', '')}
          </Link>
        )}
      </TableCell>
      <TableCell>
        <Select
          value={lead.status}
          size="small"
          variant="standard"
          onChange={e => onStatusChange(lead.id, e.target.value as LeadStatus)}
          renderValue={(v) => (
            <Chip label={v} size="small" color={STATUS_COLORS[v as LeadStatus]} />
          )}
        >
          {STATUSES.map(s => <MenuItem key={s} value={s}>{s}</MenuItem>)}
        </Select>
      </TableCell>
    </TableRow>
  )
}
