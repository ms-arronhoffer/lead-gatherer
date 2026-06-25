import { PublicClientApplication, type Configuration, type SilentRequest } from '@azure/msal-browser'
import axios from 'axios'
import type { AuthConfig } from '../types/user'

let _msal: PublicClientApplication | null = null
let _config: AuthConfig | null = null
let _initPromise: Promise<void> | null = null

export async function loadAuthConfig(): Promise<AuthConfig> {
  if (_config) return _config
  const { data } = await axios.get<AuthConfig>('/api/v1/auth-config')
  _config = data
  return data
}

export function getAuthConfig(): AuthConfig | null {
  return _config
}

export function getMsal(): PublicClientApplication | null {
  return _msal
}

export async function initMsal(): Promise<void> {
  if (_initPromise) return _initPromise
  _initPromise = (async () => {
    const cfg = await loadAuthConfig()
    if (!cfg.auth_enabled || !cfg.tenant_id || !cfg.client_id) return
    const msalConfig: Configuration = {
      auth: {
        clientId: cfg.client_id,
        authority: `https://login.microsoftonline.com/${cfg.tenant_id}`,
        redirectUri: window.location.origin,
      },
      cache: { cacheLocation: 'sessionStorage' },
    }
    const instance = new PublicClientApplication(msalConfig)
    await instance.initialize()
    await instance.handleRedirectPromise()
    _msal = instance
  })()
  return _initPromise
}

export function apiScopes(): string[] {
  if (!_config?.client_id) return []
  return [`api://${_config.client_id}/.default`]
}

export function graphScopes(): string[] {
  return ['Mail.Send', 'Mail.Read', 'User.Read']
}

export async function acquireGraphTokenSilent(): Promise<string | null> {
  if (!_msal) return null
  const accounts = _msal.getAllAccounts()
  if (accounts.length === 0) return null
  const request: SilentRequest = {
    account: accounts[0],
    scopes: graphScopes(),
  }
  try {
    const result = await _msal.acquireTokenSilent(request)
    return result.accessToken
  } catch {
    return null
  }
}

export async function acquireTokenSilent(): Promise<string | null> {
  if (!_msal) return null
  const accounts = _msal.getAllAccounts()
  if (accounts.length === 0) return null
  const request: SilentRequest = {
    account: accounts[0],
    scopes: apiScopes(),
  }
  try {
    const result = await _msal.acquireTokenSilent(request)
    return result.accessToken
  } catch {
    return null
  }
}

export async function signIn(): Promise<void> {
  if (!_msal) return
  await _msal.loginRedirect({ scopes: apiScopes() })
}

export async function signOut(): Promise<void> {
  if (!_msal) return
  await _msal.logoutRedirect()
}
