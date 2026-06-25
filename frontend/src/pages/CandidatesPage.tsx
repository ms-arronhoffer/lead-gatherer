import { useEffect, useMemo, useState } from 'react'
import {
  Box, Stack, TextField, Select, MenuItem, FormControl, InputLabel,
  Button, Chip, Typography, Pagination, Table, TableHead, TableRow,
  TableCell, TableBody, TableContainer, CircularProgress, Link,
  Dialog, DialogTitle, DialogContent, DialogActions, Alert,
} from '@mui/material'
import { useHotkeys } from 'react-hotkeys-hook'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  deleteCandidate, dismissCandidate, harvestUrls, listCandidates,
  promoteCandidate, type CandidateFilters,
} from '../api/candidates'
import type { LeadCandidate } from '../types/candidate'

const STATUS_COLORS: Record<string, 'default' | 'success' | 'warning' | 'error'> = {
  pending: 'warning',
  promoted: 'success',
  dismissed: 'default',
}

export default function CandidatesPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [filters, setFilters] = useState<CandidateFilters>({
    status: 'pending', page: 1, page_size: 50,
  })
  const { data, isLoading } = useQuery({
    queryKey: ['candidates', filters],
    queryFn: () => listCandidates(filters),
  })
  const items = useMemo(() => data?.items ?? [], [data])
  const [cursorIdx, setCursorIdx] = useState(0)
  const cursor: LeadCandidate | undefined = items[cursorIdx]
  const [harvestOpen, setHarvestOpen] = useState(false)
  const [harvestErr, setHarvestErr] = useState<string | null>(null)

  useEffect(() => {
    if (cursorIdx >= items.length && items.length > 0) setCursorIdx(items.length - 1)
  }, [items.length, cursorIdx])

  const invalidate = () => qc.invalidateQueries({ queryKey: ['candidates'] })

  const promote = useMutation({
    mutationFn: (id: string) => promoteCandidate(id),
    onSuccess: (lead) => { invalidate(); navigate(`/leads/${lead.id}`) },
  })
  const dismiss = useMutation({
    mutationFn: (id: string) => dismissCandidate(id),
    onSuccess: () => invalidate(),
  })
  const remove = useMutation({
    mutationFn: (id: string) => deleteCandidate(id),
    onSuccess: () => invalidate(),
  })
  const harvest = useMutation({
    mutationFn: (q: { query: string; max_results: number }) => harvestUrls(q),
    onSuccess: () => { setHarvestOpen(false); invalidate() },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setHarvestErr(msg || 'Harvest failed')
    },
  })

  useHotkeys('j', () => setCursorIdx(i => Math.min(i + 1, items.length - 1)), [items.length])
  useHotkeys('k', () => setCursorIdx(i => Math.max(i - 1, 0)), [])
  useHotkeys('p', () => { if (cursor && cursor.status === 'pending') promote.mutate(cursor.id) }, [cursor])
  useHotkeys('d', () => { if (cursor && cursor.status === 'pending') dismiss.mutate(cursor.id) }, [cursor])
  useHotkeys('x', () => {
    if (cursor && window.confirm('Delete this candidate?')) remove.mutate(cursor.id)
  }, [cursor])

  const setFilter = (k: keyof CandidateFilters, v: unknown) =>
    setFilters(f => ({ ...f, [k]: v, page: 1 }))

  const totalPages = data ? Math.max(1, Math.ceil(data.total / (filters.page_size ?? 50))) : 1

  return (
    <Box>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
        <Typography variant="h5" sx={{ flex: 1 }}>Lead Candidates</Typography>
        <Button variant="contained" onClick={() => { setHarvestErr(null); setHarvestOpen(true) }}>
          Harvest URLs
        </Button>
      </Stack>

      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap">
        <FormControl size="small" sx={{ width: 150 }}>
          <InputLabel>Status</InputLabel>
          <Select
            value={filters.status ?? ''}
            label="Status"
            onChange={e => setFilter('status', e.target.value || undefined)}
          >
            <MenuItem value="">All</MenuItem>
            <MenuItem value="pending">Pending</MenuItem>
            <MenuItem value="promoted">Promoted</MenuItem>
            <MenuItem value="dismissed">Dismissed</MenuItem>
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ width: 180 }}>
          <InputLabel>Source</InputLabel>
          <Select
            value={filters.source ?? ''}
            label="Source"
            onChange={e => setFilter('source', e.target.value || undefined)}
          >
            <MenuItem value="">All</MenuItem>
            <MenuItem value="url_harvester">URL Harvester</MenuItem>
            <MenuItem value="visitor_pixel">Visitor Pixel</MenuItem>
            <MenuItem value="manual">Manual</MenuItem>
          </Select>
        </FormControl>
        <TextField
          label="Min fit"
          type="number"
          size="small"
          value={filters.min_fit ?? ''}
          onChange={e => setFilter('min_fit', e.target.value === '' ? undefined : Number(e.target.value))}
          sx={{ width: 100 }}
        />
      </Stack>

      {isLoading && <CircularProgress size={24} />}

      {data && (
        <>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {data.total} candidates · j/k to walk · p to promote · d to dismiss · x to delete
          </Typography>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Company</TableCell>
                  <TableCell>Source</TableCell>
                  <TableCell>Category</TableCell>
                  <TableCell>Website</TableCell>
                  <TableCell>Fit</TableCell>
                  <TableCell>Summary</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {items.map((c, idx) => (
                  <TableRow
                    key={c.id}
                    hover
                    onClick={() => setCursorIdx(idx)}
                    sx={{
                      cursor: 'pointer',
                      outline: idx === cursorIdx ? '2px solid' : 'none',
                      outlineColor: 'primary.main',
                      outlineOffset: '-2px',
                    }}
                  >
                    <TableCell>{c.company_name}</TableCell>
                    <TableCell>{c.source}</TableCell>
                    <TableCell>{c.category}</TableCell>
                    <TableCell onClick={e => e.stopPropagation()}>
                      {c.website && (
                        <Link href={c.website} target="_blank" rel="noreferrer" underline="hover">
                          {hostname(c.website)}
                        </Link>
                      )}
                    </TableCell>
                    <TableCell>
                      {c.llm_fit_score !== null && (
                        <Chip
                          label={c.llm_fit_score}
                          size="small"
                          color={c.llm_fit_score >= 70 ? 'success' : c.llm_fit_score >= 40 ? 'warning' : 'default'}
                        />
                      )}
                    </TableCell>
                    <TableCell sx={{ maxWidth: 280 }}>
                      <Typography variant="caption" sx={{
                        display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                        overflow: 'hidden',
                      }}>
                        {c.llm_summary}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip label={c.status} size="small" color={STATUS_COLORS[c.status] ?? 'default'} />
                    </TableCell>
                    <TableCell onClick={e => e.stopPropagation()}>
                      {c.status === 'pending' && (
                        <Stack direction="row" spacing={0.5}>
                          <Button size="small" onClick={() => promote.mutate(c.id)}>Promote</Button>
                          <Button size="small" color="warning" onClick={() => dismiss.mutate(c.id)}>Dismiss</Button>
                        </Stack>
                      )}
                      {c.status === 'promoted' && c.promoted_lead_id && (
                        <Button size="small" onClick={() => navigate(`/leads/${c.promoted_lead_id}`)}>
                          View Lead
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
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

      <HarvestDialog
        open={harvestOpen}
        onClose={() => setHarvestOpen(false)}
        onSubmit={(query, max_results) => harvest.mutate({ query, max_results })}
        loading={harvest.isPending}
        error={harvestErr}
      />
    </Box>
  )
}

function HarvestDialog({
  open, onClose, onSubmit, loading, error,
}: {
  open: boolean
  onClose: () => void
  onSubmit: (query: string, maxResults: number) => void
  loading: boolean
  error: string | null
}) {
  const [query, setQuery] = useState('')
  const [maxResults, setMaxResults] = useState(25)
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Harvest URLs into Candidates</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField
            label="Search query"
            placeholder="e.g. B2B observability vendors under 50 employees"
            value={query}
            onChange={e => setQuery(e.target.value)}
            autoFocus
            fullWidth
          />
          <TextField
            label="Max results"
            type="number"
            value={maxResults}
            onChange={e => setMaxResults(Math.max(1, Math.min(100, Number(e.target.value) || 25)))}
            sx={{ width: 140 }}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          disabled={!query.trim() || loading}
          onClick={() => onSubmit(query.trim(), maxResults)}
        >
          {loading ? 'Harvesting…' : 'Harvest'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

function hostname(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, '') } catch { return url }
}
