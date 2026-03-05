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
│   ├── server/api/v1/[...].ts   # API 代理 (JWT 注入)
│   └── config/
│       ├── routes.ts            # 路由权限配置
│       └── permissions.ts       # 权限常量 (与后端一致)
├── layers/
│   ├── ui-kit/                  # 共享 UI 组件 (无业务)
│   ├── auth/                    # 登录, 注册, 认证状态
│   ├── rbac/                    # 角色/权限管理界面
│   ├── users/                   # 用户管理界面
│   └── social-media/            # 核心业务
│       ├── monitors/            # 监测项目管理
│       ├── tasks/               # 任务管理, 数据上传
│       └── analysis/            # 分析报告, 图表可视化
│           ├── components/
│           │   ├── task/        # 任务级报告组件
│           │   ├── slice/       # 监测级切片洞察组件
│           │   ├── shared/      # SpamRatioBar, TabSwitch 等
│           │   ├── deep-result/ # 深度分析结果
│           │   └── cost/        # Token 用量/成本
│           ├── composables/     # useAnalysis, useTokenUsage 等
│           └── types/           # 60+ 分析数据接口
└── nuxt.config.ts               # 主配置 (extends 注册所有 Layers)
```

## 编码约定

- API 调用**必须**用 `useApi.ts` (`apiRequest` / `useApiData`)，禁止裸 `$fetch`
- 动态内容**必须**用 `<ClientOnly>` 包装并提供 fallback
- SSR 数据获取优先用 `useApiData()`，避免仅在 `onMounted` 获取
- 渲染函数中从 `#components` 导入组件，禁止 `resolveComponent`
- 导航用组件的 `to` 属性，禁止 `onClick: () => navigateTo()`
- Options API Store 比 Setup Store 更 SSR 友好
- ECharts 必须通过 `useCharts` composable 使用
- 新增 Layer 必须在 `nuxt.config.ts` 的 `extends` 中注册

## 注意事项

- Nuxt 锁定 4.1.0（4.1.1 存在 reka-ui 兼容性问题）
- 前端命令在宿主机执行 (非 Docker 容器)
- 权限常量 `config/permissions.ts` 必须与后端 `rbac/init_data.py` 保持一致
- 路由权限在 `config/routes.ts` 的 `ROUTE_CONFIG` 中统一管理
