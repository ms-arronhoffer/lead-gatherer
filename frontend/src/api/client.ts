import axios from 'axios'
import { acquireTokenSilent, getAuthConfig } from '../auth/msal'

const client = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.request.use(async (config) => {
  const cfg = getAuthConfig()
  if (cfg?.auth_enabled) {
    const token = await acquireTokenSilent()
    if (token) {
      config.headers = config.headers ?? {}
      ;(config.headers as Record<string, string>)['Authorization'] = `Bearer ${token}`
    }
  }
  return config
})

export default client
