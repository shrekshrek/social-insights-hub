/**
 * 统一路由配置：集中管理权限与导航元数据
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
  '/charts': {
    permission: null,
    label: '数据图表',
    showInNav: true,
    order: 20,
  },
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
  '/rbac': { permission: PERMISSIONS.ROLE_MGMT_ACCESS },
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
}

/**
 * 获取路由所需权限
 */
export function getRoutePermissions(path: string): Permission | Permission[] | null {
  const config = getRouteConfig(path)
  return config?.permission ?? null
}

function getRouteConfig(path: string): RouteConfig | undefined {
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

  const parts = path.split('/')
  if (parts.length >= 2) {
    const prefix = `/${parts[1]}`
    // 兜底返回模块前缀的权限
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
