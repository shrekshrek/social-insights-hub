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

  // 爬虫任务模块
  CRAWLER_TASKS_ACCESS: {target: 'crawler_tasks', action: 'access'},
  CRAWLER_TASKS_READ: {target: 'crawler_tasks', action: 'read'},
  CRAWLER_TASKS_WRITE: {target: 'crawler_tasks', action: 'write'},
  CRAWLER_TASKS_DELETE: {target: 'crawler_tasks', action: 'delete'},
  CRAWLER_TASKS_EXECUTE: {target: 'crawler_tasks', action: 'execute'},

  // 爬虫执行监控
  CRAWLER_EXECUTIONS_ACCESS: {target: 'crawler_executions', action: 'access'},
  CRAWLER_EXECUTIONS_READ: {target: 'crawler_executions', action: 'read'},

  // 爬虫资源管理
  CRAWLER_RESOURCES_ACCESS: {target: 'crawler_resources', action: 'access'},
  CRAWLER_RESOURCES_READ: {target: 'crawler_resources', action: 'read'},
  CRAWLER_RESOURCES_WRITE: {target: 'crawler_resources', action: 'write'},
  CRAWLER_RESOURCES_DELETE: {target: 'crawler_resources', action: 'delete'},

  // 爬虫指标
  CRAWLER_METRICS_ACCESS: {target: 'crawler_metrics', action: 'access'},
  CRAWLER_METRICS_READ: {target: 'crawler_metrics', action: 'read'},

  // 爬虫数据 - 笔记
  CRAWLER_DATA_NOTES_ACCESS: {target: 'crawler_data_notes', action: 'access'},
  CRAWLER_DATA_NOTES_READ: {target: 'crawler_data_notes', action: 'read'},
  CRAWLER_DATA_NOTES_WRITE: {target: 'crawler_data_notes', action: 'write'},
  CRAWLER_DATA_NOTES_DELETE: {target: 'crawler_data_notes', action: 'delete'},

  // 爬虫数据 - 评论
  CRAWLER_DATA_COMMENTS_ACCESS: {target: 'crawler_data_comments', action: 'access'},
  CRAWLER_DATA_COMMENTS_READ: {target: 'crawler_data_comments', action: 'read'},
  CRAWLER_DATA_COMMENTS_WRITE: {target: 'crawler_data_comments', action: 'write'},
  CRAWLER_DATA_COMMENTS_DELETE: {target: 'crawler_data_comments', action: 'delete'},

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
