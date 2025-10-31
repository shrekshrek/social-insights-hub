/**
 * RBAC 模块权限工具函数
 * 包含角色和权限相关的UI展示和业务逻辑工具
 */

import type { Permission } from '~/types/permissions'
import { getPermissionKey } from '~/types/permissions'
import { SYSTEM_ROLES } from '~/config/permissions'

// 判断角色是否为核心角色
export const isCoreRole = (roleName: string | undefined): boolean => {
  if (!roleName) return false
  return ['super_admin', 'admin', 'user'].includes(roleName)
}

// 判断权限是否为RBAC核心权限
export const isCorePermission = (target: string | undefined): boolean => {
  if (!target) return false
  return ['user', 'role', 'permission', 'user_mgmt', 'role_mgmt', 'perm_mgmt'].includes(target)
}

// 权限分类工具函数
export const getPermissionType = (permission: Permission): 'page' | 'core' | 'business' => {
  if (permission.action === 'access') {
    return 'page'  // 页面访问权限
  }
  
  if (['user', 'role', 'permission', 'user_mgmt', 'role_mgmt', 'perm_mgmt'].includes(permission.target)) {
    return 'core'  // 系统核心权限
  }
  
  return 'business'  // 业务功能权限
}

// 获取权限分组
export const getPermissionGroup = (permission: Permission): string | null => {
  const type = getPermissionType(permission)
  switch (type) {
    case 'core':
      return 'CORE'
    case 'business':
      return 'BUSINESS'
    default:
      return null
  }
}

// 获取权限类型标签（用于UI展示）
export const getPermissionTypeLabel = (target: string | undefined, action: string | undefined): string => {
  if (action === 'access') {
    return '页面访问权限'
  }
  
  if (target && ['user', 'role', 'permission', 'user_mgmt', 'role_mgmt', 'perm_mgmt'].includes(target)) {
    return 'RBAC核心权限'
  }
  
  return '业务功能权限'
}

// 获取权限类型颜色（用于UI展示）
export const getPermissionTypeColor = (target: string | undefined, action: string | undefined): "primary" | "secondary" | "success" | "warning" | "error" | "info" | "neutral" => {
  if (action === 'access') {
    return 'info'  // 页面权限用info色
  }
  
  if (target && ['user', 'role', 'permission', 'user_mgmt', 'role_mgmt', 'perm_mgmt'].includes(target)) {
    return 'warning'  // RBAC核心权限用warning色
  }
  
  return 'success'  // 业务权限用success色
}

// 获取权限显示名称（RBAC模块专用，带丰富的映射）
export const getPermissionDisplayName = (permission: Permission): string => {
  const key = getPermissionKey(permission)
  const displayNames: Record<string, string> = {
    'user:read': '查看用户',
    'user:write': '编辑用户',
    'user:delete': '删除用户',
    'role:read': '查看角色',
    'role:write': '编辑角色',
    'role:delete': '删除角色',
    'permission:read': '查看权限',
    'permission:write': '编辑权限',
    'permission:delete': '删除权限',
    'dashboard:access': '访问工作台',
    'user_mgmt:access': '访问用户管理',
    'role_mgmt:access': '访问角色管理',
    'perm_mgmt:access': '访问权限管理',
  }
  return displayNames[key] || key
}

// 获取角色显示名称（RBAC模块专用）
export const getRoleDisplayName = (role: string): string => {
  const displayNames: Record<string, string> = {
    [SYSTEM_ROLES.SUPER_ADMIN]: '超级管理员',
    [SYSTEM_ROLES.ADMIN]: '管理员',
    [SYSTEM_ROLES.USER]: '普通用户',
  }
  return displayNames[role] || role
}