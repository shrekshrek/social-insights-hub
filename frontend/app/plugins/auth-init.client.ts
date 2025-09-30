/**
 * 认证初始化插件（简化版）
 * 
 * 在客户端应用启动时初始化认证状态和权限数据
 */
export default defineNuxtPlugin(async () => {
  if (import.meta.server) return

  const { loggedIn, session, fetch: fetchSession, clear: clearSession } = useUserSession()
  
  // 初始化session
  await fetchSession()

  // 检查认证状态
  const isAuthenticated = loggedIn.value && 
                         session.value?.accessToken && 
                         session.value.accessToken.length > 0

  // 如果用户已认证，预加载权限数据
  if (isAuthenticated) {
    try {
      const { useUserStore } = await import('../../layers/auth/stores/user')
      const userStore = useUserStore()
      const permissions = usePermissions()
      
      // 并行加载用户信息和权限数据
      await Promise.all([
        userStore.fetchProfile().catch(() => {
          // 如果获取失败，使用session中的用户信息
          if (session.value?.user) {
            userStore.setUser(session.value.user)
          }
        }),
        permissions.loadUserPermissions?.().catch((error) => {
          console.warn('Failed to preload user permissions:', error)
        })
      ])
    } catch (error) {
      console.error('[Auth Init] Failed to initialize user data:', error)
      // 如果初始化失败，清除认证状态
      await clearSession()
    }
  }
})