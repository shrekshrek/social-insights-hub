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
  USER_ACCESS: {target: 'user', action: 'access'},

  // 角色管理
  ROLE_READ: {target: 'role', action: 'read'},
  ROLE_WRITE: {target: 'role', action: 'write'},
  ROLE_DELETE: {target: 'role', action: 'delete'},
  ROLE_ACCESS: {target: 'role', action: 'access'},

  // 权限管理
  PERMISSION_READ: {target: 'permission', action: 'read'},
  PERMISSION_WRITE: {target: 'permission', action: 'write'},
  PERMISSION_DELETE: {target: 'permission', action: 'delete'},
  PERMISSION_ACCESS: {target: 'permission', action: 'access'},
  
  // 基础业务
  DASHBOARD_ACCESS: {target: 'dashboard', action: 'access'},

  // 社媒监测
  SOCIAL_MONITOR_ACCESS: {target: 'social_monitor', action: 'access'},
  SOCIAL_MONITOR_READ: {target: 'social_monitor', action: 'read'},
  SOCIAL_MONITOR_WRITE: {target: 'social_monitor', action: 'write'},
  SOCIAL_MONITOR_DELETE: {target: 'social_monitor', action: 'delete'},

  // 社媒采集
  SOCIAL_TASK_ACCESS: {target: 'social_task', action: 'access'},
  SOCIAL_TASK_READ: {target: 'social_task', action: 'read'},
  SOCIAL_TASK_WRITE: {target: 'social_task', action: 'write'},
  SOCIAL_TASK_DELETE: {target: 'social_task', action: 'delete'},

  // 新闻监测
  NEWS_MONITOR_ACCESS: {target: 'news_monitor', action: 'access'},
  NEWS_MONITOR_READ: {target: 'news_monitor', action: 'read'},
  NEWS_MONITOR_WRITE: {target: 'news_monitor', action: 'write'},
  NEWS_MONITOR_DELETE: {target: 'news_monitor', action: 'delete'},

  // 新闻采集
  NEWS_TASK_ACCESS: {target: 'news_task', action: 'access'},
  NEWS_TASK_READ: {target: 'news_task', action: 'read'},
  NEWS_TASK_WRITE: {target: 'news_task', action: 'write'},
  NEWS_TASK_DELETE: {target: 'news_task', action: 'delete'},

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

  // AI 分析
  ANALYSIS_ACCESS: {target: 'analysis', action: 'access'},
  ANALYSIS_READ: {target: 'analysis', action: 'read'},
  ANALYSIS_WRITE: {target: 'analysis', action: 'write'},
  ANALYSIS_DELETE: {target: 'analysis', action: 'delete'},

  // 研究分析
  RESEARCH_AGENT_ACCESS: {target: 'research_agent', action: 'access'},
  RESEARCH_AGENT_READ: {target: 'research_agent', action: 'read'},
  RESEARCH_AGENT_WRITE: {target: 'research_agent', action: 'write'},
  RESEARCH_AGENT_DELETE: {target: 'research_agent', action: 'delete'},

  // 审计日志
  AUDIT_ACCESS: {target: 'audit', action: 'access'},
  AUDIT_READ: {target: 'audit', action: 'read'},
} as const satisfies Record<string, Permission>

// ============================================================================
// 系统角色常量
// ============================================================================

export const SYSTEM_ROLES = {
  SUPER_ADMIN: 'super_admin',
  ADMIN: 'admin',
  USER: 'user',
} as const