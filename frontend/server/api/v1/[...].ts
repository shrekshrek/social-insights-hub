export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig(event)
  
  // 提取路径和查询参数
  const url = event.node.req.url || ''
  const [path, queryString] = url.split('?')
  const cleanPath = (path || '').replace(/^\/api\/v1/, '') || ''
  
  // 构建完整的后端URL
  const apiBase = config.public.apiBase || ''
  const isAbsoluteBase = apiBase.startsWith('http://') || apiBase.startsWith('https://')
  if (!isAbsoluteBase) {
    throw createError({
      statusCode: 500,
      statusMessage: 'Invalid apiBase configuration',
      data: 'config.public.apiBase 必须是包含协议的完整URL，请检查 NUXT_PUBLIC_API_BASE'
    })
  }
  const targetUrl = `${apiBase}${cleanPath}${queryString ? `?${queryString}` : ''}`
  
  // 获取请求方法
  const method = getMethod(event)
  
  // 简化的API认证检查（内联逻辑）
  const publicPaths = ['/auth/login', '/auth/register', '/auth/token', '/auth/logout', '/auth/request-password-reset', '/auth/reset-password']
  const needsAuth = cleanPath && !publicPaths.some(p => cleanPath === p || cleanPath.startsWith(p + '/'))
  
  // 准备请求头，过滤掉可能有问题的头部
  const headers: Record<string, string> = {}
  const originalHeaders = getHeaders(event)
  
  // 如果需要认证，检查Authorization头或session
  if (needsAuth) {
    let authHeader = originalHeaders['authorization'] || originalHeaders['Authorization']
    
    // 如果没有Authorization头，尝试从session获取token
    if (!authHeader) {
      const session = await getUserSession(event)
      if (session?.accessToken) {
        authHeader = `Bearer ${session.accessToken}`
        headers['Authorization'] = authHeader
      }
    }
    
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      throw createError({
        statusCode: 401,
        statusMessage: 'Unauthorized - Authentication required'
      })
    }
  }
  
  // 只复制安全的头部
  const safeHeaders = ['content-type', 'authorization', 'accept', 'user-agent']
  for (const [key, value] of Object.entries(originalHeaders)) {
    if (safeHeaders.includes(key.toLowerCase()) && typeof value === 'string') {
      headers[key] = value
    }
  }
  
  try {
    let body: string | object | undefined = undefined
    
    // 处理请求体
    if (method !== 'GET' && method !== 'HEAD') {
      const contentType = headers['content-type'] || headers['Content-Type'] || ''
      
      if (contentType.includes('application/x-www-form-urlencoded')) {
        // 对于form-urlencoded数据，直接读取原始body
        body = await readRawBody(event)
      } else {
        // 对于JSON数据，正常读取
        body = await readBody(event)
      }
    }
    
    // 转发请求到后端
    const response = await $fetch(targetUrl, {
      method,
      headers,
      body,
    })
    
    return response
  } catch (error: unknown) {
    // 处理错误响应
    const errorObj = error as { status?: number; statusCode?: number; statusText?: string; statusMessage?: string; data?: unknown; message?: string }
    
    throw createError({
      statusCode: errorObj.status || errorObj.statusCode || 500,
      statusMessage: errorObj.statusText || errorObj.statusMessage || 'Internal Server Error',
      data: errorObj.data || errorObj.message || 'API request failed'
    })
  }
}) 
