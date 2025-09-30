/**
 * 登录端点 - nuxt-auth-utils 官方推荐的唯一必需的认证端点
 * 负责验证用户凭据并设置session
 */

interface LoginRequest {
  email: string
  password: string
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
  created_at: string
  updated_at: string
  roles?: string[]
}

export default defineEventHandler(async (event) => {
  // 传入event以获取正确的context
  const config = useRuntimeConfig(event)
  
  // 获取完整的后端URL
  // 开发环境直连后端，生产环境使用配置
  const backendUrl = import.meta.dev 
    ? 'http://localhost:8000/api/v1'  // 开发环境直连后端
    : (config.public.apiBase || '/api/v1')  // 生产环境使用配置的路径
  
  const body = await readBody<LoginRequest>(event)
  const { email, password } = body

  try {
    // 调用后端 FastAPI 认证端点
    // FastAPI 期望 form-data 格式的认证请求
    const formData = new FormData()
    formData.append('username', email)
    formData.append('password', password)
    
    const tokenResponse = await $fetch<TokenResponse>(`${backendUrl}/auth/token`, {
      method: 'POST',
      body: formData
    })

    // 获取用户详细信息
    const userInfo = await $fetch<UserResponse>(`${backendUrl}/users/me`, {
      headers: {
        'Authorization': `Bearer ${tokenResponse.access_token}`
      }
    })

    // 设置用户会话 - 这是 nuxt-auth-utils 的核心功能
    // session 数据会被加密存储在 cookie 中
    await setUserSession(event, {
      user: {
        id: userInfo.id,
        email: userInfo.email,
        username: userInfo.username,
        is_active: userInfo.is_active,
        is_superuser: userInfo.is_superuser,
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
    console.error('Login error:', error)
    
    // 处理错误响应
    const errorData = error as { data?: { detail?: string }; message?: string; status?: number; statusCode?: number }
    const errorMessage = errorData?.data?.detail || errorData?.message || 'Invalid credentials'
    
    throw createError({
      statusCode: errorData?.status || errorData?.statusCode || 401,
      statusMessage: errorMessage
    })
  }
})