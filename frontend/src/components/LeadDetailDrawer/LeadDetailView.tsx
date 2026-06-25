import { useEffect, useRef, useState } from 'react'
import {
  Box, Typography, Chip, Divider, TextField, Link, CircularProgress,
  Tooltip, Button, MenuItem, Avatar, Autocomplete,
} from '@mui/material'
import VerifiedIcon from '@mui/icons-material/Verified'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlineOutlined'
import RefreshIcon from '@mui/icons-material/Refresh'
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh'
import { useLead, useUpdateLead, useRevalidateLead, useEnrichLead, useAssignLead, useLeadActivities } from '../../hooks/useLeads'
import { useUsers } from '../../hooks/useMe'
import { useTags, useSetLeadTags } from '../../hooks/useTags'
import type { LeadActivity, LeadEmail, LeadStatus, LeadUpdate } from '../../types/lead'
import type { TagDetail } from '../../types/tag'

const STATUS_COLORS: Record<LeadStatus, 'default' | 'primary' | 'success' | 'error'> = {
  new: 'default',
  contacted: 'primary',
  qualified: 'success',
  rejected: 'error',
}

interface Props {
  leadId: string | null
}

export default function LeadDetailView({ leadId }: Props) {
  const { data: lead, isLoading } = useLead(leadId)
  const { mutate: updateLead } = useUpdateLead()
  const { mutate: revalidate, isPending: revalidating } = useRevalidateLead()
  const { mutate: enrich, isPending: enriching } = useEnrichLead()
  const { mutate: assign } = useAssignLead()
  const { data: users = [] } = useUsers()
  const { data: allTags = [] } = useTags()
  const { mutate: setLeadTags, isPending: settingTags } = useSetLeadTags()
  const { data: activities = [] } = useLeadActivities(leadId)
  const [notes, setNotes] = useState('')
  const notesTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastSavedNotes = useRef('')

  const [draft, setDraft] = useState<Record<string, string>>({})
  const fieldTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  useEffect(() => {
    if (lead) {
      setNotes(lead.notes ?? '')
      lastSavedNotes.current = lead.notes ?? ''
      setDraft({})
      Object.values(fieldTimers.current).forEach(clearTimeout)
      fieldTimers.current = {}
    }
  }, [lead?.id])

  const valueOf = (field: keyof LeadUpdate, current: string | null | undefined): string =>
    draft[field as string] !== undefined ? draft[field as string] : (current ?? '')

  const onFieldChange = (field: keyof LeadUpdate, value: string) => {
    setDraft(d => ({ ...d, [field as string]: value }))
    if (fieldTimers.current[field as string]) clearTimeout(fieldTimers.current[field as string])
    fieldTimers.current[field as string] = setTimeout(() => {
      if (!lead) return
      updateLead({ id: lead.id, data: { [field]: value || null } as LeadUpdate })
    }, 600)
  }

  const onNotesChange = (v: string) => {
    setNotes(v)
    if (notesTimer.current) clearTimeout(notesTimer.current)
    notesTimer.current = setTimeout(() => {
      if (lead && v !== lastSavedNotes.current) {
        updateLead({ id: lead.id, data: { notes: v } })
        lastSavedNotes.current = v
      }
    }, 500)
  }

  if (isLoading) return <CircularProgress size={24} />
  if (!lead) return <Typography variant="body2" color="text.secondary">Lead not found.</Typography>

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 1 }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <TextField
            variant="standard"
            fullWidth
            value={valueOf('name', lead.name)}
            onChange={e => onFieldChange('name', e.target.value)}
            slotProps={{ input: { sx: { fontSize: '1.25rem', fontWeight: 500 } } }}
          />
          <Chip
            label={lead.status}
            size="small"
            color={STATUS_COLORS[lead.status]}
            sx={{ mt: 0.5 }}
          />
        </Box>
        <Tooltip title={lead.website ? 'Re-scrape website and refresh AI brief, contacts, and fit reasons' : 'No website to scrape'}>
          <span>
            <Button
              size="small"
              variant="outlined"
              startIcon={<AutoFixHighIcon />}
              disabled={!lead.website || enriching}
              onClick={() => enrich(lead.id)}
            >
              {enriching ? 'Queued…' : 'Re-enrich'}
            </Button>
          </span>
        </Tooltip>
      </Box>

      <Divider />

      {lead.summary && (
        <Section title="Brief">
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
            {lead.summary}
          </Typography>
        </Section>
      )}

      {lead.fit_reasons && lead.fit_reasons.length > 0 && (
        <Section title="Why this fits">
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
            {lead.fit_reasons.map(r => (
              <Box key={r.segment_id}>
                <Chip label={r.segment_name} size="small" color="primary" variant="outlined" sx={{ mb: 0.25 }} />
                <Typography variant="body2">{r.rationale}</Typography>
              </Box>
            ))}
          </Box>
        </Section>
      )}

      <Section title="Assignee">
        <TextField
          select
          size="small"
          fullWidth
          value={lead.assigned_to_user_id ?? ''}
          onChange={e => assign({ id: lead.id, userId: e.target.value || null })}
        >
          <MenuItem value="">— Unassigned —</MenuItem>
          {users.map(u => (
            <MenuItem key={u.id} value={u.id}>
              {u.display_name || u.email}
            </MenuItem>
          ))}
        </TextField>
        {lead.last_touched_by && lead.last_touched_at && (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
            Last touched by {lead.last_touched_by.display_name || lead.last_touched_by.email} · {timeAgo(lead.last_touched_at)}
          </Typography>
        )}
      </Section>

      <Section title="Location">
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <TextField
            size="small"
            fullWidth
            placeholder="Street address"
            value={valueOf('address', lead.address)}
            onChange={e => onFieldChange('address', e.target.value)}
          />
          <Box sx={{ display: 'flex', gap: 1 }}>
            <TextField
              size="small"
              fullWidth
              placeholder="City"
              value={valueOf('city', lead.city)}
              onChange={e => onFieldChange('city', e.target.value)}
            />
            <TextField
              size="small"
              sx={{ width: 100 }}
              placeholder="State"
              value={valueOf('state', lead.state)}
              onChange={e => onFieldChange('state', e.target.value)}
            />
          </Box>
        </Box>
      </Section>

      <Section title="Phone">
        <TextField
          size="small"
          fullWidth
          placeholder="—"
          value={valueOf('phone', lead.phone)}
          onChange={e => onFieldChange('phone', e.target.value)}
        />
        {(lead.phone_normalized || lead.phone_type) && (
          <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5, flexWrap: 'wrap' }}>
            {lead.phone_normalized && (
              <Chip label={lead.phone_normalized} size="small" variant="outlined" />
            )}
            {lead.phone_type && (
              <Chip label={lead.phone_type} size="small" color="info" variant="outlined" />
            )}
          </Box>
        )}
      </Section>

      <Section
        title="Website"
        action={
          lead.website ? (
            <Link href={lead.website} target="_blank" rel="noreferrer" variant="caption">
              Open ↗
            </Link>
          ) : null
        }
      >
        <TextField
          size="small"
          fullWidth
          placeholder="https://example.com"
          value={valueOf('website', lead.website)}
          onChange={e => onFieldChange('website', e.target.value)}
        />
      </Section>

      <Section
        title={`Emails (${lead.emails.length})`}
        action={
          lead.emails.length > 0 && (
            <Tooltip title="Re-run MX + role + disposable checks">
              <span>
                <Button
                  size="small"
                  startIcon={<RefreshIcon />}
                  disabled={revalidating}
                  onClick={() => revalidate(lead.id)}
                >
                  {revalidating ? 'Checking…' : 'Revalidate'}
                </Button>
              </span>
            </Tooltip>
          )
        }
      >
        {lead.emails.length === 0 && <Typography variant="body2">—</Typography>}
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          {lead.emails.map(e => (
            <Box key={e.id} sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}>
              <Tooltip title={`source: ${e.source}, confidence: ${e.confidence}`}>
                <Link href={`mailto:${e.email}`}>{e.email}</Link>
              </Tooltip>
              <Chip label={e.source} size="small" variant="outlined" />
              <EmailBadges email={e} />
            </Box>
          ))}
        </Box>
      </Section>

      {lead.contacts.length > 0 && (
        <Section title={`Contacts (${lead.contacts.length})`}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            {lead.contacts.map(c => (
              <Box key={c.id}>
                <Typography variant="body2">
                  {c.name}{c.title ? ` — ${c.title}` : ''}
                </Typography>
                {(c.email || c.phone) && (
                  <Typography variant="caption" color="text.secondary">
                    {[c.email, c.phone].filter(Boolean).join(' · ')}
                  </Typography>
                )}
              </Box>
            ))}
          </Box>
        </Section>
      )}

      {lead.place_types.length > 0 && (
        <Section title="Categories">
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
            {lead.place_types.map(t => (
              <Chip key={t} label={t} size="small" variant="outlined" />
            ))}
          </Box>
        </Section>
      )}

      <Section title={`Tags (${lead.tags?.length ?? 0})`}>
        <Autocomplete
          multiple
          size="small"
          options={allTags}
          value={(allTags || []).filter(t => (lead.tags || []).some(lt => lt.id === t.id))}
          getOptionLabel={(o: TagDetail) => o.name}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          disabled={settingTags}
          onChange={(_e, value) => {
            setLeadTags({ leadId: lead.id, tagIds: value.map(v => v.id) })
          }}
          renderValue={(value, getItemProps) =>
            value.map((option, index) => {
              const { key, ...rest } = getItemProps({ index })
              return (
                <Chip
                  key={key}
                  label={option.name}
                  size="small"
                  sx={{
                    bgcolor: option.color || undefined,
                    color: option.color ? '#fff' : undefined,
                  }}
                  {...rest}
                />
              )
            })
          }
          renderInput={(params) => (
            <TextField
              {...params}
              placeholder={(lead.tags?.length ?? 0) === 0 ? 'Add tags…' : ''}
            />
          )}
        />
      </Section>

      <Divider />

      <Section title="Notes (autosaves)">
        <TextField
          multiline
          minRows={4}
          fullWidth
          size="small"
          value={notes}
          onChange={e => onNotesChange(e.target.value)}
          placeholder="Add notes about this lead…"
        />
      </Section>

      <Divider />

      <Section title={`Activity (${activities.length})`}>
        {activities.length === 0 ? (
          <Typography variant="body2" color="text.secondary">No activity yet.</Typography>
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            {activities.map(a => (
              <Box key={a.id} sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                <Avatar sx={{ width: 24, height: 24, fontSize: 11, bgcolor: 'primary.dark' }}>
                  {actorInitials(a)}
                </Avatar>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2">
                    <strong>{a.user?.display_name || a.user?.email || 'system'}</strong>{' '}
                    {actionLabel(a)}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {timeAgo(a.created_at)} · {new Date(a.created_at * 1000).toLocaleString()}
                  </Typography>
                </Box>
              </Box>
            ))}
          </Box>
        )}
      </Section>

      <Typography variant="caption" color="text.secondary">
        Source: {lead.source} · Created {new Date(lead.created_at * 1000).toLocaleString()}
      </Typography>
    </Box>
  )
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

function actorInitials(a: LeadActivity): string {
  const base = a.user?.display_name || a.user?.email || 'SY'
  const parts = base.trim().split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return base.slice(0, 2).toUpperCase()
}

function actionLabel(a: LeadActivity): string {
  const p = (a.payload || {}) as Record<string, unknown>
  const s = (v: unknown, fallback = '—') => (v == null ? fallback : String(v))
  switch (a.action) {
    case 'status_changed':
      return `changed status: ${s(p.from)} → ${s(p.to)}`
    case 'notes_updated':
      return 'updated notes'
    case 'firmographics_updated':
      return `updated ${Array.isArray(p.fields) ? (p.fields as string[]).join(', ') : 'firmographics'}`
    case 'assigned':
      return `assigned to ${s(p.assignee_name ?? p.assignee_email, 'user')}`
    case 'unassigned':
      return 'unassigned'
    case 'revalidated':
      return 'revalidated emails'
    case 'enrich_queued':
      return 'queued AI re-enrichment'
    case 'tags_updated': {
      const added = Array.isArray(p.added) ? (p.added as string[]).length : 0
      const removed = Array.isArray(p.removed) ? (p.removed as string[]).length : 0
      if (added && removed) return `updated tags (+${added}, -${removed})`
      if (added) return `added ${added} tag${added === 1 ? '' : 's'}`
      if (removed) return `removed ${removed} tag${removed === 1 ? '' : 's'}`
      return 'updated tags'
    }
    default:
      return a.action
  }
}

function Section({
  title, children, action,
}: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography variant="overline" color="text.secondary">{title}</Typography>
        {action}
      </Box>
      <Box>{children}</Box>
    </Box>
  )
}

function EmailBadges({ email }: { email: LeadEmail }) {
  const badges: React.ReactNode[] = []
  if (email.mx_valid === true) {
    badges.push(
      <Tooltip key="mx" title="MX record present"><VerifiedIcon fontSize="small" color="success" /></Tooltip>
    )
  } else if (email.mx_valid === false) {
    badges.push(
      <Tooltip key="mx" title="No MX record — likely undeliverable"><ErrorOutlineIcon fontSize="small" color="error" /></Tooltip>
    )
  }
  if (email.role_based) {
    badges.push(
      <Tooltip key="role" title="Role-based (info@, sales@, ...)"><Chip label="role" size="small" color="warning" variant="outlined" /></Tooltip>
    )
  }
  if (email.disposable) {
    badges.push(
      <Tooltip key="disp" title="Disposable / throwaway domain"><WarningAmberIcon fontSize="small" color="warning" /></Tooltip>
    )
  }
  return <>{badges}</>
}
