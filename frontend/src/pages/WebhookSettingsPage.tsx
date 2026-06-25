import { useState } from 'react'
import {
  Box, Typography, Button, Card, CardContent, Chip, IconButton, TextField,
  Switch, FormControlLabel, FormGroup, Checkbox, Dialog, DialogTitle,
  DialogContent, DialogActions, Tooltip, Stack, Divider, CircularProgress,
} from '@mui/material'
import DeleteIcon from '@mui/icons-material/Delete'
import SendIcon from '@mui/icons-material/Send'
import HistoryIcon from '@mui/icons-material/History'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import AddIcon from '@mui/icons-material/Add'
import {
  useWebhooks, useCreateWebhook, useUpdateWebhook, useDeleteWebhook,
  useSendTestEvent, useDeliveries,
} from '../hooks/useWebhooks'
import type { Webhook, WebhookEvent } from '../types/webhook'
import { WEBHOOK_EVENTS } from '../types/webhook'

const DELIVERY_COLORS: Record<string, 'default' | 'success' | 'warning' | 'error'> = {
  pending: 'warning',
  delivered: 'success',
  failed: 'error',
}

export default function WebhookSettingsPage() {
  const { data: webhooks, isLoading } = useWebhooks()
  const [createOpen, setCreateOpen] = useState(false)
  const [deliveriesFor, setDeliveriesFor] = useState<string | null>(null)

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5" sx={{ flex: 1 }}>Webhooks</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
          Add Webhook
        </Button>
      </Box>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Receive HTTP POST notifications when leads are created, updated, or change status.
        Each request is signed with HMAC-SHA256 in the <code>X-LG-Signature</code> header.
      </Typography>

      {isLoading && <CircularProgress size={24} />}

      <Stack spacing={2}>
        {(webhooks ?? []).map(w => (
          <WebhookCard key={w.id} webhook={w} onShowDeliveries={() => setDeliveriesFor(w.id)} />
        ))}
        {webhooks && webhooks.length === 0 && (
          <Typography variant="body2" color="text.secondary">No webhooks configured.</Typography>
        )}
      </Stack>

      <CreateWebhookDialog open={createOpen} onClose={() => setCreateOpen(false)} />
      <DeliveriesDialog webhookId={deliveriesFor} onClose={() => setDeliveriesFor(null)} />
    </Box>
  )
}

function WebhookCard({ webhook, onShowDeliveries }: { webhook: Webhook; onShowDeliveries: () => void }) {
  const { mutate: updateHook } = useUpdateWebhook()
  const { mutate: deleteHook } = useDeleteWebhook()
  const { mutate: sendTest, isPending: sending } = useSendTestEvent()
  const [secretRevealed, setSecretRevealed] = useState(false)

  const copySecret = () => navigator.clipboard.writeText(webhook.secret)

  return (
    <Card variant="outlined">
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="subtitle1" sx={{ wordBreak: 'break-all' }}>{webhook.url}</Typography>
            {webhook.description && (
              <Typography variant="body2" color="text.secondary">{webhook.description}</Typography>
            )}
          </Box>
          <FormControlLabel
            control={
              <Switch
                checked={webhook.enabled}
                onChange={e => updateHook({ id: webhook.id, data: { enabled: e.target.checked } })}
              />
            }
            label={webhook.enabled ? 'Enabled' : 'Disabled'}
          />
        </Box>

        <Box sx={{ display: 'flex', gap: 0.5, mt: 1, flexWrap: 'wrap' }}>
          {webhook.events.map(e => <Chip key={e} label={e} size="small" />)}
        </Box>

        <Divider sx={{ my: 1.5 }} />

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
          <Typography variant="caption" color="text.secondary" sx={{ minWidth: 60 }}>Secret:</Typography>
          <Typography variant="caption" sx={{ fontFamily: 'monospace', flex: 1, wordBreak: 'break-all' }}>
            {secretRevealed ? webhook.secret : '••••••••••••••••••••'}
          </Typography>
          <Button size="small" onClick={() => setSecretRevealed(v => !v)}>
            {secretRevealed ? 'Hide' : 'Show'}
          </Button>
          <Tooltip title="Copy secret">
            <IconButton size="small" onClick={copySecret}><ContentCopyIcon fontSize="small" /></IconButton>
          </Tooltip>
        </Box>

        <Stack direction="row" spacing={1}>
          <Button
            size="small"
            startIcon={<SendIcon />}
            disabled={!webhook.enabled || sending}
            onClick={() => sendTest(webhook.id)}
          >
            Send test event
          </Button>
          <Button size="small" startIcon={<HistoryIcon />} onClick={onShowDeliveries}>
            Deliveries
          </Button>
          <Box sx={{ flex: 1 }} />
          <Tooltip title="Delete webhook">
            <IconButton
              size="small"
              onClick={() => {
                if (confirm('Delete this webhook? Delivery history will also be removed.')) {
                  deleteHook(webhook.id)
                }
              }}
            >
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
      </CardContent>
    </Card>
  )
}

function CreateWebhookDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [url, setUrl] = useState('')
  const [description, setDescription] = useState('')
  const [events, setEvents] = useState<WebhookEvent[]>([...WEBHOOK_EVENTS])
  const { mutate: createHook, isPending, error, reset } = useCreateWebhook()

  const handleClose = () => {
    setUrl(''); setDescription(''); setEvents([...WEBHOOK_EVENTS])
    reset()
    onClose()
  }

  const handleSubmit = () => {
    createHook(
      { url, description: description || null, events, enabled: true },
      { onSuccess: handleClose }
    )
  }

  const toggleEvent = (event: WebhookEvent) => {
    setEvents(prev => prev.includes(event) ? prev.filter(e => e !== event) : [...prev, event])
  }

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="sm">
      <DialogTitle>Add Webhook</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            label="URL"
            placeholder="https://example.com/webhook"
            value={url}
            onChange={e => setUrl(e.target.value)}
            fullWidth
            size="small"
          />
          <TextField
            label="Description (optional)"
            value={description}
            onChange={e => setDescription(e.target.value)}
            fullWidth
            size="small"
          />
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>Events</Typography>
            <FormGroup>
              {WEBHOOK_EVENTS.map(event => (
                <FormControlLabel
                  key={event}
                  control={
                    <Checkbox
                      checked={events.includes(event)}
                      onChange={() => toggleEvent(event)}
                      size="small"
                    />
                  }
                  label={event}
                />
              ))}
            </FormGroup>
          </Box>
          {error && (
            <Typography variant="caption" color="error">
              {(error as Error).message}
            </Typography>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={handleSubmit}
          disabled={!url || events.length === 0 || isPending}
        >
          {isPending ? 'Creating…' : 'Create'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

function DeliveriesDialog({ webhookId, onClose }: { webhookId: string | null; onClose: () => void }) {
  const { data: deliveries, isLoading } = useDeliveries(webhookId)

  return (
    <Dialog open={!!webhookId} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Recent Deliveries</DialogTitle>
      <DialogContent>
        {isLoading && <CircularProgress size={24} />}
        {deliveries && deliveries.length === 0 && (
          <Typography variant="body2" color="text.secondary">No deliveries yet.</Typography>
        )}
        <Stack spacing={1}>
          {(deliveries ?? []).map(d => (
            <Card key={d.id} variant="outlined">
              <CardContent sx={{ '&:last-child': { pb: 1.5 } }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                  <Chip label={d.status} size="small" color={DELIVERY_COLORS[d.status] ?? 'default'} />
                  <Chip label={d.event} size="small" variant="outlined" />
                  {d.status_code != null && (
                    <Chip label={`HTTP ${d.status_code}`} size="small" variant="outlined" />
                  )}
                  <Typography variant="caption" color="text.secondary">attempt {d.attempt}</Typography>
                  <Box sx={{ flex: 1 }} />
                  <Typography variant="caption" color="text.secondary">
                    {new Date(d.created_at * 1000).toLocaleString()}
                  </Typography>
                </Box>
                {d.error && (
                  <Typography variant="caption" color="error" sx={{ display: 'block' }}>
                    {d.error}
                  </Typography>
                )}
                {d.next_retry_at && d.status === 'pending' && (
                  <Typography variant="caption" color="text.secondary">
                    Next retry: {new Date(d.next_retry_at * 1000).toLocaleString()}
                  </Typography>
                )}
              </CardContent>
            </Card>
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  )
}
