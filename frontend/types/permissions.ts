/**
 * 权限系统基础类型定义
 * 只包含跨模块共享的基础类型，不包含具体业务类型
 */

// 基础权限接口
export interface Permission {
  target: string
  action: string
}

// 带元数据的权限接口（用于从API获取的权限数据）
export interface PermissionWithMeta extends Permission {
  id?: number
  display_name: string
  description?: string
}

// 权限检查器接口（用于组件props等）
export interface PermissionChecker {
  hasPermission: (permission: Permission) => boolean
}

// 权限常量类型（用于配置文件）
export type PermissionConstant = Record<string, Permission>

// 权限比较工具函数
export const isSamePermission = (p1: Permission, p2: Permission): boolean => {
  return p1.target === p2.target && p1.action === p2.action
}

// 权限键生成工具函数（用于日志、调试等场景）
export const getPermissionKey = (permission: Permission): string => {
  return `${permission.target}:${permission.action}`
}