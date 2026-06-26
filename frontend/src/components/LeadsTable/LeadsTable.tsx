import { useEffect, useMemo, useState } from 'react'
import {
  Avatar, Box, Stack, TextField, Select, MenuItem, FormControl, InputLabel,
  Button, Chip, Typography, Pagination, Link, Table, TableHead,
  TableRow, TableCell, TableBody, TableSortLabel, TableContainer, CircularProgress,
  Checkbox, IconButton, Tooltip, Dialog, DialogTitle, DialogContent, DialogActions, Alert,
} from '@mui/material'
import DownloadIcon from '@mui/icons-material/Download'
import DeleteIcon from '@mui/icons-material/Delete'
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep'
import KeyboardIcon from '@mui/icons-material/Keyboard'
import OutboxIcon from '@mui/icons-material/Outbox'
import { useSearchParams } from 'react-router-dom'
import { useHotkeys } from 'react-hotkeys-hook'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useLeads, useUpdateLead, useDeleteLead } from '../../hooks/useLeads'
import { exportLeadsCsv } from '../../api/leads'
import { listSequences, bulkEnroll } from '../../api/sequences'
import LeadDetailDrawer from '../LeadDetailDrawer/LeadDetailDrawer'
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
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedId = searchParams.get('selected')

  const [filters, setFilters] = useState<LeadFilters>({
    page: 1,
    page_size: 50,
    sort_by: 'created_at',
    sort_dir: 'desc',
  })

  const { data, isLoading } = useLeads(filters)
  const { mutate: updateLead } = useUpdateLead()
  const { mutate: deleteLead } = useDeleteLead()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [helpOpen, setHelpOpen] = useState(false)
  const [enrollOpen, setEnrollOpen] = useState(false)
  const [enrollSequenceId, setEnrollSequenceId] = useState<string>('')
  const [enrollMsg, setEnrollMsg] = useState<string | null>(null)
  const [cursorIdx, setCursorIdx] = useState(0)
  const sequencesQ = useQuery({ queryKey: ['sequences'], queryFn: listSequences, enabled: enrollOpen })
  const enrollMut = useMutation({
    mutationFn: (sequence_id: string) => bulkEnroll(sequence_id, { sequence_id, lead_ids: Array.from(selected) }),
    onSuccess: (r) => { setEnrollMsg(`Enrolled ${r.enrolled}, skipped ${r.skipped}.`); setSelected(new Set()) },
    onError: (e: Error) => setEnrollMsg(e.message),
  })

  const items = useMemo(() => data?.items ?? [], [data])
  const cursorLead: Lead | undefined = items[cursorIdx]

  useEffect(() => {
    if (cursorIdx >= items.length && items.length > 0) setCursorIdx(items.length - 1)
  }, [items.length, cursorIdx])

  const setFilter = (key: keyof LeadFilters, value: unknown) =>
    setFilters(f => ({ ...f, [key]: value, page: 1 }))

  const openLead = (id: string) =>
    setSearchParams(prev => { const p = new URLSearchParams(prev); p.set('selected', id); return p })

  const closeLead = () =>
    setSearchParams(prev => { const p = new URLSearchParams(prev); p.delete('selected'); return p })

  const toggleSelect = (id: string) =>
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const toggleSelectAll = (ids: string[]) =>
    setSelected(prev => {
      const allChecked = ids.every(i => prev.has(i))
      const next = new Set(prev)
      if (allChecked) ids.forEach(i => next.delete(i))
      else ids.forEach(i => next.add(i))
      return next
    })

  const deleteOne = (id: string) => {
    if (!window.confirm('Delete this lead permanently?')) return
    deleteLead(id)
    setSelected(prev => {
      const next = new Set(prev)
      next.delete(id)
      return next
    })
  }

  const deleteSelected = () => {
    if (selected.size === 0) return
    if (!window.confirm(`Delete ${selected.size} lead(s) permanently?`)) return
    selected.forEach(id => deleteLead(id))
    setSelected(new Set())
  }

  const toggleSort = (col: string) => {
    if (filters.sort_by === col) {
      setFilters(f => ({ ...f, sort_dir: f.sort_dir === 'desc' ? 'asc' : 'desc' }))
    } else {
      setFilters(f => ({ ...f, sort_by: col, sort_dir: 'desc' }))
    }
  }

  const setStatus = (id: string | undefined, status: LeadStatus) => {
    if (!id) return
    updateLead({ id, data: { status } })
  }

  useHotkeys('j', () => setCursorIdx(i => Math.min(i + 1, items.length - 1)), [items.length])
  useHotkeys('k', () => setCursorIdx(i => Math.max(i - 1, 0)), [])
  useHotkeys('enter', () => { if (cursorLead) openLead(cursorLead.id) }, [cursorLead])
  useHotkeys('escape', () => { if (selectedId) closeLead() }, [selectedId])
  useHotkeys('x', () => { if (cursorLead) toggleSelect(cursorLead.id) }, [cursorLead])
  useHotkeys('c', () => setStatus(cursorLead?.id, 'contacted'), [cursorLead])
  useHotkeys('q', () => setStatus(cursorLead?.id, 'qualified'), [cursorLead])
  useHotkeys('r', () => setStatus(cursorLead?.id, 'rejected'), [cursorLead])
  useHotkeys('n', () => setStatus(cursorLead?.id, 'new'), [cursorLead])
  useHotkeys('e', () => { if (cursorLead) openLead(cursorLead.id) }, [cursorLead])
  useHotkeys('/', e => { e.preventDefault(); (document.getElementById('lead-search-input') as HTMLInputElement | null)?.focus() })
  useHotkeys('shift+/', () => setHelpOpen(o => !o))

  const totalPages = data ? Math.ceil(data.total / (filters.page_size ?? 50)) : 1

  return (
    <Box>
      {/* Filter bar */}
      <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: 'wrap' }}>
        <TextField
          id="lead-search-input"
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
        <TextField
          label="Min score"
          type="number"
          size="small"
          value={filters.min_score ?? ''}
          onChange={e => setFilter('min_score', e.target.value === '' ? undefined : Number(e.target.value))}
          sx={{ width: 100 }}
        />
        <TextField
          label="Max score"
          type="number"
          size="small"
          value={filters.max_score ?? ''}
          onChange={e => setFilter('max_score', e.target.value === '' ? undefined : Number(e.target.value))}
          sx={{ width: 100 }}
        />
        <Box sx={{ flex: 1 }} />
        <Tooltip title="Keyboard shortcuts (?)">
          <IconButton onClick={() => setHelpOpen(true)}><KeyboardIcon /></IconButton>
        </Tooltip>
        {selected.size > 0 && (
          <Button
            variant="outlined"
            color="error"
            startIcon={<DeleteSweepIcon />}
            onClick={deleteSelected}
          >
            Delete {selected.size}
          </Button>
        )}
        {selected.size > 0 && (
          <Button
            variant="outlined"
            startIcon={<OutboxIcon />}
            onClick={() => { setEnrollMsg(null); setEnrollSequenceId(''); setEnrollOpen(true) }}
          >
            Enroll {selected.size}
          </Button>
        )}
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
            {data.total} leads · use ↑/↓ row hint: j/k to walk, c/q/r/n to set status, enter to open
          </Typography>
          <TableContainer sx={{ width: '100%' }}>
            <Table size="small">
              <TableHead>
              <TableRow>
                <TableCell padding="checkbox">
                  <Checkbox
                    indeterminate={
                      items.some(l => selected.has(l.id)) &&
                      !items.every(l => selected.has(l.id))
                    }
                    checked={items.length > 0 && items.every(l => selected.has(l.id))}
                    onChange={() => toggleSelectAll(items.map(l => l.id))}
                  />
                </TableCell>
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
                <TableCell>
                  <TableSortLabel
                    active={filters.sort_by === 'score'}
                    direction={filters.sort_by === 'score' ? filters.sort_dir as 'asc' | 'desc' : 'desc'}
                    onClick={() => toggleSort('score')}
                  >
                    Score
                  </TableSortLabel>
                </TableCell>
                <TableCell>Phone</TableCell>
                <TableCell>Emails</TableCell>
                <TableCell>Website</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Assignee</TableCell>
                <TableCell padding="checkbox" />
              </TableRow>
            </TableHead>
            <TableBody>
              {items.map((lead, idx) => (
                <LeadRow
                  key={lead.id}
                  lead={lead}
                  selected={selected.has(lead.id)}
                  cursor={idx === cursorIdx}
                  onClick={() => { setCursorIdx(idx); openLead(lead.id) }}
                  onToggleSelect={toggleSelect}
                  onStatusChange={(id, status) => updateLead({ id, data: { status } })}
                  onDelete={deleteOne}
                />
              ))}
            </TableBody>
          </Table>
          </TableContainer>
          <Box sx={{ mt: 2, display: 'flex', justifyContent: 'center' }}>
            <Pagination
              count={totalPages}
              page={filters.page ?? 1}
              onChange={(_, p) => setFilters(f => ({ ...f, page: p }))}
            />
          </Box>
        </>
      )}

      <LeadDetailDrawer leadId={selectedId} onClose={closeLead} />
      <ShortcutHelp open={helpOpen} onClose={() => setHelpOpen(false)} />
      <Dialog open={enrollOpen} onClose={() => setEnrollOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Enroll {selected.size} lead{selected.size === 1 ? '' : 's'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {enrollMsg && <Alert severity="info">{enrollMsg}</Alert>}
            <FormControl fullWidth size="small">
              <InputLabel>Sequence</InputLabel>
              <Select label="Sequence" value={enrollSequenceId} onChange={(e) => setEnrollSequenceId(String(e.target.value))}>
                {(sequencesQ.data ?? []).filter(s => s.enabled).map(s => (
                  <MenuItem key={s.id} value={s.id}>{s.name} ({s.steps.length} steps)</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEnrollOpen(false)}>Close</Button>
          <Button variant="contained" disabled={!enrollSequenceId || enrollMut.isPending}
            onClick={() => enrollMut.mutate(enrollSequenceId)}>
            {enrollMut.isPending ? 'Enrolling…' : 'Enroll'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

function LeadRow({
  lead, selected, cursor, onClick, onToggleSelect, onStatusChange, onDelete,
}: {
  lead: Lead
  selected: boolean
  cursor: boolean
  onClick: () => void
  onToggleSelect: (id: string) => void
  onStatusChange: (id: string, s: LeadStatus) => void
  onDelete: (id: string) => void
}) {
  const stop = (e: React.MouseEvent) => e.stopPropagation()
  return (
    <TableRow
      hover
      selected={selected}
      onClick={onClick}
      sx={{
        cursor: 'pointer',
        outline: cursor ? '2px solid' : 'none',
        outlineColor: 'primary.main',
        outlineOffset: '-2px',
      }}
    >
      <TableCell padding="checkbox" onClick={stop}>
        <Checkbox checked={selected} onChange={() => onToggleSelect(lead.id)} />
      </TableCell>
      <TableCell>{lead.name}</TableCell>
      <TableCell>{lead.city}</TableCell>
      <TableCell>{lead.state}</TableCell>
      <TableCell><ScoreBadge score={lead.score ?? null} /></TableCell>
      <TableCell>{lead.phone}</TableCell>
      <TableCell onClick={stop}>
        <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }}>
          {lead.emails.slice(0, 2).map(e => (
            <Chip key={e.id} label={e.email} size="small" variant="outlined" />
          ))}
          {lead.emails.length > 2 && <Chip label={`+${lead.emails.length - 2}`} size="small" />}
        </Stack>
      </TableCell>
      <TableCell onClick={stop}>
        {lead.website && (
          <Link href={lead.website} target="_blank" rel="noreferrer" underline="hover">
            {new URL(lead.website).hostname.replace('www.', '')}
          </Link>
        )}
      </TableCell>
      <TableCell onClick={stop}>
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
      <TableCell>
        <AssigneeCell lead={lead} />
      </TableCell>
      <TableCell padding="checkbox" onClick={stop}>
        <Tooltip title="Delete lead">
          <IconButton size="small" color="error" onClick={() => onDelete(lead.id)}>
            <DeleteIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </TableCell>
    </TableRow>
  )
}

function AssigneeCell({ lead }: { lead: Lead }) {
  const assignee = lead.assignee
  const touchedBy = lead.last_touched_by
  if (!assignee && !touchedBy) {
    return <Typography variant="caption" color="text.secondary">—</Typography>
  }
  const name = (u: { display_name: string | null; email: string }) => u.display_name || u.email
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', minWidth: 0 }}>
      {assignee ? (
        <Tooltip title={`Assigned to ${name(assignee)}`}>
          <Avatar sx={{ width: 24, height: 24, fontSize: 11, bgcolor: 'primary.dark' }}>
            {initials(name(assignee))}
          </Avatar>
        </Tooltip>
      ) : (
        <Avatar sx={{ width: 24, height: 24, fontSize: 11, bgcolor: 'grey.400' }}>—</Avatar>
      )}
      {touchedBy && lead.last_touched_at && (
        <Typography variant="caption" color="text.secondary" noWrap>
          {name(touchedBy)} · {timeAgo(lead.last_touched_at)}
        </Typography>
      )}
    </Stack>
  )
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null || score === undefined) {
    return <Typography variant="caption" color="text.secondary">—</Typography>
  }
  const color: 'success' | 'warning' | 'default' =
    score >= 70 ? 'success' : score >= 40 ? 'warning' : 'default'
  return <Chip label={score} size="small" color={color} variant="filled" />
}

function initials(base: string): string {
  const parts = base.trim().split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return base.slice(0, 2).toUpperCase()
}

function timeAgo(ts: number): string {
  const sec = Math.max(0, Math.floor(Date.now() / 1000 - ts))
  if (sec < 60) return `${sec}s ago`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  const d = Math.floor(hr / 24)
  if (d < 30) return `${d}d ago`
  const mo = Math.floor(d / 30)
  if (mo < 12) return `${mo}mo ago`
  return `${Math.floor(mo / 12)}y ago`
}

function ShortcutHelp({ open, onClose }: { open: boolean; onClose: () => void }) {
  const rows: [string, string][] = [
    ['j / k', 'Next / previous row'],
    ['enter or e', 'Open lead detail'],
    ['escape', 'Close detail'],
    ['x', 'Toggle row selection'],
    ['c', 'Mark contacted'],
    ['q', 'Mark qualified'],
    ['r', 'Mark rejected'],
    ['n', 'Mark new'],
    ['/', 'Focus search'],
    ['?', 'Show / hide this help'],
  ]
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Keyboard Shortcuts</DialogTitle>
      <DialogContent>
        <Table size="small">
          <TableBody>
            {rows.map(([k, d]) => (
              <TableRow key={k}>
                <TableCell sx={{ width: 100, fontFamily: 'monospace' }}>{k}</TableCell>
                <TableCell>{d}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </DialogContent>
    </Dialog>
  )
}
