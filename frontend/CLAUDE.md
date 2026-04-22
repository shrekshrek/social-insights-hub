# Frontend Tier — Nuxt 4 + Vue 3

> Tier 专属约定。与根 `CLAUDE.md` 冲突时以本文件为准。
> 详细编码规范见 `CODING_GUIDE.md`。

## 技术栈

| 项 | 选型 |
|----|------|
| 框架 | Nuxt 4.1.0 (锁定版本) |
| 语言 | TypeScript + Vue 3 |
| UI 库 | @nuxt/ui v4 (基于 Reka UI + Tailwind CSS v4) |
| 状态管理 | Pinia (Options API Store 优先) |
| 认证 | nuxt-auth-utils |
| 图表 | ECharts (via useCharts composable) |
| 包管理 | pnpm |

## 构建与测试命令

所有命令在项目根目录执行：

```bash
pnpm fe:typecheck     # vue-tsc --noEmit
pnpm fe:lint          # eslint
pnpm fe:add <pkg>     # pnpm --prefix frontend add
```

开发服务器：

```bash
pnpm fe:dev           # nuxt dev (port 3000)
```

## Layer 结构

```
frontend/
├── app/                         # 全局基础设施
│   ├── composables/
│   │   ├── useApi.ts            # 统一 API 请求 (apiRequest + useApiData)
│   │   ├── usePermissions.ts    # RBAC 权限检查
│   │   └── useCharts.ts         # ECharts 组合函数
│   ├── middleware/
│   │   └── route-guard.global.ts
│   ├── plugins/
│   │   └── auth-init.client.ts
├── config/
│   ├── routes.ts                # 路由权限配置
│   └── permissions.ts           # 权限常量 (与后端一致)
├── server/api/v1/[...].ts       # API 代理 (JWT 注入)
├── layers/
│   ├── ui-kit/                  # 共享 UI 组件 (无业务)
│   ├── auth/                    # 飞书扫码登录(主), 密码登录(次), 认证状态
│   ├── users/                   # 用户管理界面
│   ├── rbac/                    # 角色/权限管理界面
│   ├── jobs/                    # 跨渠道分析任务列表
│   ├── social-media/            # 社媒监测/任务/分析
│   │   ├── monitors/            # 监测项目管理
│   │   ├── tasks/               # 任务管理, 数据上传
│   │   └── analysis/            # 分析报告, 图表可视化
│   ├── news-media/              # 新闻监测/任务/分析
│   ├── strategies/              # 策略研究全流程
│   └── knowledge-base/          # 市场知识库管理
└── nuxt.config.ts               # 主配置 (extends 注册所有 Layers)
```

## 编码约定

- 确认对话框**必须**用 `const { $confirm } = useNuxtApp()` 程序化调用，禁止内联 `UModal`
- API 调用**必须**用 `useApi.ts` (`apiRequest` / `useApiData`)，禁止裸 `$fetch`
- 动态内容**必须**用 `<ClientOnly>` 包装并提供 fallback
- SSR 数据获取优先用 `useApiData()`，避免仅在 `onMounted` 获取
- 渲染函数中从 `#components` 导入组件，禁止 `resolveComponent`
- 导航用组件的 `to` 属性，禁止 `onClick: () => navigateTo()`
- Options API Store 比 Setup Store 更 SSR 友好
- ECharts 必须通过 `useCharts` composable 使用
- 新增 Layer 必须在 `nuxt.config.ts` 的 `extends` 中注册
- 全局错误处理器（`vueApp.config.errorHandler` / `vue:error` hook / `window.unhandledrejection`）**禁止触发任何 reactive 副作用**——不得 `toast.add`、不得写 reactive ref、不得 `navigateTo`。否则会在渲染错误时形成"error→副作用→再渲染→再 error"无限循环（2026-04 事故根因）。用户可见的运行时通知请走路由中间件 `error-handler.global.ts` 的显式分派。详见 [`app/plugins/error-handler.client.ts`](../app/plugins/error-handler.client.ts) 头注释
- 详情页面对"资源不存在"（404）必须在 composable 层用 `silent404: true` 抑制 toast + 显式 watch `data===null` 后 `navigateTo` 到列表。残留失效链接不能进入 broken render 路径

## 注意事项

- Nuxt 锁定 4.1.0（4.1.1 存在 reka-ui 兼容性问题）
- 前端命令在宿主机执行 (非 Docker 容器)
- 权限常量 `config/permissions.ts` 必须与后端 `rbac/init_data.py` 保持一致
- 路由权限在 `config/routes.ts` 的 `ROUTE_CONFIG` 中统一管理
