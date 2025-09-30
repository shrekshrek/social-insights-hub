import type { UIColor } from '../types'

// 获取角色颜色
export const getRoleColor = (role: string): UIColor => {
  // 基于角色名称的颜色映射逻辑
  if (role === 'super_admin') return 'error'
  if (role === 'admin') return 'warning'
  if (role === 'user') return 'success'
  return 'primary'
}

// 获取角色显示名称
export const getRoleLabel = (role: string): string => {
  const staticLabels: Record<string, string> = {
    super_admin: '超级管理员',
    admin: '管理员',
    user: '普通用户'
  }
  return staticLabels[role] || role
}

// 日期格式化
export const formatDate = (dateString: string): string => {
  return new Date(dateString).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  })
} 