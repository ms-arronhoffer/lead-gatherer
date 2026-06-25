export interface User {
  id: string
  email: string
  display_name: string | null
}

export interface AuthConfig {
  auth_enabled: boolean
  tenant_id: string | null
  client_id: string | null
}
