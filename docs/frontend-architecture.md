
# 前端架构说明文档

- **版本**: `v1.0`
- **日期**: `2025-07-24`
- **状态**: `完成`

---

## 目录

1.  [系统概览](#1-系统概览)
2.  [核心架构：Nuxt Layers](#2-核心架构nuxt-layers)
3.  [模块详细说明](#3-模块详细说明)
4.  [API 通信与状态管理](#4-api-通信与状态管理)
5.  [UI 与样式](#5-ui-与样式)
6.  [开发指南](#6-开发指南)

---

## 1. 系统概览

### 1.1. 技术栈

-   **核心框架**: [Nuxt 4](https://nuxt.com/)
-   **UI 库**: [@nuxt/ui v3](https://ui.nuxt.com/) (基于 Tailwind CSS)
-   **状态管理**: [Pinia](https://pinia.vuejs.org/)
-   **认证**: [nuxt-auth-utils](https://nuxt.com/modules/auth-utils)
-   **数据可视化**: [ECharts](https://echarts.apache.org/en/index.html)
-   **包管理**: PNPM

### 1.2. 架构特点

-   **Nuxt Layers**: 采用官方推荐的 Layers 模式实现前端的模块化和领域驱动设计 (DDD)，与后端架构保持对称。
-   **配置驱动**: 路由权限、导航菜单等核心功能由 `config/` 目录下的配置文件驱动，实现了逻辑与配置的分离。
-   **统一 API 通信**: 所有后端 API 请求都通过全局的 `composables/useApi.ts` 进行，内置了统一的错误处理、认证集成和加载状态管理。
-   **SSR 优先**: 遵循 Nuxt 4 的服务端渲染 (SSR) 最佳实践，通过 `useApiData` 等组合式函数确保高效和 SEO 友好的数据获取。
-   **类型安全**: 全面使用 TypeScript，从 API 数据到组件属性，确保端到端的类型安全。

---

## 2. 核心架构：Nuxt Layers

### 2.1. 项目结构

```
frontend/
├── layers/                    # 业务层架构 (DDD核心)
│   ├── auth/                 # 认证模块
│   ├── rbac/                 # 角色权限管理模块
│   ├── users/                # 用户管理模块
│   └── ui-kit/               # 共享UI组件库
├── pages/                     # 全局页面
├── components/                # 全局通用组件
├── composables/               # 全局组合式函数
│   ├── useApi.ts             # 统一API请求 (核心)
│   └── usePermissions.ts     # 权限检查 (核心)
├── config/                    # 全局配置文件
│   ├── routes.ts             # 路由权限配置
│   └── permissions.ts        # 权限元数据定义
├── middleware/                # 全局中间件
│   └── route-guard.global.ts # 统一路由守卫
├── plugins/                   # Nuxt 插件
│   └── auth-init.client.ts   # 认证初始化
├── stores/                    # 全局状态管理
├── nuxt.config.ts             # 主配置文件
└── error.vue                  # 全局错误页面
```

### 2.2. Layer 设计原则

-   **业务 Layer**: 封装特定业务领域的所有功能（页面、组件、API调用等），例如 `layers/auth`。每个业务 Layer 都是一个功能相对独立的“微前端”。
-   **UI Layer**: `layers/ui-kit` 用于存放跨业务复用的、纯粹的 UI 组件（如自定义按钮、卡片等），不包含业务逻辑。
-   **自包含原则**: 每个 Layer 都应被设计成一个功能完整的迷你 Nuxt 应用，可以理论上被独立复用。
-   **主应用编排**: 根目录的 `pages/`, `nuxt.config.ts` 等文件负责组合和编排来自不同 Layer 的功能，构建成最终的完整应用。

---

## 3. 模块详细说明

### 3.1. 全局核心模块

-   **`composables/`**:
    -   `useApi.ts`: 项目的 API 通信基石。封装了 `$fetch` 和 `useFetch`，提供了 `apiRequest` (客户端操作) 和 `useApiData` (SSR数据获取) 两个核心方法。
    -   `usePermissions.ts`: 动态 RBAC 系统的核心。提供 `hasPermission`, `hasRole` 等响应式的权限检查方法。
-   **`config/`**:
    -   `permissions.ts`: 定义了系统权限和业务权限的元数据（如显示名称、分组），为权限管理界面提供配置。
    -   `routes.ts`: 定义了每个页面的访问权限要求，供全局路由守卫使用。
-   **`middleware/`**:
    -   `route-guard.global.ts`: 全局路由中间件。在每次路由跳转时，它会读取 `config/routes.ts` 的配置，结合 `usePermissions` 的检查结果，自动处理页面的认证和权限校验。
-   **`plugins/`**:
    -   `auth-init.client.ts`: 在应用客户端初始化时运行，负责加载用户会话信息和权限数据，确保在渲染任何页面前，应用的权限状态是就绪的。

### 3.2. 业务 Layers

-   **`auth` Layer**:
    -   **职责**: 处理用户认证的全流程。
    -   **内容**: 包含登录、注册、忘记密码、重置密码等页面，以及封装认证相关 API 调用的 `useAuthApi.ts`。
-   **`rbac` Layer**:
    -   **职责**: 提供角色和权限的可视化管理界面。
    -   **内容**: 包含角色列表/表单、权限列表/表单等页面和组件，以及封装 RBAC 相关 API 的 `useRbacApi.ts`。
-   **`users` Layer**:
    -   **职责**: 提供用户管理界面。
    -   **内容**: 包含用户列表、用户详情、用户表单等组件，以及封装用户管理 API 的 `useUsersApi.ts`。

---

## 4. API 通信与状态管理

### 4.1. API 通信 (`useApi.ts`)

-   **`apiRequest()`**: 用于客户端发起的、会产生副作用的操作（如 POST, PUT, DELETE）。它会自动处理加载状态和错误通知。
-   **`useApiData()`**: 用于在页面或组件加载时获取数据（GET请求），完全兼容 SSR。它能防止在服务端和客户端之间重复请求数据。
-   **统一处理**: 自动附加认证 Token，并在收到 `401 Unauthorized` 响应时自动登出用户。错误信息会通过全局 Toast 组件展示给用户。

### 4.2. 状态管理 (`Pinia`)

-   **Store 划分**: 状态管理的 Store 按业务领域划分。全局性的状态（如权限配置）放在根 `stores/` 目录下，而与特定业务 Layer 紧密相关的状态则放在该 Layer 的 `stores/` 目录中。
-   **持久化**: 使用 `pinia-plugin-persistedstate` 对需要跨会话保存的状态（如用户偏好）进行本地存储。

---

## 5. UI 与样式

-   **UI 库**: `@nuxt/ui` 提供了丰富的基础组件，是构建界面的首选。
-   **全局定制**: 在 `app.config.ts` 文件中可以对 `@nuxt/ui` 的颜色、圆角、边距等设计令牌 (Design Tokens) 进行全局定制，以实现统一的视觉风格。
-   **局部调整**: 对于单个组件的微调，直接在组件上使用 Tailwind CSS 的功能类。
-   **图标**: 使用 `@nuxt/icon` 模块，可以通过 `<UIcon name="i-heroicons-..." />` 的方式方便地使用 [Iconify](https://icones.js.org/) 的海量图标。

---

## 6. 开发指南

详细的开发规范和操作指南见：
- [前端开发规范](../frontend/CONTRIBUTING.md)
- [模块化开发指南](./MODULAR_DEVELOPMENT.md)

### 关键要点

- **SSR 优先**: 使用 `useApiData()` 获取数据，支持服务端渲染
- **避免 Hydration Mismatch**: 客户端特定组件必须用 `<ClientOnly>` 包裹
- **类型安全**: 全面使用 TypeScript，确保端到端类型安全

---

*本文档将随着系统的演进持续更新。如有疑问或建议，请提交Issue或联系开发团队。* 