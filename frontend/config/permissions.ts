/**
 * 权限配置文件（简化版）
 * 
 * 与后端保持一致的权限定义
 */

import type { Permission } from '../types/permissions'

// ============================================================================
// 权限定义（与后端保持一致）
// ============================================================================

export const PERMISSIONS = {
  // 用户管理
  USER_READ: {target: 'user', action: 'read'},
  USER_WRITE: {target: 'user', action: 'write'},
  USER_DELETE: {target: 'user', action: 'delete'},
  USER_MGMT_ACCESS: {target: 'user_mgmt', action: 'access'},
  
  // 角色管理
  ROLE_READ: {target: 'role', action: 'read'},
  ROLE_WRITE: {target: 'role', action: 'write'},
  ROLE_DELETE: {target: 'role', action: 'delete'},
  ROLE_MGMT_ACCESS: {target: 'role_mgmt', action: 'access'},
  
  // 权限管理
  PERMISSION_READ: {target: 'permission', action: 'read'},
  PERMISSION_WRITE: {target: 'permission', action: 'write'},
  PERMISSION_DELETE: {target: 'permission', action: 'delete'},
  PERM_MGMT_ACCESS: {target: 'perm_mgmt', action: 'access'},
  
  // 基础业务
  DASHBOARD_ACCESS: {target: 'dashboard', action: 'access'},
  
  // 扩展权限示例（根据需要添加）
  // REPORTS_ACCESS: {target: 'reports', action: 'access'},
  // REPORTS_READ: {target: 'reports', action: 'read'},
  // REPORTS_WRITE: {target: 'reports', action: 'write'},
  // REPORTS_EXPORT: {target: 'reports', action: 'export'},
} as const satisfies Record<string, Permission>

// ============================================================================
// 系统角色常量
// ============================================================================

export const SYSTEM_ROLES = {
  SUPER_ADMIN: 'super_admin',
  ADMIN: 'admin',
  USER: 'user',
} as const