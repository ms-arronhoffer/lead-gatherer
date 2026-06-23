import { useState } from 'react'
import {
  Box, Button, TextField, Typography, Collapse,
  Slider, Switch, FormControlLabel, Stack, MenuItem, Select, InputLabel, FormControl, Divider,
} from '@mui/material'
import { useCreateJob } from '../../hooks/useJobs'
import { useActiveJobStore } from '../../store/activeJobStore'
import type { JobConfig } from '../../types/job'

const REVENUE_OPTIONS = ['', 'Under 1M', '1M-10M', '10M-50M', '50M-250M', '250M+']

export default function SearchForm() {
  const [category, setCategory] = useState('')
  const [location, setLocation] = useState('')
  const [maxResults, setMaxResults] = useState(50)
  const [employeeRange, setEmployeeRange] = useState<[number, number]>([1, 500])
  const [revenueRange, setRevenueRange] = useState('')
  const [enableScraping, setEnableScraping] = useState(true)
  const [enableSerp, setEnableSerp] = useState(false)
  const [showFilters, setShowFilters] = useState(false)

  const { mutate: create, isPending } = useCreateJob()
  const setActiveJobId = useActiveJobStore(s => s.setActiveJobId)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!category.trim() || !location.trim()) return
    const config: JobConfig = {
      category: category.trim(),
      location: location.trim(),
      max_results: maxResults,
      employee_min: employeeRange[0],
      employee_max: employeeRange[1],
      revenue_range: revenueRange || null,
      enable_website_scraping: enableScraping,
      enable_serp_enrichment: enableSerp,
    }
    create(config, { onSuccess: (job) => setActiveJobId(job.id) })
  }

  return (
    <Box component="form" onSubmit={handleSubmit} sx={{ p: 3, bgcolor: 'background.paper', borderRadius: 2, boxShadow: 1 }}>
      <Typography variant="h6" gutterBottom>New Lead Search</Typography>
      <Stack spacing={2}>
        <TextField
          label="Business Category"
          placeholder='e.g. "dental office", "auto repair", "restaurant"'
          value={category}
          onChange={e => setCategory(e.target.value)}
          required
          fullWidth
        />
        <TextField
          label="Location"
          placeholder='e.g. "Seattle, WA" or "Austin, TX"'
          value={location}
          onChange={e => setLocation(e.target.value)}
          required
          fullWidth
        />
        <Box>
          <Typography gutterBottom>Max Results: {maxResults}</Typography>
          <Slider
            value={maxResults}
            onChange={(_, v) => setMaxResults(v as number)}
            min={1} max={500} step={10}
            marks={[{ value: 50, label: '50' }, { value: 250, label: '250' }, { value: 500, label: '500' }]}
          />
        </Box>

        <Button variant="text" size="small" onClick={() => setShowFilters(!showFilters)} sx={{ alignSelf: 'flex-start' }}>
          {showFilters ? 'Hide' : 'Show'} size filters & options
        </Button>

        <Collapse in={showFilters}>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Divider />
            <Typography variant="subtitle2" color="text.secondary">
              Size filters are stored with the job for reference. Employee count and revenue cannot
              pre-filter Google Places results — use them for manual review.
            </Typography>
            <Box>
              <Typography gutterBottom>
                Employee range: {employeeRange[0]} – {employeeRange[1]}
              </Typography>
              <Slider
                value={employeeRange}
                onChange={(_, v) => setEmployeeRange(v as [number, number])}
                min={1} max={10000} step={10}
                valueLabelDisplay="auto"
              />
            </Box>
            <FormControl fullWidth>
              <InputLabel>Revenue Range</InputLabel>
              <Select value={revenueRange} label="Revenue Range" onChange={e => setRevenueRange(e.target.value)}>
                {REVENUE_OPTIONS.map(o => <MenuItem key={o} value={o}>{o || 'Any'}</MenuItem>)}
              </Select>
            </FormControl>
            <Divider />
            <FormControlLabel
              control={<Switch checked={enableScraping} onChange={e => setEnableScraping(e.target.checked)} />}
              label="Scrape websites for emails"
            />
            <FormControlLabel
              control={<Switch checked={enableSerp} onChange={e => setEnableSerp(e.target.checked)} />}
              label="Bing SERP enrichment (requires API key)"
            />
          </Stack>
        </Collapse>

        <Button type="submit" variant="contained" size="large" disabled={isPending || !category || !location}>
          {isPending ? 'Starting…' : 'Search Leads'}
        </Button>
      </Stack>
    </Box>
  )
}
