import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppBar, Container, Toolbar, Typography, Button } from '@mui/material'
import SearchPage from './pages/SearchPage'
import LeadsPage from './pages/LeadsPage'
import HotLeadsPage from './pages/HotLeadsPage'
import KanbanPage from './pages/KanbanPage'
import SegmentsPage from './pages/SegmentsPage'
import TagsPage from './pages/TagsPage'
import WebhookSettingsPage from './pages/WebhookSettingsPage'
import LeadDetailPage from './pages/LeadDetailPage'
import CandidatesPage from './pages/CandidatesPage'
import SequencesPage from './pages/SequencesPage'
import AuthShell from './auth/AuthShell'
import UserMenu from './components/UserMenu'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000 } },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthShell>
        <BrowserRouter>
          <AppBar position="static">
            <Toolbar>
              <Typography variant="h6" sx={{ flex: 1 }}>Lead Gatherer</Typography>
              <Button color="inherit" component={Link} to="/">Search</Button>
              <Button color="inherit" component={Link} to="/leads">Leads</Button>
              <Button color="inherit" component={Link} to="/leads/hot">Hot Leads</Button>
              <Button color="inherit" component={Link} to="/leads/candidates">Candidates</Button>
              <Button color="inherit" component={Link} to="/leads/kanban">Kanban</Button>
              <Button color="inherit" component={Link} to="/sequences">Sequences</Button>
              <Button color="inherit" component={Link} to="/segments">Segments</Button>
              <Button color="inherit" component={Link} to="/tags">Tags</Button>
              <Button color="inherit" component={Link} to="/settings/webhooks">Webhooks</Button>
              <UserMenu />
            </Toolbar>
          </AppBar>
          <Container maxWidth={false} sx={{ mt: 4, px: { xs: 2, sm: 3 } }}>
            <Routes>
              <Route path="/" element={<SearchPage />} />
              <Route path="/leads" element={<LeadsPage />} />
              <Route path="/leads/hot" element={<HotLeadsPage />} />
              <Route path="/leads/candidates" element={<CandidatesPage />} />
              <Route path="/leads/kanban" element={<KanbanPage />} />
              <Route path="/leads/:id" element={<LeadDetailPage />} />
              <Route path="/sequences" element={<SequencesPage />} />
              <Route path="/segments" element={<SegmentsPage />} />
              <Route path="/tags" element={<TagsPage />} />
              <Route path="/settings/webhooks" element={<WebhookSettingsPage />} />
            </Routes>
          </Container>
        </BrowserRouter>
      </AuthShell>
    </QueryClientProvider>
  )
}
