/**
 * 审计日志类型定义
 */

import type { PaginatedResponse } from '~/types/common'

export type AuditAction =
  | 'LOGIN'
  | 'LOGIN_FAILED'
  | 'CREATE'
  | 'UPDATE'
  | 'DELETE'
  | 'TRIGGER'

export type AuditResource =
  | 'user'
  | 'role'
  | 'permission'
  | 'social_monitor'
  | 'social_task'
  | 'social_slice'
  | 'news_monitor'
  | 'news_task'
  | 'news_slice'
  | 'strategy'
  | 'analysis_job'
  | 'kb_document'
  | 'research_task'

export interface AuditLog {
  id: number
  user_id: number | null
  username: string | null
  action: AuditAction
  operation: string | null
  resource: AuditResource | null
  resource_id: string | null
  request_path: string | null
  status_code: number | null
  ip_address: string | null
  extra_data: Record<string, unknown> | null
  created_at: string
}

export type AuditLogListResponse = PaginatedResponse<AuditLog>

export interface AuditLogFilterParams {
  page?: number
  page_size?: number
  user_id?: number
  action?: AuditAction
  resource?: AuditResource
  start_time?: string
  end_time?: string
}
