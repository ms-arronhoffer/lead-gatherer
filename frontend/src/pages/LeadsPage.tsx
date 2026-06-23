import { Box, Typography } from '@mui/material'
import LeadsTable from '../components/LeadsTable/LeadsTable'

export default function LeadsPage() {
  return (
    <Box>
      <Typography variant="h5" gutterBottom>Leads</Typography>
      <LeadsTable />
    </Box>
  )
}
