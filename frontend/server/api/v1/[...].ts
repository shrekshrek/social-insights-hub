export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig(event)
  
  // 提取路径和查询参数
  const url = event.node.req.url || ''
  const [path, queryString] = url.split('?')
  const cleanPath = (path || '').replace(/^\/api\/v1/, '') || ''
  
  // 构建完整的后端URL
  // 开发环境直连后端（与 server/api/auth/* 一致）：dev 下 devProxy 只代理客户端请求，
  // SSR 内部 $fetch('/api/v1/...') 会落到本路由，若无此回退会因 apiBaseInternal 未设而报
  // Invalid apiBase。生产环境优先用内网地址 NUXT_API_BASE_INTERNAL，回退 public.apiBase
  const apiBase = import.meta.dev
    ? 'http://localhost:8000/api/v1'
    : (config.apiBaseInternal as string) || config.public.apiBase || ''
  const isAbsoluteBase = apiBase.startsWith('http://') || apiBase.startsWith('https://')
  if (!isAbsoluteBase) {
    throw createError({
      statusCode: 500,
      statusMessage: 'Invalid apiBase configuration',
      data: '服务端 API 地址必须是包含协议的完整URL，请设置 NUXT_API_BASE_INTERNAL=http://prod-backend:8000/api/v1'
    })
  }
  const targetUrl = `${apiBase}${cleanPath}${queryString ? `?${queryString}` : ''}`
  
  // 获取请求方法
  const method = getMethod(event)
  
  // 简化的API认证检查（内联逻辑）
  const publicPaths = ['/auth/login', '/auth/register', '/auth/token', '/auth/logout', '/auth/request-password-reset', '/auth/reset-password', '/auth/feishu/authorize', '/auth/feishu/callback']
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
    
    // 判断是否为文件下载请求（避免对普通 JSON 接口造成额外开销）
    const isBinaryRequest = cleanPath.endsWith('/export')

    if (isBinaryRequest) {
      // 二进制文件：使用 raw + arrayBuffer 以获取响应头和原始数据
      const response = await $fetch.raw(targetUrl, {
        method,
        headers,
        body,
        responseType: 'arrayBuffer',
      })
      const contentType = response.headers.get('content-type') || 'application/octet-stream'
      const disposition = response.headers.get('content-disposition')

      // 直接写入底层 response，避免 Nitro 序列化覆盖头部
      const res = event.node.res
      res.setHeader('Content-Type', contentType)
      if (disposition) {
        res.setHeader('Content-Disposition', disposition)
      }
      res.end(Buffer.from(response._data as ArrayBuffer))
      return
    }

    // 普通 JSON 请求：保持原有逻辑
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
