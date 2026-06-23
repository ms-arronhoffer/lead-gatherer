import { Box, Typography } from '@mui/material'
import SearchForm from '../components/SearchForm/SearchForm'
import JobQueue from '../components/JobQueue/JobQueue'

export default function SearchPage() {
  return (
    <Box>
      <Typography variant="h5" gutterBottom>Find Leads</Typography>
      <SearchForm />
      <JobQueue />
    </Box>
  )
}
