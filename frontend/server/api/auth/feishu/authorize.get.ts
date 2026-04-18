/**
 * 飞书授权 URL 获取端点
 * 代理后端 /auth/feishu/authorize，返回授权页跳转地址
 */

interface AuthorizeResponse {
  authorize_url: string
  state: string
}

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig(event)

  const backendUrl = import.meta.dev
    ? 'http://localhost:8000/api/v1'
    : ((config.apiBaseInternal as string) || config.public.apiBase || '/api/v1')

  try {
    const data = await $fetch<AuthorizeResponse>(`${backendUrl}/auth/feishu/authorize`)
    return data
  } catch (error: unknown) {
    const errorData = error as { data?: { detail?: string }; message?: string; status?: number; statusCode?: number }
    throw createError({
      statusCode: errorData?.status || errorData?.statusCode || 503,
      statusMessage: errorData?.data?.detail || '飞书登录服务不可用'
    })
  }
})
