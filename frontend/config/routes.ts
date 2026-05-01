/**
 * 路由由配置：集中管理权限与导航元数据
 */

import { PERMISSIONS } from "./permissions";
import type { Permission } from "~/types/permissions";

export interface RouteConfig {
  permission: Permission | Permission[] | null;
  label?: string;
  showInNav?: boolean;
  order?: number;
  // 模块顶层路由声明对应的权限 target（仅首级模块需要），
  // 作为 TARGET_ORDER / TARGET_LABEL 的单一来源
  target?: string;
}

export interface NavigationItem {
  path: string;
  label: string;
  order: number;
}

// 每个路由集中声明权限与导航元信息，新增模块时只需要在此补充一条记录
export const ROUTE_CONFIG: Record<string, RouteConfig> = {
  "/dashboard": {
    permission: null,
    label: "工作台",
    showInNav: true,
    order: 10,
    target: "dashboard",
  },
  "/profile": { permission: null },
  "/settings": { permission: null },
  // 策略研究模块
  "/strategies": {
    permission: PERMISSIONS.STRATEGY_ACCESS,
    label: "策略研究",
    showInNav: true,
    order: 20,
    target: "strategy",
  },
  "/strategies/create": { permission: PERMISSIONS.STRATEGY_WRITE },
  "/strategies/[id]": { permission: PERMISSIONS.STRATEGY_READ },
  // 社媒监测模块
  "/social-media/monitors": {
    permission: PERMISSIONS.SOCIAL_MONITOR_ACCESS,
    label: "社媒监测",
    showInNav: true,
    order: 30,
    target: "social_monitor",
  },
  "/social-media/monitors/create": { permission: PERMISSIONS.SOCIAL_MONITOR_WRITE },
  "/social-media/monitors/[id]": { permission: PERMISSIONS.SOCIAL_MONITOR_READ },
  "/social-media/tasks": {
    permission: PERMISSIONS.SOCIAL_TASK_ACCESS,
    label: "社媒采集",
    showInNav: true,
    order: 40,
    target: "social_task",
  },
  "/social-media/tasks/create": { permission: PERMISSIONS.SOCIAL_TASK_WRITE },
  "/social-media/tasks/[id]": { permission: PERMISSIONS.SOCIAL_TASK_READ },
  "/social-media/tasks/[id]/upload": {
    permission: PERMISSIONS.SOCIAL_TASK_WRITE,
  },
  "/social-media/posts/[id]": { permission: PERMISSIONS.SOCIAL_TASK_READ },
  // 新闻监测模块
  "/news-media/monitors": {
    permission: PERMISSIONS.NEWS_MONITOR_ACCESS,
    label: "新闻监测",
    showInNav: true,
    order: 50,
    target: "news_monitor",
  },
  "/news-media/monitors/create": { permission: PERMISSIONS.NEWS_MONITOR_WRITE },
  "/news-media/monitors/[id]": { permission: PERMISSIONS.NEWS_MONITOR_READ },
  "/news-media/tasks": {
    permission: PERMISSIONS.NEWS_TASK_ACCESS,
    label: "新闻采集",
    showInNav: true,
    order: 60,
    target: "news_task",
  },
  "/news-media/tasks/create": { permission: PERMISSIONS.NEWS_TASK_WRITE },
  "/news-media/tasks/[id]": { permission: PERMISSIONS.NEWS_TASK_READ },
  "/news-media/slices/[id]": { permission: PERMISSIONS.NEWS_MONITOR_READ },
  // 专题研究模块
  "/research-agent": {
    permission: PERMISSIONS.RESEARCH_AGENT_ACCESS,
    label: "专题研究",
    showInNav: true,
    order: 65,
    target: "research_agent",
  },
  "/research-agent/create": { permission: PERMISSIONS.RESEARCH_AGENT_WRITE },
  "/research-agent/[id]": { permission: PERMISSIONS.RESEARCH_AGENT_READ },
  // AI 统计模块（跨渠道 AnalysisJob）
  "/jobs": {
    permission: PERMISSIONS.JOBS_ACCESS,
    label: "AI 统计",
    showInNav: true,
    order: 70,
    target: "jobs",
  },
  // 知识库模块
  "/knowledge-base": {
    permission: PERMISSIONS.KB_ACCESS,
    label: "市场知识库",
    showInNav: true,
    order: 80,
    target: "knowledge_base",
  },
  "/knowledge-base/upload": {
    permission: PERMISSIONS.KB_WRITE,
    label: "上传文档",
  },
  "/knowledge-base/search": {
    permission: PERMISSIONS.KB_READ,
    label: "RAG 检索测试",
  },
  "/users": {
    permission: PERMISSIONS.USER_ACCESS,
    label: "用户管理",
    showInNav: true,
    order: 90,
    target: "user",
  },
  "/users/create": { permission: PERMISSIONS.USER_WRITE },
  "/users/[id]": { permission: PERMISSIONS.USER_READ },
  "/users/[id]/edit": { permission: PERMISSIONS.USER_WRITE },
  "/users/[id]/roles": { permission: PERMISSIONS.USER_WRITE },
  "/rbac/roles": {
    permission: PERMISSIONS.ROLE_ACCESS,
    label: "角色管理",
    showInNav: true,
    order: 100,
    target: "role",
  },
  "/rbac/roles/create": { permission: PERMISSIONS.ROLE_WRITE },
  "/rbac/roles/[id]": { permission: PERMISSIONS.ROLE_READ },
  "/rbac/roles/[id]/edit": { permission: PERMISSIONS.ROLE_WRITE },
  "/rbac/roles/[id]/permissions": { permission: PERMISSIONS.ROLE_WRITE },
  "/rbac/permissions": {
    permission: PERMISSIONS.PERMISSION_ACCESS,
    label: "权限管理",
    showInNav: true,
    order: 110,
    target: "permission",
  },
  "/rbac/permissions/[id]": { permission: PERMISSIONS.PERMISSION_READ },
  // 审计日志
  "/audit/logs": {
    permission: PERMISSIONS.AUDIT_ACCESS,
    label: "操作日志",
    showInNav: true,
    order: 120,
    target: "audit",
  },
};

// 从 ROUTE_CONFIG 派生：权限 target → 展示顺序 / 显示名称
// 单一来源：新增模块只需在 ROUTE_CONFIG 补充 target 字段即可
type TargetRoute = RouteConfig & { target: string; label: string; order: number };

const targetRoutes: readonly TargetRoute[] = Object.values(ROUTE_CONFIG).filter(
  (c): c is TargetRoute =>
    typeof c.target === "string" && typeof c.label === "string" && typeof c.order === "number",
);

export const TARGET_ORDER: Record<string, number> = Object.fromEntries(
  targetRoutes.map((c) => [c.target, c.order]),
);

export const TARGET_LABEL: Record<string, string> = Object.fromEntries(
  targetRoutes.map((c) => [c.target, c.label]),
);

/**
 * 获取路由所需权限
 */
export function getRoutePermissions(
  path: string,
): Permission | Permission[] | null {
  const config = getRouteConfig(path);
  return config?.permission ?? null;
}

function getRouteConfig(path: string): RouteConfig | undefined {
  // 精确匹配
  if (ROUTE_CONFIG[path]) {
    return ROUTE_CONFIG[path];
  }

  // 动态路由（[id]等）通过正则方式匹配
  for (const [route, config] of Object.entries(ROUTE_CONFIG)) {
    if (!route.includes("[")) {
      continue;
    }
    const pattern = route.replace(/\[.*?\]/g, "[^/]+");
    const regex = new RegExp(`^${pattern}$`);
    if (regex.test(path)) {
      return config;
    }
  }

  // 模块前缀匹配
  const parts = path.split("/");
  if (parts.length >= 2) {
    const prefix = `/${parts[1]}`;
    if (ROUTE_CONFIG[prefix]) {
      return ROUTE_CONFIG[prefix];
    }
  }

  return undefined;
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
    .sort((a, b) => a.order - b.order);
}

export function isPublicPage(path: string): boolean {
  const publicPages = ["/", "/401", "/403", "/404", "/500"];
  return publicPages.includes(path);
}

export function isGuestOnlyPage(path: string): boolean {
  const guestPages = [
    "/login",
    "/register",
    "/reset-password",
    "/request-password-reset",
    "/auth/feishu/callback",
  ];
  return guestPages.some((page) => path.startsWith(page));
}

export interface UserInfo {
  id: number;
  roles: string[];
  username: string;
  email: string;
  created_at: string;
  updated_at: string;
}
