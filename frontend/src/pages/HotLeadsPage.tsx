import { useMemo, useState } from 'react'
import {
  Box, Card, CardContent, Chip, CircularProgress, Divider, Link, Slider, Stack,
  Table, TableBody, TableCell, TableHead, TableRow, Tooltip, Typography,
} from '@mui/material'
import WhatshotIcon from '@mui/icons-material/Whatshot'
import { Link as RouterLink } from 'react-router-dom'
import { HOT_LEAD_THRESHOLD, useHotLeads, useSignalMetrics } from '../hooks/useLeads'
import type { Lead, LeadSignal } from '../types/lead'

const STATUS_COLORS: Record<string, 'default' | 'primary' | 'success' | 'error'> = {
  new: 'default',
  contacted: 'primary',
  qualified: 'success',
  rejected: 'error',
}

function fmtAgo(ts?: number | null): string {
  if (!ts) return '—'
  const secs = Math.max(0, Math.floor(Date.now() / 1000) - ts)
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`
  return `${Math.floor(secs / 86400)}d ago`
}

function ScorePill({ label, value, color }: { label: string; value?: number | null; color: string }) {
  return (
    <Tooltip title={label}>
      <Box
        sx={{
          px: 1, py: 0.25, borderRadius: 1, minWidth: 44, textAlign: 'center',
          bgcolor: color, color: '#fff', fontSize: 12, fontWeight: 600,
        }}
      >
        {value ?? 0}
      </Box>
    </Tooltip>
  )
}

function topSignals(signals: LeadSignal[], limit = 4): LeadSignal[] {
  return [...signals]
    .sort((a, b) => (b.strength ?? 0) - (a.strength ?? 0))
    .slice(0, limit)
}

function HotLeadCard({ lead }: { lead: Lead }) {
  const signals = topSignals(lead.signals ?? [])
  const place = [lead.city, lead.state].filter(Boolean).join(', ')
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'flex-start' }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
              <Link component={RouterLink} to={`/leads/${lead.id}`} variant="subtitle1" sx={{ fontWeight: 600 }}>
                {lead.name}
              </Link>
              <Chip
                label={lead.status}
                size="small"
                color={STATUS_COLORS[lead.status] ?? 'default'}
              />
            </Stack>
            {place && (
              <Typography variant="body2" color="text.secondary">{place}</Typography>
            )}
            <Stack direction="row" spacing={0.5} sx={{ mt: 1, flexWrap: 'wrap' }}>
              {signals.length === 0 && (
                <Typography variant="caption" color="text.secondary">No buying signals yet</Typography>
              )}
              {signals.map(s => (
                <Tooltip key={s.id} title={`${s.source} · strength ${s.strength} · ${fmtAgo(s.detected_at)}`}>
                  <Chip label={s.type} size="small" variant="outlined" color="warning" />
                </Tooltip>
              ))}
            </Stack>
          </Box>
          <Stack spacing={0.5} sx={{ alignItems: 'flex-end' }}>
            <ScorePill label="Priority score" value={lead.priority_score} color="#d32f2f" />
            <Stack direction="row" spacing={0.5}>
              <ScorePill label="Fit score" value={lead.fit_score} color="#1976d2" />
              <ScorePill label="Intent score" value={lead.intent_score} color="#ed6c02" />
            </Stack>
            <Typography variant="caption" color="text.secondary">
              {fmtAgo(lead.last_touched_at ?? lead.created_at)}
            </Typography>
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  )
}

function SignalMetricsPanel() {
  const { data, isLoading } = useSignalMetrics()
  const rows = data?.signal_types ?? []
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }} gutterBottom>
          Signal precision
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          Which buying signals actually predict pipeline.
        </Typography>
        {isLoading ? (
          <CircularProgress size={20} />
        ) : rows.length === 0 ? (
          <Typography variant="body2" color="text.secondary">No signals recorded yet.</Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Signal</TableCell>
                <TableCell align="right">Leads</TableCell>
                <TableCell align="right">Contacted</TableCell>
                <TableCell align="right">Qualified</TableCell>
                <TableCell align="right">Qual. rate</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map(m => (
                <TableRow key={m.type}>
                  <TableCell>{m.type}</TableCell>
                  <TableCell align="right">{m.leads}</TableCell>
                  <TableCell align="right">{m.contacted}</TableCell>
                  <TableCell align="right">{m.qualified}</TableCell>
                  <TableCell align="right">{(m.qualified_rate * 100).toFixed(0)}%</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

export default function HotLeadsPage() {
  const [threshold, setThreshold] = useState(HOT_LEAD_THRESHOLD)
  const { data, isLoading, isFetching } = useHotLeads(threshold)
  const leads = useMemo(() => data?.items ?? [], [data])

  return (
    <Box>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1 }}>
        <WhatshotIcon color="error" />
        <Typography variant="h5">Hot Leads</Typography>
        {isFetching && <CircularProgress size={18} />}
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Live feed of the highest-priority leads, ranked by priority score (fit × intent, freshness-decayed).
        Auto-refreshes every 30s.
      </Typography>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ alignItems: 'flex-start' }}>
        <Box sx={{ flex: 2, minWidth: 0, width: '100%' }}>
          <Box sx={{ maxWidth: 320, mb: 2 }}>
            <Typography variant="caption" color="text.secondary">
              Minimum priority score: {threshold}
            </Typography>
            <Slider
              value={threshold}
              min={0}
              max={100}
              step={5}
              valueLabelDisplay="auto"
              onChange={(_e, v) => setThreshold(v as number)}
            />
          </Box>

          {isLoading ? (
            <CircularProgress />
          ) : leads.length === 0 ? (
            <Typography color="text.secondary">
              No leads at or above a priority score of {threshold}. Lower the threshold or wait for new buying signals.
            </Typography>
          ) : (
            <Stack spacing={1.5}>
              <Typography variant="body2" color="text.secondary">
                {data?.total ?? leads.length} hot lead{(data?.total ?? leads.length) === 1 ? '' : 's'}
              </Typography>
              {leads.map(lead => <HotLeadCard key={lead.id} lead={lead} />)}
            </Stack>
          )}
        </Box>

        <Box sx={{ flex: 1, minWidth: 0, width: '100%', position: { md: 'sticky' }, top: 16 }}>
          <SignalMetricsPanel />
          <Divider sx={{ my: 2 }} />
          <Typography variant="caption" color="text.secondary">
            Tune segment weights from the Segments page to feed better fit signal into these scores.
          </Typography>
        </Box>
      </Stack>
    </Box>
  )
}
