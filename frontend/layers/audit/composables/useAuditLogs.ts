import type { AuditLogListResponse, AuditLogFilterParams } from '../types'

/**
 * 审计日志 Composable
 */
export const useAuditLogs = () => {
  const { useApiData } = useApi()

  /**
   * 获取审计日志列表（分页+过滤）
   */
  const getAuditLogs = (params?: MaybeRef<AuditLogFilterParams>) => {
    return useApiData<AuditLogListResponse>(
      computed(() => {
        const p = unref(params) || {}
        const searchParams = new URLSearchParams()

        if (p.page) searchParams.set('page', String(p.page))
        if (p.page_size) searchParams.set('page_size', String(p.page_size))
        if (p.user_id) searchParams.set('user_id', String(p.user_id))
        if (p.action) searchParams.set('action', p.action)
        if (p.resource) searchParams.set('resource', p.resource)
        if (p.start_time) searchParams.set('start_time', p.start_time)
        if (p.end_time) searchParams.set('end_time', p.end_time)

        const query = searchParams.toString()
        return `/audit/logs${query ? `?${query}` : ''}`
      }),
      {
        key: computed(() => {
          const p = unref(params) || {}
          return `audit-logs-${JSON.stringify(p)}`
        }),
        getCachedData: () => undefined,
      },
    )
  }

  return { getAuditLogs }
}
