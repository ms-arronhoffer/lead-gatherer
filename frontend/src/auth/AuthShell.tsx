import { useEffect, useState, type ReactNode } from 'react'
import { Box, Button, CircularProgress, Stack, Typography } from '@mui/material'
import { getAuthConfig, initMsal, signIn } from './msal'
import { useMe } from '../hooks/useMe'

interface Props {
  children: ReactNode
}

export default function AuthShell({ children }: Props) {
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    initMsal()
      .then(() => setReady(true))
      .catch((err) => setError(String(err)))
  }, [])

  if (!ready) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        {error ? <Typography color="error">{error}</Typography> : <CircularProgress />}
      </Box>
    )
  }

  const cfg = getAuthConfig()
  if (!cfg?.auth_enabled) {
    return <>{children}</>
  }

  return <SignedInGate>{children}</SignedInGate>
}

function SignedInGate({ children }: Props) {
  const { data: me, isLoading, error } = useMe()

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <CircularProgress />
      </Box>
    )
  }

  if (!me || error) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <Stack spacing={2} sx={{ alignItems: 'center' }}>
          <Typography variant="h5">Lead Gatherer</Typography>
          <Typography color="text.secondary">Sign in with your Microsoft account to continue.</Typography>
          <Button variant="contained" onClick={() => signIn()}>Sign in</Button>
        </Stack>
      </Box>
    )
  }

  return <>{children}</>
}
