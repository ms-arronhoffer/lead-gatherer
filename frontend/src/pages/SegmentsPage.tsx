import { useEffect, useState } from 'react'
import {
  Accordion, AccordionDetails, AccordionSummary,
  Box, Button, Card, CardContent, Chip, Dialog, DialogActions, DialogContent,
  DialogTitle, FormControl, FormControlLabel, IconButton, InputLabel, MenuItem,
  Select, Stack, Switch, Table, TableBody, TableCell, TableHead, TableRow,
  TextField, Tooltip, Typography,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import EditIcon from '@mui/icons-material/Edit'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import RefreshIcon from '@mui/icons-material/Refresh'
import TuneIcon from '@mui/icons-material/Tune'
import {
  useApplySegmentTuning, useCreateSegment, useDeleteSegment, usePreviewSegment,
  useRescoreAll, useSegments, useSegmentTuning, useUpdateSegment,
} from '../hooks/useSegments'
import { useTags } from '../hooks/useTags'
import type { Segment, SegmentCreate, SegmentRules } from '../types/segment'
import type { TagDetail } from '../types/tag'

const EMPTY: SegmentCreate = {
  name: '',
  description: '',
  weight: 50,
  rules: {},
  enabled: true,
}

const BOOL_PREDICATES: { key: keyof SegmentRules; label: string }[] = [
  { key: 'has_email', label: 'Has email' },
  { key: 'has_phone', label: 'Has phone' },
  { key: 'has_website', label: 'Has website' },
  { key: 'mx_valid_email', label: 'Has MX-valid email' },
  { key: 'non_role_email', label: 'Has non-role email' },
  { key: 'assigned', label: 'Is assigned' },
  { key: 'unassigned', label: 'Is unassigned' },
]

const STATUSES = ['new', 'contacted', 'qualified', 'rejected']

export default function SegmentsPage() {
  const { data: segments = [], isLoading } = useSegments()
  const { data: tags = [] } = useTags()
  const tagsById = new Map(tags.map(t => [t.id, t]))
  const { mutate: del } = useDeleteSegment()
  const { mutate: rescore, isPending: rescoring } = useRescoreAll()
  const [editing, setEditing] = useState<Segment | 'new' | null>(null)

  return (
    <Box>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center', mb: 2 }}>
        <Typography variant="h5" sx={{ flex: 1 }}>Segments (ICP scoring)</Typography>
        <Tooltip title="Recompute scores for all leads">
          <span>
            <Button
              variant="outlined"
              startIcon={<RefreshIcon />}
              disabled={rescoring}
              onClick={() => rescore()}
            >
              {rescoring ? 'Rescoring…' : 'Rescore all'}
            </Button>
          </span>
        </Tooltip>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setEditing('new')}>
          New segment
        </Button>
      </Stack>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Each lead's score is the <strong>maximum weight</strong> of any segment whose rules it satisfies.
        All listed rules must pass for a segment to match.
      </Typography>

      <TuningPanel />

      {isLoading && <Typography>Loading…</Typography>}

      <Stack spacing={1.5}>
        {segments.map(s => (
          <Card key={s.id} variant="outlined">
            <CardContent>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                <Typography variant="h6">{s.name}</Typography>
                <Chip label={`weight ${s.weight}`} size="small" color="primary" />
                {!s.enabled && <Chip label="disabled" size="small" />}
                <Box sx={{ flex: 1 }} />
                <IconButton size="small" onClick={() => setEditing(s)}>
                  <EditIcon fontSize="small" />
                </IconButton>
                <IconButton
                  size="small"
                  color="error"
                  onClick={() => { if (window.confirm(`Delete segment "${s.name}"?`)) del(s.id) }}
                >
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </Stack>
              {s.description && (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                  {s.description}
                </Typography>
              )}
              <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', mt: 1 }}>
                {Object.entries(s.rules).map(([k, v]) => {
                  let display: string
                  if ((k === 'tags_any' || k === 'tags_all') && Array.isArray(v)) {
                    display = (v as string[]).map(id => tagsById.get(id)?.name ?? id).join('|')
                  } else if (Array.isArray(v)) {
                    display = v.join('|')
                  } else {
                    display = String(v)
                  }
                  return (
                    <Chip
                      key={k}
                      size="small"
                      variant="outlined"
                      label={`${k}: ${display}`}
                    />
                  )
                })}
                {Object.keys(s.rules).length === 0 && (
                  <Typography variant="caption" color="text.secondary">No rules — never matches</Typography>
                )}
              </Stack>
            </CardContent>
          </Card>
        ))}
      </Stack>

      {editing && (
        <SegmentEditor
          initial={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </Box>
  )
}

function SegmentEditor({ initial, onClose }: { initial: Segment | null; onClose: () => void }) {
  const [draft, setDraft] = useState<SegmentCreate>(
    initial
      ? {
          name: initial.name,
          description: initial.description ?? '',
          weight: initial.weight,
          rules: initial.rules,
          enabled: initial.enabled,
        }
      : EMPTY
  )
  const { data: tags = [] } = useTags()
  const tagsById = new Map<string, TagDetail>(tags.map(t => [t.id, t]))
  const { mutate: preview, data: previewData, reset: resetPreview } = usePreviewSegment()
  const { mutate: create, isPending: creating } = useCreateSegment()
  const { mutate: update, isPending: updating } = useUpdateSegment()

  useEffect(() => { resetPreview() }, [draft, resetPreview])

  const setRule = <K extends keyof SegmentRules>(k: K, v: SegmentRules[K] | undefined) => {
    setDraft(d => {
      const next = { ...d.rules } as SegmentRules
      if (v === undefined || v === null || (v as unknown) === '' || (Array.isArray(v) && v.length === 0)) {
        delete next[k]
      } else {
        next[k] = v
      }
      return { ...d, rules: next }
    })
  }

  const save = () => {
    if (initial) {
      update({ id: initial.id, data: draft }, { onSuccess: onClose })
    } else {
      create(draft, { onSuccess: onClose })
    }
  }

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{initial ? `Edit "${initial.name}"` : 'New segment'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            label="Name"
            size="small"
            value={draft.name}
            onChange={e => setDraft(d => ({ ...d, name: e.target.value }))}
          />
          <TextField
            label="Description"
            size="small"
            multiline
            minRows={2}
            value={draft.description ?? ''}
            onChange={e => setDraft(d => ({ ...d, description: e.target.value }))}
          />
          <TextField
            label="Weight (0–100)"
            type="number"
            size="small"
            value={draft.weight}
            onChange={e => setDraft(d => ({ ...d, weight: Math.max(0, Math.min(100, Number(e.target.value))) }))}
          />
          <FormControlLabel
            control={<Switch checked={draft.enabled} onChange={e => setDraft(d => ({ ...d, enabled: e.target.checked }))} />}
            label="Enabled"
          />

          <Typography variant="overline" color="text.secondary">Rules (all must pass)</Typography>

          {BOOL_PREDICATES.map(({ key, label }) => (
            <FormControl size="small" key={key}>
              <InputLabel>{label}</InputLabel>
              <Select
                value={draft.rules[key] === undefined ? '' : String(draft.rules[key])}
                label={label}
                onChange={e => setRule(key as keyof SegmentRules, e.target.value === '' ? undefined : (e.target.value === 'true') as never)}
              >
                <MenuItem value="">— ignore —</MenuItem>
                <MenuItem value="true">true</MenuItem>
                <MenuItem value="false">false</MenuItem>
              </Select>
            </FormControl>
          ))}

          <TextField
            label="Min employee count"
            type="number"
            size="small"
            value={draft.rules.min_employee_count ?? ''}
            onChange={e => setRule('min_employee_count', e.target.value === '' ? undefined : Number(e.target.value))}
          />
          <TextField
            label="Max employee count"
            type="number"
            size="small"
            value={draft.rules.max_employee_count ?? ''}
            onChange={e => setRule('max_employee_count', e.target.value === '' ? undefined : Number(e.target.value))}
          />
          <TextField
            label="Revenue range in (comma-separated)"
            size="small"
            placeholder="e.g. $1M-$10M, $10M-$50M"
            value={(draft.rules.revenue_range_in ?? []).join(', ')}
            onChange={e => setRule(
              'revenue_range_in',
              e.target.value.split(',').map(s => s.trim()).filter(Boolean)
            )}
          />

          <FormControl size="small">
            <InputLabel>Status in</InputLabel>
            <Select
              multiple
              value={draft.rules.status_in ?? []}
              label="Status in"
              onChange={e => {
                const v = e.target.value
                setRule('status_in', Array.isArray(v) ? v : [v])
              }}
              renderValue={(selected) => (selected as string[]).join(', ')}
            >
              {STATUSES.map(s => <MenuItem key={s} value={s}>{s}</MenuItem>)}
            </Select>
          </FormControl>

          <FormControl size="small">
            <InputLabel>Has any of tags</InputLabel>
            <Select
              multiple
              value={draft.rules.tags_any ?? []}
              label="Has any of tags"
              onChange={e => {
                const v = e.target.value
                setRule('tags_any', Array.isArray(v) ? v : [v])
              }}
              renderValue={(selected) => (
                <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }}>
                  {(selected as string[]).map(id => {
                    const t = tagsById.get(id)
                    return (
                      <Chip
                        key={id}
                        label={t?.name ?? id}
                        size="small"
                        sx={{ bgcolor: t?.color || undefined, color: t?.color ? '#fff' : undefined }}
                      />
                    )
                  })}
                </Stack>
              )}
            >
              {tags.map(t => (
                <MenuItem key={t.id} value={t.id}>
                  <Chip
                    label={t.name}
                    size="small"
                    sx={{ bgcolor: t.color || undefined, color: t.color ? '#fff' : undefined, mr: 1 }}
                  />
                </MenuItem>
              ))}
              {tags.length === 0 && <MenuItem disabled value="">No tags defined — create some on the Tags page</MenuItem>}
            </Select>
          </FormControl>

          <FormControl size="small">
            <InputLabel>Has all of tags</InputLabel>
            <Select
              multiple
              value={draft.rules.tags_all ?? []}
              label="Has all of tags"
              onChange={e => {
                const v = e.target.value
                setRule('tags_all', Array.isArray(v) ? v : [v])
              }}
              renderValue={(selected) => (
                <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }}>
                  {(selected as string[]).map(id => {
                    const t = tagsById.get(id)
                    return (
                      <Chip
                        key={id}
                        label={t?.name ?? id}
                        size="small"
                        sx={{ bgcolor: t?.color || undefined, color: t?.color ? '#fff' : undefined }}
                      />
                    )
                  })}
                </Stack>
              )}
            >
              {tags.map(t => (
                <MenuItem key={t.id} value={t.id}>
                  <Chip
                    label={t.name}
                    size="small"
                    sx={{ bgcolor: t.color || undefined, color: t.color ? '#fff' : undefined, mr: 1 }}
                  />
                </MenuItem>
              ))}
              {tags.length === 0 && <MenuItem disabled value="">No tags defined — create some on the Tags page</MenuItem>}
            </Select>
          </FormControl>

          <TextField
            label="Place types — any of (comma-separated)"
            size="small"
            placeholder="e.g. restaurant, store, health"
            value={(draft.rules.place_types_any ?? []).join(', ')}
            onChange={e => setRule(
              'place_types_any',
              e.target.value.split(',').map(s => s.trim()).filter(Boolean)
            )}
          />
          <TextField
            label="Place types — all of (comma-separated)"
            size="small"
            placeholder="e.g. restaurant, cafe"
            value={(draft.rules.place_types_all ?? []).join(', ')}
            onChange={e => setRule(
              'place_types_all',
              e.target.value.split(',').map(s => s.trim()).filter(Boolean)
            )}
          />

          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Button variant="outlined" onClick={() => preview(draft)}>Preview matches</Button>
            {previewData && (
              <Typography variant="body2" color="text.secondary">
                Matches <strong>{previewData.matches}</strong> of {previewData.total} leads
              </Typography>
            )}
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          disabled={!draft.name || creating || updating}
          onClick={save}
        >
          {creating || updating ? 'Saving…' : 'Save'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

function TuningPanel() {
  const { data: tuning = [], isLoading } = useSegmentTuning()
  const { mutate: apply, isPending: applying, data: applied } = useApplySegmentTuning()
  const changes = tuning.filter(t => t.delta !== 0)

  return (
    <Accordion variant="outlined" sx={{ mb: 2 }}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <TuneIcon fontSize="small" />
          <Typography sx={{ fontWeight: 600 }}>Auto-tune weights from outcomes</Typography>
          {changes.length > 0 && (
            <Chip label={`${changes.length} proposed`} size="small" color="warning" />
          )}
        </Stack>
      </AccordionSummary>
      <AccordionDetails>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          Adjusts each segment's weight toward the qualified-conversion rate of the leads it matches.
          Segments without enough matched leads are left unchanged.
        </Typography>
        {isLoading ? (
          <Typography variant="body2">Loading…</Typography>
        ) : tuning.length === 0 ? (
          <Typography variant="body2" color="text.secondary">No enabled segments to tune.</Typography>
        ) : (
          <>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Segment</TableCell>
                  <TableCell align="right">Matched</TableCell>
                  <TableCell align="right">Qualified</TableCell>
                  <TableCell align="right">Conv. rate</TableCell>
                  <TableCell align="right">Weight</TableCell>
                  <TableCell align="right">Proposed</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {tuning.map(t => (
                  <TableRow key={t.segment_id}>
                    <TableCell>{t.name}</TableCell>
                    <TableCell align="right">{t.matched}</TableCell>
                    <TableCell align="right">{t.qualified}</TableCell>
                    <TableCell align="right">{(t.conversion_rate * 100).toFixed(0)}%</TableCell>
                    <TableCell align="right">{t.current_weight}</TableCell>
                    <TableCell align="right">
                      {t.delta === 0 ? (
                        <Typography variant="body2" color="text.secondary" component="span">—</Typography>
                      ) : (
                        <Chip
                          label={`${t.proposed_weight} (${t.delta > 0 ? '+' : ''}${t.delta})`}
                          size="small"
                          color={t.delta > 0 ? 'success' : 'error'}
                        />
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Stack direction="row" spacing={2} sx={{ alignItems: 'center', mt: 1.5 }}>
              <Button
                variant="contained"
                startIcon={<TuneIcon />}
                disabled={applying || changes.length === 0}
                onClick={() => apply()}
              >
                {applying ? 'Applying…' : `Apply ${changes.length} change${changes.length === 1 ? '' : 's'}`}
              </Button>
              {applied && (
                <Typography variant="body2" color="text.secondary">
                  Applied {applied.applied.length}, rescored {applied.rescored} leads.
                </Typography>
              )}
            </Stack>
          </>
        )}
      </AccordionDetails>
    </Accordion>
  )
}
