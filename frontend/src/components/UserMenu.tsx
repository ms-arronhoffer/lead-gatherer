import { useState, type MouseEvent } from 'react'
import { Avatar, Box, Chip, IconButton, Menu, MenuItem, Tooltip, Typography } from '@mui/material'
import LogoutIcon from '@mui/icons-material/Logout'
import { useMe } from '../hooks/useMe'
import { getAuthConfig, signOut } from '../auth/msal'

function initials(name?: string | null, email?: string): string {
  const base = name?.trim() || email || ''
  const parts = base.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return base.slice(0, 2).toUpperCase()
}

export default function UserMenu() {
  const { data: me } = useMe()
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const cfg = getAuthConfig()
  if (!me) return null
  const label = me.display_name || me.email
  const open = (e: MouseEvent<HTMLElement>) => setAnchor(e.currentTarget)
  const close = () => setAnchor(null)
  return (
    <Box>
      <Tooltip title={label}>
        <IconButton onClick={open} size="small" sx={{ ml: 1 }}>
          <Avatar sx={{ width: 32, height: 32, bgcolor: 'primary.dark', fontSize: 14 }}>
            {initials(me.display_name, me.email)}
          </Avatar>
        </IconButton>
      </Tooltip>
      <Menu anchorEl={anchor} open={!!anchor} onClose={close}>
        <Box sx={{ px: 2, py: 1 }}>
          <Typography variant="body2">{label}</Typography>
          <Typography variant="caption" color="text.secondary">{me.email}</Typography>
        </Box>
        {cfg?.auth_enabled && (
          <MenuItem onClick={() => { close(); signOut() }}>
            <LogoutIcon fontSize="small" sx={{ mr: 1 }} /> Sign out
          </MenuItem>
        )}
        {!cfg?.auth_enabled && (
          <MenuItem disabled>
            <Chip size="small" label="Dev bypass" />
          </MenuItem>
        )}
      </Menu>
    </Box>
  )
}
