export interface BaseResource {
  id: number
  is_active: boolean
  failure_count: number
  locked_by_task_id?: number | null
  last_used_at?: string | null
  created_at: string
  updated_at: string
}

export interface AccountResource extends BaseResource {
  platform: string
  account_name: string
  cookies?: string
}

export interface AccountCreatePayload {
  platform: string
  account_name: string
  cookies: string
}

export interface AccountUpdatePayload {
  account_name?: string
  cookies?: string
  is_active?: boolean
}

export interface ProxyProvider {
  id: number
  name: string
  provider_type: string
  secret_id: string
  signature: string
  username: string
  password: string
  pool_size: number
  validate_enabled: boolean
  sync_interval_minutes: number
  is_active: boolean
  last_synced_at?: string | null
  created_at: string
  updated_at: string
}

export interface ProxyProviderCreatePayload {
  name: string
  secret_id: string
  signature: string
  username: string
  password: string
  pool_size?: number
  validate_enabled?: boolean
  sync_interval_minutes?: number
  is_active?: boolean
}

export interface ProxyProviderUpdatePayload {
  name?: string
  secret_id?: string
  signature?: string
  username?: string
  password?: string
  pool_size?: number
  validate_enabled?: boolean
  sync_interval_minutes?: number
  is_active?: boolean
}

export type AccountListResponse = AccountResource[]
export type ProxyProviderListResponse = ProxyProvider[]

export interface ProxyPoolStatus {
  provider_id: number
  available: number
  last_synced_at?: string | null
  checked_at: string
}
