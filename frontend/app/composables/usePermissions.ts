/**
 * 权限检查组合函数（简化版）
 * 
 * 核心功能：权限检查和加载
 */

import type { Permission, PermissionWithMeta } from '../../types/permissions'
import { isSamePermission } from '../../types/permissions'

// 全局权限缓存
const globalUserPermissions = ref<PermissionWithMeta[]>([])
const permissionsLoaded = ref(false)
const permissionsLoading = ref(false)

export const usePermissions = () => {
  // 服务端安全默认值
  if (import.meta.server) {
    return {
      hasPermission: () => false,
      loadUserPermissions: () => Promise.resolve([]),
      permissionsLoaded: readonly(ref(false)),
      permissionsLoading: readonly(ref(false)),
      
      // 管理员权限
      hasAdminPermissions: readonly(ref(false)),
      
      // 页面访问权限
      canAccessDashboard: readonly(ref(false)),
      canAccessUsersPage: readonly(ref(false)),
      canAccessRolesPage: readonly(ref(false)),
      canAccessPermissionsPage: readonly(ref(false)),
      
      // 用户操作权限
      canEditUser: () => false,
      canDeleteUser: () => false,
      
      // 用户信息
      currentUserId: readonly(ref(undefined)),
      currentUserRoles: readonly(ref([])),
      
      // 权限数据
      permissions: readonly(ref([]))
    }
  }

  const { session } = useUserSession()
  
  /**
   * 核心功能：检查权限
   */
  const hasPermission = (permission: Permission): boolean => {
    // 超级管理员特殊处理
    const userRoles = session.value?.user?.roles || []
    if (userRoles.includes('super_admin')) {
      return true  // 超级管理员拥有所有权限
    }
    
    // 管理员特殊处理（除了删除核心资源）
    if (userRoles.includes('admin')) {
      if (permission.action !== 'delete' || 
          !['user', 'role', 'permission'].includes(permission.target)) {
        return true
      }
    }
    
    // 普通权限检查
    if (!permissionsLoaded.value || !globalUserPermissions.value) {
      return false
    }
    
    return globalUserPermissions.value.some(p => isSamePermission(p, permission))
  }
  
  /**
   * 加载用户权限（缓存优化）
   */
  const loadUserPermissions = async (): Promise<PermissionWithMeta[]> => {
    // 避免重复加载
    if (permissionsLoading.value) return globalUserPermissions.value
    if (permissionsLoaded.value) return globalUserPermissions.value
    
    permissionsLoading.value = true
    
    try {
      const { apiRequest } = useApi()
      const permissions = await apiRequest<PermissionWithMeta[]>('/rbac/me/permissions')
      globalUserPermissions.value = permissions
      permissionsLoaded.value = true
      
      // 客户端本地存储缓存
      if (import.meta.client) {
        localStorage.setItem('user_permissions_cache', JSON.stringify({
          permissions,
          timestamp: Date.now(),
          userId: session.value?.user?.id
        }))
      }
      
      return permissions
    } catch (error) {
      console.error('Failed to load user permissions:', error)
      return []
    } finally {
      permissionsLoading.value = false
    }
  }

  /**
   * 获取当前用户ID
   */
  const currentUserId = computed(() => {
    return session.value?.user?.id
  })
  
  /**
   * 获取当前用户角色
   */
  const currentUserRoles = computed(() => {
    return session.value?.user?.roles || []
  })

  // 常用页面访问权限检查（基于hasPermission的便捷封装）
  const canAccessDashboard = computed(() => hasPermission({ target: 'dashboard', action: 'access' }))
  const canAccessUsersPage = computed(() => hasPermission({ target: 'user_mgmt', action: 'access' }))
  const canAccessRolesPage = computed(() => hasPermission({ target: 'role_mgmt', action: 'access' }))
  const canAccessPermissionsPage = computed(() => hasPermission({ target: 'perm_mgmt', action: 'access' }))
  
  // 管理员权限检查
  const hasAdminPermissions = computed(() => {
    return currentUserRoles.value.includes('admin') ||
           currentUserRoles.value.includes('super_admin')
  })
  
  // 用户操作权限检查
  const canEditUser = (targetUser: { id: number } | null | undefined): boolean => {
    if (!targetUser) return false
    
    // 有用户编辑权限可以编辑所有用户
    if (hasPermission({ target: 'user', action: 'write' })) {
      return true
    }
    
    // 用户只能编辑自己
    return targetUser.id === currentUserId.value
  }
  
  const canDeleteUser = (targetUser: { id: number } | null | undefined): boolean => {
    if (!targetUser) return false
    
    // 只有有删除权限的用户可以删除
    if (!hasPermission({ target: 'user', action: 'delete' })) {
      return false
    }
    
    // 不能删除自己
    return targetUser.id !== currentUserId.value
  }

  return {
    // 核心权限检查
    hasPermission,
    
    // 权限加载
    loadUserPermissions,
    permissionsLoaded: readonly(permissionsLoaded),
    permissionsLoading: readonly(permissionsLoading),
    
    // 管理员权限
    hasAdminPermissions: readonly(hasAdminPermissions),
    
    // 页面访问权限（UI使用）
    canAccessDashboard: readonly(canAccessDashboard),
    canAccessUsersPage: readonly(canAccessUsersPage),
    canAccessRolesPage: readonly(canAccessRolesPage),
    canAccessPermissionsPage: readonly(canAccessPermissionsPage),
    
    // 用户操作权限（UI使用）
    canEditUser,
    canDeleteUser,
    
    // 用户信息
    currentUserId: readonly(currentUserId),
    currentUserRoles: readonly(currentUserRoles),
    
    // 权限数据
    permissions: readonly(globalUserPermissions)
  }
}

// ============================================================================
// 导出的工具函数（用于特殊场景）
// ============================================================================

/**
 * 判断是否为核心权限
 */
export const isCorePermission = (permission: Permission): boolean => {
  return ['user', 'role', 'permission', 'user_mgmt', 'role_mgmt', 'perm_mgmt'].includes(permission.target)
}

/**
 * 判断角色是否为核心角色
 */
export const isCoreRole = (roleName: string): boolean => {
  return ['super_admin', 'admin', 'user'].includes(roleName)
}