import { Box, Button, Paper } from '@mui/material'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import { Link as RouterLink, useParams } from 'react-router-dom'
import LeadDetailView from '../components/LeadDetailDrawer/LeadDetailView'

export default function LeadDetailPage() {
  const { id } = useParams<{ id: string }>()
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Button
        component={RouterLink}
        to="/leads"
        startIcon={<ArrowBackIcon />}
        size="small"
        sx={{ alignSelf: 'flex-start' }}
      >
        Back to leads
      </Button>
      <Paper sx={{ p: 3, maxWidth: 720 }}>
        <LeadDetailView leadId={id ?? null} />
      </Paper>
    </Box>
  )
}
