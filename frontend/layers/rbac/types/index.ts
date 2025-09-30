/**
 * RBAC 模块类型定义
 * 包含角色管理相关的所有业务类型
 */

// 导入基础类型（来自全局）
import type { Role } from '../../../types/user'
import type { Permission, PermissionWithMeta } from '../../../types/permissions'
import type { PaginationParams, PaginatedResponse } from '../../../types/common'

// 重新导出基础类型，便于模块内部使用
export type { Role, Permission, PermissionWithMeta, PaginationParams, PaginatedResponse }

// 关联表类型
export interface RolePermission {
  role_id: number
  permission_id: number
}

export interface UserRole {
  user_id: number
  role_id: number
}

// 表单相关类型
export interface RoleCreate {
  name: string
  display_name: string
  description?: string
}

export interface RoleUpdate {
  name?: string
  display_name?: string
  description?: string
}

export interface PermissionCreate {
  target: string
  action: string
  display_name: string
  description?: string
}

export interface PermissionUpdate {
  display_name?: string
  description?: string
}

// API 响应类型
export interface RoleListResponse {
  items: Role[]
  total: number
  page: number
  page_size: number
}

export interface PermissionListResponse {
  items: PermissionWithMeta[]
  total: number
  page: number
  page_size: number
}