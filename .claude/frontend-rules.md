# Nuxt.js 前端开发核心规则

详细规范见：`frontend/CONTRIBUTING.md`

## 核心技术栈
- **框架**: Nuxt 4
- **架构**: Nuxt Layers (领域驱动设计)
- **UI库**: @nuxt/ui v4（基于 Tailwind CSS v4 和 Reka UI）
- **状态管理**: Pinia
- **认证**: nuxt-auth-utils
- **图表**: ECharts（必须用ClientOnly包装）

## 关键编码规范

### 设计原则
- **KISS原则**: 保持简单，避免过度工程化
- **统一处理**: 使用封装好的工具确保代码一致性和可维护性

### API调用
- **必须**使用 `composables/useApi.ts` 进行所有API通信
- 客户端操作使用 `apiRequest()`
- SSR数据获取使用 `useApiData()`
- **禁止**直接使用原始 `$fetch` 或 `useFetch`

### SSR注意事项
- 动态内容**必须**使用 `<ClientOnly>` 包装
- 提供有意义的 `fallback` 内容
- 数据获取优先使用SSR友好的方法
- 避免仅在 `onMounted` 中获取数据

### 项目结构
```
frontend/
├── layers/          # 业务层
│   ├── auth/       # 认证模块
│   ├── rbac/       # 权限模块
│   └── ui-kit/     # UI组件库
├── composables/     # 全局组合式函数
│   ├── useApi.ts   # API统一处理
│   └── usePermissions.ts # 权限检查
├── pages/          # 全局页面
├── config/         # 配置文件
│   ├── routes.ts   # 统一路由权限配置（页面约定+功能权限）
│   └── permissions.ts # 权限常量定义
├── server/api/v1/[...].ts # 服务端API代理
├── plugins/        # 插件配置
│   ├── auth-init.client.ts # 认证初始化
│   └── error-handler.client.ts # 全局错误处理
└── nuxt.config.ts  # 主配置
```

### 组件开发
- 业务组件放在对应Layer中
- 通用UI组件放在 `layers/ui-kit`
- 优先使用 @nuxt/ui v4 组件
- 样式使用 Tailwind CSS v4

### 状态管理
- Store按业务领域组织
- 使用 `pinia-plugin-persistedstate` 持久化
- Options API Store更SSR友好

### 权限控制
- 路由保护在 `config/routes.ts` 配置
- 使用 `usePermissions()` 检查权限
- 使用 `<PermissionGuard>` 组件控制UI

### 分层权限控制
- 页面访问与功能权限统一在 `config/routes.ts` 的 `ROUTE_CONFIG` 中声明
- 若需要更细粒度的功能开关，可在对应路由配置数组或对象中定义额外权限
- API认证逻辑已内联到 `server/api/v1/[...].ts`，无需单独配置文件

### 错误处理
- 全局错误处理器在 `plugins/error-handler.client.ts`
- 自动捕获Vue运行时错误和未处理的Promise rejection
- 401错误自动触发登出流程
