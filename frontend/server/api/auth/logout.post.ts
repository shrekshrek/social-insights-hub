/**
 * 登出端点 - 处理token失效和session清除
 * 符合 nuxt-auth-utils 最佳实践
 */

export default defineEventHandler(async (event) => {
  const session = await getUserSession(event)
  
  // 如果有有效的session，通知后端使token失效
  if (session?.accessToken) {
    try {
      const config = useRuntimeConfig(event)
      
      // 获取后端URL
      // 开发环境直连，生产环境使用配置
      const backendUrl = import.meta.dev 
        ? 'http://localhost:8000/api/v1'
        : (config.public.apiBase || '/api/v1')
      
      await $fetch(`${backendUrl}/auth/logout`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${session.accessToken}`
        }
      })
    } catch (error) {
      // 即使后端登出失败，也继续清除前端session
      console.warn('Backend logout notification failed:', error)
    }
  }
  
  // 清除用户会话
  await clearUserSession(event)
  
  return { 
    success: true,
    message: 'Logged out successfully' 
  }
})