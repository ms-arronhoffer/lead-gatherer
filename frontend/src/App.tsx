import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppBar, Box, Container, Toolbar, Typography, Button } from '@mui/material'
import SearchPage from './pages/SearchPage'
import LeadsPage from './pages/LeadsPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000 } },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppBar position="static">
          <Toolbar>
            <Typography variant="h6" sx={{ flex: 1 }}>Lead Gatherer</Typography>
            <Button color="inherit" component={Link} to="/">Search</Button>
            <Button color="inherit" component={Link} to="/leads">Leads</Button>
          </Toolbar>
        </AppBar>
        <Container maxWidth="xl" sx={{ mt: 4 }}>
          <Routes>
            <Route path="/" element={<SearchPage />} />
            <Route path="/leads" element={<LeadsPage />} />
          </Routes>
        </Container>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
