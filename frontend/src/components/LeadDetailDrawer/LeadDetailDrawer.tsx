import { Drawer, Box, Typography, IconButton, Button } from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import { Link as RouterLink } from 'react-router-dom'
import LeadDetailView from './LeadDetailView'

interface Props {
  leadId: string | null
  onClose: () => void
}

export default function LeadDetailDrawer({ leadId, onClose }: Props) {
  return (
    <Drawer
      anchor="right"
      open={!!leadId}
      onClose={onClose}
      slotProps={{ paper: { sx: { width: { xs: '100%', sm: 480 } } } }}
    >
      <Box sx={{ p: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2, gap: 1 }}>
          <Typography variant="h6" sx={{ flex: 1 }}>Lead Detail</Typography>
          {leadId && (
            <Button
              component={RouterLink}
              to={`/leads/${leadId}`}
              size="small"
              startIcon={<OpenInNewIcon />}
            >
              Open page
            </Button>
          )}
          <IconButton onClick={onClose} size="small"><CloseIcon /></IconButton>
        </Box>
        <LeadDetailView leadId={leadId} />
      </Box>
    </Drawer>
  )
}
