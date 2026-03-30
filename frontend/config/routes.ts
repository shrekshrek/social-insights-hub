/**
 * 路由由配置：集中管理权限与导航元数据
 */

import { PERMISSIONS } from './permissions'
import type { Permission } from '~/types/permissions'

export interface RouteConfig {
  permission: Permission | Permission[] | null
  label?: string
  showInNav?: boolean
  order?: number
}

export interface NavigationItem {
  path: string
  label: string
  order: number
}

// 每个路由集中声明权限与导航元信息，新增模块时只需要在此补充一条记录
export const ROUTE_CONFIG: Record<string, RouteConfig> = {
  '/dashboard': {
    permission: null,
    label: '工作台',
    showInNav: true,
    order: 10,
  },
  '/profile': { permission: null },
  '/settings': { permission: null },
  '/users': {
    permission: PERMISSIONS.USER_MGMT_ACCESS,
    label: '用户管理',
    showInNav: true,
    order: 30,
  },
  '/users/create': { permission: PERMISSIONS.USER_WRITE },
  '/users/[id]': { permission: PERMISSIONS.USER_READ },
  '/users/[id]/edit': { permission: PERMISSIONS.USER_WRITE },
  '/users/[id]/roles': { permission: PERMISSIONS.USER_WRITE },
  '/rbac/roles': {
    permission: PERMISSIONS.ROLE_MGMT_ACCESS,
    label: '角色管理',
    showInNav: true,
    order: 40,
  },
  '/rbac/roles/create': { permission: PERMISSIONS.ROLE_WRITE },
  '/rbac/roles/[id]': { permission: PERMISSIONS.ROLE_READ },
  '/rbac/roles/[id]/edit': { permission: PERMISSIONS.ROLE_WRITE },
  '/rbac/roles/[id]/permissions': { permission: PERMISSIONS.ROLE_WRITE },
  '/rbac/permissions': {
    permission: PERMISSIONS.PERM_MGMT_ACCESS,
    label: '权限管理',
    showInNav: true,
    order: 50,
  },
  '/rbac/permissions/[id]': { permission: PERMISSIONS.PERMISSION_READ },
  // 社交媒体数据洞察模块
  '/social-media/monitors': {
    permission: PERMISSIONS.MONITOR_ACCESS,
    label: '社媒监测',
    showInNav: true,
    order: 60,
  },
  '/social-media/monitors/create': { permission: PERMISSIONS.MONITOR_WRITE },
  '/social-media/monitors/[id]': { permission: PERMISSIONS.MONITOR_READ },
  '/social-media/tasks': {
    permission: PERMISSIONS.SOCIAL_TASK_ACCESS,
    label: '数据采集',
    showInNav: true,
    order: 70,
  },
  '/social-media/tasks/create': { permission: PERMISSIONS.SOCIAL_TASK_WRITE },
  '/social-media/tasks/[id]': { permission: PERMISSIONS.SOCIAL_TASK_READ },
  '/social-media/tasks/[id]/upload': { permission: PERMISSIONS.SOCIAL_TASK_WRITE },
  '/social-media/posts/[id]': { permission: PERMISSIONS.SOCIAL_TASK_READ },
  // AI 分析模块
  '/social-media/analysis': {
    permission: PERMISSIONS.SOCIAL_TASK_ACCESS,
    label: 'AI 分析',
    showInNav: true,
    order: 80,
  },
  // 策略定义模块
  '/strategies': {
    permission: PERMISSIONS.STRATEGY_ACCESS,
    label: '策略管理',
    showInNav: true,
    order: 90,
  },
  '/strategies/create': { permission: PERMISSIONS.STRATEGY_WRITE },
  '/strategies/[id]': { permission: PERMISSIONS.STRATEGY_READ },
  // 知识库模块
  '/knowledge-base': {
    permission: PERMISSIONS.KB_ACCESS,
    label: '市场知识库',
    showInNav: true,
    order: 95,
  },
  '/knowledge-base/upload': {
    permission: PERMISSIONS.KB_WRITE,
    label: '上传文档',
  },
  '/knowledge-base/search': {
    permission: PERMISSIONS.KB_READ,
    label: 'RAG 检索测试',
  },
}

/**
 * 获取路由所需权限
 */
export function getRoutePermissions(path: string): Permission | Permission[] | null {
  const config = getRouteConfig(path)
  return config?.permission ?? null
}

function getRouteConfig(path: string): RouteConfig | undefined {
  // 精确匹配
  if (ROUTE_CONFIG[path]) {
    return ROUTE_CONFIG[path]
  }

  // 动态路由（[id]等）通过正则方式匹配
  for (const [route, config] of Object.entries(ROUTE_CONFIG)) {
    if (!route.includes('[')) {
      continue
    }
    const pattern = route.replace(/\[.*?\]/g, '[^/]+')
    const regex = new RegExp(`^${pattern}$`)
    if (regex.test(path)) {
      return config
    }
  }

  // 模块前缀匹配
  const parts = path.split('/')
  if (parts.length >= 2) {
    const prefix = `/${parts[1]}`
    if (ROUTE_CONFIG[prefix]) {
      return ROUTE_CONFIG[prefix]
    }
  }

  return undefined
}

/**
 * 生成导航菜单（已按 order 排序）
 */
export function getNavigationItems(): NavigationItem[] {
  // 只保留需要出现在导航中的路由，并根据 order 进行排序
  return Object.entries(ROUTE_CONFIG)
    .filter(([, config]) => config.showInNav && config.label)
    .map(([path, config]) => ({
      path,
      label: config.label as string,
      order: config.order ?? 0,
    }))
    .sort((a, b) => a.order - b.order)
}

export function isPublicPage(path: string): boolean {
  const publicPages = ['/', '/401', '/403', '/404', '/500']
  return publicPages.includes(path)
}

export function isGuestOnlyPage(path: string): boolean {
  const guestPages = ['/login', '/register', '/reset-password', '/request-password-reset']
  return guestPages.some((page) => path.startsWith(page))
}

export interface UserInfo {
  id: number
  roles: string[]
  username: string
  email: string
  created_at: string
  updated_at: string
}
