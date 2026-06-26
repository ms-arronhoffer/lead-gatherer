import { Stack, Typography } from '@mui/material'
import { useJobs } from '../../hooks/useJobs'
import JobCard from './JobCard'

export default function JobQueue() {
  const { data: jobs, isLoading } = useJobs()

  if (isLoading) return null
  if (!jobs?.length) return (
    <Typography color="text.secondary" sx={{ mt: 2 }}>
      No search jobs yet. Submit a search above to get started.
    </Typography>
  )

  return (
    <Stack spacing={1} sx={{ mt: 2 }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>Recent Jobs</Typography>
      {jobs.map(job => <JobCard key={job.id} job={job} />)}
    </Stack>
  )
}
