/**
 * 飞书 OAuth 回调端点
 * 接收前端传来的 code + state，调用后端兑换 JWT，设置 session
 * 模式与 login.post.ts 一致
 */

interface CallbackRequest {
  code: string
  state: string
}

interface TokenResponse {
  access_token: string
  token_type: string
}

interface UserResponse {
  id: number
  email: string
  username: string
  is_active: boolean
  is_superuser: boolean
  oauth_provider?: string | null
  avatar_url?: string | null
  created_at: string
  updated_at: string
  roles?: string[]
}

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig(event)

  const backendUrl = import.meta.dev
    ? 'http://localhost:8000/api/v1'
    : ((config.apiBaseInternal as string) || config.public.apiBase || '/api/v1')

  const body = await readBody<CallbackRequest>(event)

  try {
    // 1. 调用后端飞书回调端点，获取 JWT
    const tokenResponse = await $fetch<TokenResponse>(`${backendUrl}/auth/feishu/callback`, {
      method: 'POST',
      body: {
        code: body.code,
        state: body.state
      }
    })

    // 2. 用 JWT 获取用户详细信息
    const userInfo = await $fetch<UserResponse>(`${backendUrl}/users/me`, {
      headers: {
        'Authorization': `Bearer ${tokenResponse.access_token}`
      }
    })

    // 3. 设置 session（与密码登录一致）
    await setUserSession(event, {
      user: {
        id: userInfo.id,
        email: userInfo.email,
        username: userInfo.username,
        is_active: userInfo.is_active,
        is_superuser: userInfo.is_superuser,
        oauth_provider: userInfo.oauth_provider,
        avatar_url: userInfo.avatar_url,
        created_at: userInfo.created_at,
        updated_at: userInfo.updated_at,
        roles: userInfo.roles || []
      },
      accessToken: tokenResponse.access_token,
      tokenType: tokenResponse.token_type || 'Bearer'
    })

    return {
      success: true,
      user: userInfo
    }
  } catch (error: unknown) {
    console.error('Feishu callback error:', error)

    const errorData = error as { data?: { detail?: string }; message?: string; status?: number; statusCode?: number }
    const errorMessage = errorData?.data?.detail || errorData?.message || '飞书登录失败'

    throw createError({
      statusCode: errorData?.status || errorData?.statusCode || 400,
      statusMessage: errorMessage
    })
  }
})
