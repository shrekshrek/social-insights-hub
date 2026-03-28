/**
 * 权限配置文件（简化版）
 * 
 * 与后端保持一致的权限定义
 */

import type { Permission } from '~/types/permissions'

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

  // 监测管理
  MONITOR_ACCESS: {target: 'monitor', action: 'access'},
  MONITOR_READ: {target: 'monitor', action: 'read'},
  MONITOR_WRITE: {target: 'monitor', action: 'write'},
  MONITOR_DELETE: {target: 'monitor', action: 'delete'},

  SOCIAL_TASK_ACCESS: {target: 'social_task', action: 'access'},
  SOCIAL_TASK_READ: {target: 'social_task', action: 'read'},
  SOCIAL_TASK_WRITE: {target: 'social_task', action: 'write'},
  SOCIAL_TASK_DELETE: {target: 'social_task', action: 'delete'},

  // 策略定义
  STRATEGY_ACCESS: {target: 'strategy', action: 'access'},
  STRATEGY_READ: {target: 'strategy', action: 'read'},
  STRATEGY_WRITE: {target: 'strategy', action: 'write'},
  STRATEGY_DELETE: {target: 'strategy', action: 'delete'},

  // 知识库
  KB_ACCESS: {target: 'knowledge_base', action: 'access'},
  KB_READ: {target: 'knowledge_base', action: 'read'},
  KB_WRITE: {target: 'knowledge_base', action: 'write'},
  KB_DELETE: {target: 'knowledge_base', action: 'delete'},
} as const satisfies Record<string, Permission>

// ============================================================================
// 系统角色常量
// ============================================================================

export const SYSTEM_ROLES = {
  SUPER_ADMIN: 'super_admin',
  ADMIN: 'admin',
  USER: 'user',
} as const