import { useEffect, useState } from 'react'
import {
  Box, Typography, Button, Card, CardContent, Chip, IconButton, TextField,
  Dialog, DialogTitle, DialogContent, DialogActions, Stack, CircularProgress,
} from '@mui/material'
import DeleteIcon from '@mui/icons-material/Delete'
import EditIcon from '@mui/icons-material/Edit'
import AddIcon from '@mui/icons-material/Add'
import { useCreateTag, useDeleteTag, useTags, useUpdateTag } from '../hooks/useTags'
import type { TagDetail } from '../types/tag'

const SWATCHES = ['#9e9e9e', '#ef5350', '#ff9800', '#ffc107', '#4caf50', '#26a69a', '#42a5f5', '#7e57c2', '#ec407a']

export default function TagsPage() {
  const { data: tags, isLoading } = useTags()
  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<TagDetail | null>(null)

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5" sx={{ flex: 1 }}>Tags</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
          New Tag
        </Button>
      </Box>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Manage the tag list used to label leads and to drive segment rules.
      </Typography>

      {isLoading && <CircularProgress size={24} />}

      <Stack spacing={1}>
        {(tags ?? []).map(t => (
          <TagRow key={t.id} tag={t} onEdit={() => setEditing(t)} />
        ))}
        {tags && tags.length === 0 && (
          <Typography variant="body2" color="text.secondary">No tags yet.</Typography>
        )}
      </Stack>

      <TagDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        mode="create"
      />
      <TagDialog
        open={!!editing}
        onClose={() => setEditing(null)}
        mode="edit"
        tag={editing ?? undefined}
      />
    </Box>
  )
}

function TagRow({ tag, onEdit }: { tag: TagDetail; onEdit: () => void }) {
  const { mutate: deleteTag } = useDeleteTag()
  return (
    <Card variant="outlined">
      <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2, '&:last-child': { pb: 2 } }}>
        <Chip
          label={tag.name}
          size="small"
          sx={{
            bgcolor: tag.color || undefined,
            color: tag.color ? '#fff' : undefined,
          }}
        />
        <Typography variant="caption" color="text.secondary">
          {tag.lead_count} lead{tag.lead_count === 1 ? '' : 's'}
        </Typography>
        <Box sx={{ flex: 1 }} />
        <IconButton size="small" onClick={onEdit}><EditIcon fontSize="small" /></IconButton>
        <IconButton
          size="small"
          onClick={() => {
            if (confirm(`Delete tag "${tag.name}"? It will be removed from ${tag.lead_count} lead(s).`)) {
              deleteTag(tag.id)
            }
          }}
        >
          <DeleteIcon fontSize="small" />
        </IconButton>
      </CardContent>
    </Card>
  )
}

function TagDialog({
  open, onClose, mode, tag,
}: {
  open: boolean
  onClose: () => void
  mode: 'create' | 'edit'
  tag?: TagDetail
}) {
  const [name, setName] = useState(tag?.name ?? '')
  const [color, setColor] = useState<string | null>(tag?.color ?? null)
  const { mutate: createTag, isPending: creating, error: createErr, reset: resetCreate } = useCreateTag()
  const { mutate: updateTag, isPending: updating, error: updateErr, reset: resetUpdate } = useUpdateTag()

  const isPending = creating || updating
  const error = createErr || updateErr

  useEffect(() => {
    if (open) {
      setName(tag?.name ?? '')
      setColor(tag?.color ?? null)
    }
  }, [open, tag?.id, tag?.name, tag?.color])

  const handleClose = () => {
    setName(''); setColor(null)
    resetCreate(); resetUpdate()
    onClose()
  }

  const handleSubmit = () => {
    if (mode === 'create') {
      createTag({ name: name.trim(), color }, { onSuccess: handleClose })
    } else if (tag) {
      updateTag({ id: tag.id, data: { name: name.trim(), color } }, { onSuccess: handleClose })
    }
  }

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="xs">
      <DialogTitle>{mode === 'create' ? 'New Tag' : 'Edit Tag'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            label="Name"
            value={name}
            onChange={e => setName(e.target.value)}
            fullWidth
            size="small"
            autoFocus
          />
          <Box>
            <Typography variant="caption" color="text.secondary">Color</Typography>
            <Box sx={{ display: 'flex', gap: 1, mt: 0.5, flexWrap: 'wrap' }}>
              <Box
                onClick={() => setColor(null)}
                sx={{
                  width: 28, height: 28, borderRadius: '50%', cursor: 'pointer',
                  border: color === null ? '2px solid #1976d2' : '1px solid #ccc',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 18,
                }}
              >∅</Box>
              {SWATCHES.map(c => (
                <Box
                  key={c}
                  onClick={() => setColor(c)}
                  sx={{
                    width: 28, height: 28, borderRadius: '50%', bgcolor: c, cursor: 'pointer',
                    border: color === c ? '2px solid #1976d2' : '1px solid #ccc',
                  }}
                />
              ))}
            </Box>
          </Box>
          {error && (
            <Typography variant="caption" color="error">{(error as Error).message}</Typography>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Cancel</Button>
        <Button variant="contained" onClick={handleSubmit} disabled={!name.trim() || isPending}>
          {isPending ? 'Saving…' : (mode === 'create' ? 'Create' : 'Save')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
