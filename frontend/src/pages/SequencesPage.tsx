import { useEffect, useState } from 'react'
import {
  Box, Stack, Button, Typography, Table, TableHead, TableRow, TableCell,
  TableBody, TableContainer, Paper, CircularProgress, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, IconButton, Chip, Alert, Tabs, Tab,
  Switch, FormControlLabel, Divider,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import SendIcon from '@mui/icons-material/Send'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  approveAndSend, cacheGraphToken, createSequence, deleteSequence,
  listOutbound, listSequences, updateSequence,
} from '../api/sequences'
import type { Sequence, SequenceStep } from '../types/sequence'

const EMPTY_STEP: SequenceStep = {
  day_offset: 0,
  subject_template: 'Quick question about {{lead.name}}',
  body_template: '{{opener}}\n\nWould you have 15 minutes this week?\n\nThanks.',
  requires_approval: true,
}

export default function SequencesPage() {
  const qc = useQueryClient()
  const [tab, setTab] = useState(0)
  const [editing, setEditing] = useState<Sequence | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { cacheGraphToken().catch(() => undefined) }, [])

  const sequencesQ = useQuery({ queryKey: ['sequences'], queryFn: listSequences })
  const outboundQ = useQuery({
    queryKey: ['outbound', 'awaiting_approval'],
    queryFn: () => listOutbound({ status: 'awaiting_approval' }),
    enabled: tab === 1,
  })

  const create = useMutation({
    mutationFn: createSequence,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sequences'] }); setCreateOpen(false) },
    onError: (e: Error) => setErr(e.message),
  })
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<Sequence> }) => updateSequence(id, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sequences'] }); setEditing(null) },
    onError: (e: Error) => setErr(e.message),
  })
  const remove = useMutation({
    mutationFn: deleteSequence,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sequences'] }),
  })
  const approve = useMutation({
    mutationFn: approveAndSend,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['outbound'] }),
    onError: (e: Error) => setErr(e.message),
  })

  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
        <Typography variant="h5">Sequences</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
          New sequence
        </Button>
      </Stack>
      {err && <Alert severity="error" onClose={() => setErr(null)} sx={{ mb: 2 }}>{err}</Alert>}
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Templates" />
        <Tab label="Awaiting approval" />
      </Tabs>
      {tab === 0 && (
        sequencesQ.isLoading ? <CircularProgress /> :
        <TableContainer component={Paper}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Steps</TableCell>
                <TableCell>Enabled</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(sequencesQ.data ?? []).map(s => (
                <TableRow key={s.id} hover sx={{ cursor: 'pointer' }} onClick={() => setEditing(s)}>
                  <TableCell>{s.name}</TableCell>
                  <TableCell>{s.steps.length}</TableCell>
                  <TableCell><Chip size="small" label={s.enabled ? 'on' : 'off'} color={s.enabled ? 'success' : 'default'} /></TableCell>
                  <TableCell>
                    <IconButton size="small" onClick={(e) => { e.stopPropagation(); remove.mutate(s.id) }}>
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      {tab === 1 && (
        outboundQ.isLoading ? <CircularProgress /> :
        <TableContainer component={Paper}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>To</TableCell>
                <TableCell>Subject</TableCell>
                <TableCell>Body (preview)</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(outboundQ.data ?? []).map(m => (
                <TableRow key={m.id}>
                  <TableCell>{m.to_email}</TableCell>
                  <TableCell>{m.subject}</TableCell>
                  <TableCell sx={{ maxWidth: 480, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {m.body.slice(0, 200)}
                  </TableCell>
                  <TableCell>
                    <Button size="small" startIcon={<SendIcon />} onClick={() => approve.mutate(m.id)}>
                      Approve & send
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {(outboundQ.data ?? []).length === 0 && (
                <TableRow><TableCell colSpan={4} align="center"><em>No messages awaiting approval.</em></TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      {createOpen && (
        <SequenceEditor
          initial={{ name: '', description: '', steps: [EMPTY_STEP], enabled: true }}
          onCancel={() => setCreateOpen(false)}
          onSave={(payload) => create.mutate(payload)}
          busy={create.isPending}
        />
      )}
      {editing && (
        <SequenceEditor
          initial={editing}
          onCancel={() => setEditing(null)}
          onSave={(payload) => update.mutate({ id: editing.id, body: payload })}
          busy={update.isPending}
        />
      )}
    </Box>
  )
}

interface EditorPayload {
  name: string
  description: string | null
  steps: SequenceStep[]
  enabled: boolean
}

interface EditorProps {
  initial: EditorPayload | Sequence
  onCancel: () => void
  onSave: (payload: EditorPayload) => void
  busy: boolean
}

function SequenceEditor({ initial, onCancel, onSave, busy }: EditorProps) {
  const [name, setName] = useState(initial.name)
  const [description, setDescription] = useState(initial.description ?? '')
  const [enabled, setEnabled] = useState(initial.enabled)
  const [steps, setSteps] = useState<SequenceStep[]>(initial.steps as SequenceStep[])

  const updateStep = (idx: number, patch: Partial<SequenceStep>) =>
    setSteps(prev => prev.map((s, i) => i === idx ? { ...s, ...patch } : s))

  return (
    <Dialog open onClose={onCancel} maxWidth="md" fullWidth>
      <DialogTitle>{('id' in initial) ? `Edit ${initial.name}` : 'New sequence'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} fullWidth />
          <TextField label="Description" value={description} onChange={(e) => setDescription(e.target.value)} fullWidth multiline rows={2} />
          <FormControlLabel control={<Switch checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />} label="Enabled" />
          <Divider />
          <Stack direction="row" alignItems="center" justifyContent="space-between">
            <Typography variant="subtitle1">Steps</Typography>
            <Button size="small" startIcon={<AddIcon />} onClick={() => setSteps([...steps, EMPTY_STEP])}>Add step</Button>
          </Stack>
          {steps.map((s, idx) => (
            <Paper key={idx} variant="outlined" sx={{ p: 2 }}>
              <Stack spacing={1}>
                <Stack direction="row" spacing={2} alignItems="center">
                  <TextField label="Day offset" type="number" size="small" value={s.day_offset}
                    onChange={(e) => updateStep(idx, { day_offset: parseInt(e.target.value || '0', 10) })} />
                  <FormControlLabel control={<Switch checked={s.requires_approval}
                    onChange={(e) => updateStep(idx, { requires_approval: e.target.checked })} />}
                    label="Requires approval" />
                  <Box sx={{ flex: 1 }} />
                  <IconButton size="small" onClick={() => setSteps(steps.filter((_, i) => i !== idx))}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Stack>
                <TextField label="Subject template" size="small" fullWidth value={s.subject_template}
                  onChange={(e) => updateStep(idx, { subject_template: e.target.value })} />
                <TextField label="Body template" size="small" fullWidth multiline rows={5} value={s.body_template}
                  onChange={(e) => updateStep(idx, { body_template: e.target.value })}
                  helperText="Placeholders: {{opener}}, {{lead.name}}, {{lead.city}}, {{lead.state}}, {{lead.website}}, {{lead.category}}" />
              </Stack>
            </Paper>
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel}>Cancel</Button>
        <Button variant="contained" disabled={busy || !name.trim()}
          onClick={() => onSave({ name, description: description || null, steps, enabled })}>
          {busy ? 'Saving…' : 'Save'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
