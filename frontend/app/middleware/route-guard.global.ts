/**
 * 简化版路由守卫中间件
 * 
 * 三层权限检查：
 * 1. 公开/客人页面处理
 * 2. 登录检查
 * 3. 统一权限检查
 */

import { getRoutePermissions, isPublicPage, isGuestOnlyPage } from '~/config/routes'
import type { Permission } from '~/types/permissions'
import { isJwtExpiring } from '~/app/utils/token'

export default defineNuxtRouteMiddleware(async (to) => {
  const { loggedIn, session, fetch: fetchSession, clear: clearSession } = useUserSession()
  
  // ========================================================================
  // 第1层：公开页面和客人页面处理
  // ========================================================================
  if (isPublicPage(to.path)) {
    return // 公开页面直接放行
  }
  
  if (isGuestOnlyPage(to.path)) {
    if (loggedIn.value) {
      return navigateTo('/dashboard')
    }
    return
  }
  
  // ========================================================================
  // 第2层：登录检查
  // ========================================================================
  // 确保session已加载
  if (!session.value && loggedIn.value === undefined) {
    await fetchSession()
  }
  
  if (!loggedIn.value || !session.value?.accessToken || isJwtExpiring(session.value.accessToken, 0)) {
    await clearSession()
    return navigateTo('/login')
  }
  
  // ========================================================================
  // 第3层：统一权限检查
  // ========================================================================
  const userRoles = session.value?.user?.roles || []
  
  // 超级管理员直接放行
  if (userRoles.includes('super_admin')) {
    return
  }
  
  // 获取路由所需权限
  const requiredPermissions = getRoutePermissions(to.path)
  if (!requiredPermissions) {
    return // 无权限要求，已登录即可访问
  }
  
  const permissions = usePermissions()
  
  // 管理员对于页面访问权限直接放行
  if (userRoles.includes('admin')) {
    const isSinglePermission = !Array.isArray(requiredPermissions)
    if (isSinglePermission && requiredPermissions.action === 'access') {
      return
    }
  }
  
  // 确保权限已加载
  if (!permissions.permissionsLoaded.value) {
    await permissions.loadUserPermissions()
  }
  
  // 检查权限
  const hasAccess = Array.isArray(requiredPermissions)
    ? requiredPermissions.every((p: Permission) => permissions.hasPermission(p))
    : permissions.hasPermission(requiredPermissions)
    
  if (!hasAccess) {
    return navigateTo('/403')
  }
})
