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

export interface ProxyResource extends BaseResource {
  label?: string | null
  protocol: string
  host: string
  port: number
  username?: string | null
  password?: string | null
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

export interface ProxyCreatePayload {
  label?: string | null
  protocol?: string
  host: string
  port: number
  username?: string | null
  password?: string | null
}

export interface ProxyUpdatePayload {
  label?: string | null
  protocol?: string | null
  host?: string | null
  port?: number | null
  username?: string | null
  password?: string | null
  is_active?: boolean
}

export type AccountListResponse = AccountResource[]
export type ProxyListResponse = ProxyResource[]
