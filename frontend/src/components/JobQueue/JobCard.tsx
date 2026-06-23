import { Box, Typography, LinearProgress, Chip, Stack, IconButton, Tooltip } from '@mui/material'
import CancelIcon from '@mui/icons-material/Cancel'
import { useJobSocket } from '../../hooks/useJobSocket'
import { useCancelJob } from '../../hooks/useJobs'
import type { Job } from '../../types/job'

const STATUS_COLOR: Record<string, 'default' | 'primary' | 'success' | 'error' | 'warning'> = {
  pending: 'default',
  running: 'primary',
  completed: 'success',
  failed: 'error',
  cancelled: 'warning',
}

interface Props {
  job: Job
}

export default function JobCard({ job }: Props) {
  const progress = useJobSocket(
    ['pending', 'running'].includes(job.status) ? job.id : null
  )
  const { mutate: cancel } = useCancelJob()

  const pct = progress?.progress_pct ?? job.progress_pct
  const found = progress?.leads_found ?? job.leads_found
  const status = progress?.status ?? job.status
  const phase = progress?.phase ?? job.phase

  return (
    <Box sx={{ p: 2, border: 1, borderColor: 'divider', borderRadius: 1, bgcolor: 'background.paper' }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip
            label={status}
            color={STATUS_COLOR[status] ?? 'default'}
            size="small"
          />
          <Typography variant="body2" fontWeight={600}>
            {job.config.category} · {job.config.location}
          </Typography>
        </Stack>
        {['pending', 'running'].includes(status) && (
          <Tooltip title="Cancel job">
            <IconButton size="small" onClick={() => cancel(job.id)}>
              <CancelIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </Stack>

      {['running', 'pending'].includes(status) && (
        <Box sx={{ mt: 1 }}>
          <LinearProgress
            variant={pct > 0 ? 'determinate' : 'indeterminate'}
            value={pct}
          />
          <Typography variant="caption" color="text.secondary">
            {phase ? `Phase: ${phase.replace(/_/g, ' ')}` : 'Starting…'} · {found} leads found
          </Typography>
        </Box>
      )}

      {status === 'completed' && (
        <Typography variant="caption" color="success.main">
          Completed · {found} leads found
        </Typography>
      )}
      {status === 'failed' && (
        <Typography variant="caption" color="error">
          Failed: {job.error_message || 'Unknown error'}
        </Typography>
      )}
    </Box>
  )
}
