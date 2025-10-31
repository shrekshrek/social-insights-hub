# Nuxt.js 前端开发指南

本指南旨在为全栈项目的前端部分提供一套清晰、统一的开发规范。前端架构选用 [Nuxt Layers](https://nuxt.com/docs/getting-started/layers)，以实现与模块化后端（见 [backend/CONTRIBUTING.md](../backend/CONTRIBUTING.md)）在设计理念上的对称与统一。

---

## 目录

1. [核心架构：Nuxt Layers](#1-核心架构nuxt-layers)
2. [项目结构](#2-项目结构-project-structure)
3. [Layer 开发规范](#3-layer-开发规范)
4. [UI 与样式](#4-ui-与样式-nuxtui-v3)
5. [状态管理](#5-状态管理-pinia)
6. [认证与权限](#6-认证与权限-nuxt-auth-utils--rbac)
7. [SSR 渲染与数据获取 ⚠️](#7-ssr-渲染与数据获取-⚠️)
8. [API 通信与统一处理](#8-api-通信与统一处理)
9. [客户端渲染与数据可视化](#9-客户端渲染与数据可视化)
10. [API认证处理](#10-api认证处理)

---

### 1. 核心架构：Nuxt Layers

我们采用 Nuxt Layers 实现前端的模块化和领域驱动设计（DDD）。

#### 核心架构特性

- **架构对称**: 每个前端业务模块作为一个独立的 Layer，与后端 FastAPI 的领域模块一一对应（如 `frontend/layers/auth` 对应 `backend/src/auth`）。
- **关注点分离**:
    - **业务 Layer**: 封装特定业务领域的所有功能，如 `layers/auth`, `layers/rbac`。
    - **UI Layer**: 创建一个共享的 `layers/ui-kit`，存放全局复用的基础组件（如按钮、卡片、输入框等）。

---

### 2. 项目结构 (Project Structure)

基于 Nuxt Layers 的前端架构如下：

```
frontend/
├── layers/                    # 业务层架构 (按需创建)
│   ├── auth/                 # 认证模块 (项目必需)
│   │   ├── components/       # 登录表单、注册表单等
│   │   ├── pages/           # /login, /register, /reset-password
│   │   ├── stores/          # 用户状态管理
│   │   ├── composables/     # useAuthApi() 等
│   │   ├── server/          # 认证相关的BFF API
│   │   └── nuxt.config.ts   # 该层配置
│   ├── [domain]/            # 业务模块 (按需创建)
│   │   ├── components/      # 领域相关组件
│   │   ├── pages/           # 领域相关页面
│   │   ├── stores/          # 领域状态管理 (可选)
│   │   ├── composables/     # 领域API封装 (如 useDomainApi)
│   │   └── ...              # 按需添加其他目录
│   └── ui-kit/              # UI组件库 (推荐)
│       ├── components/      # 可复用的基础组件
│       └── nuxt.config.ts   # UI层配置
├── pages/                   # 全局页面 (必需: index.vue)
├── layouts/                 # 全局布局 (推荐: default.vue)
├── components/              # 全局组件 (可选)
├── composables/             # 全局组合式函数 (核心)
│   ├── useApi.ts           # 统一API请求 (必需)
│   ├── useCharts.ts        # 图表组合函数 (可选)
│   ├── useLoading.ts       # 加载状态管理 (推荐)
│   └── useFormValidation.ts # 表单验证 (推荐)
├── config/                  # 配置文件 (推荐)
│   ├── routes.ts           # 统一路由权限配置（页面约定+功能配置）(必需)
│   └── permissions.ts      # 权限常量定义 (必需)
├── middleware/              # 全局中间件 (推荐)
│   └── route-guard.global.ts # 统一路由守卫 (必需)
├── plugins/                 # 插件 (按需)
│   ├── auth-init.client.ts # 认证初始化 (必需)
│   └── error-handler.client.ts # 全局错误处理 (推荐)
├── server/                  # 全局服务端API (可选)
│   └── api/v1/[...].ts     # API代理中间件 (必需)
├── types/                   # TypeScript 类型定义 (推荐)
├── assets/                  # 编译时资源 (可选)
├── public/                  # 静态资源 (可选)
├── nuxt.config.ts          # 主配置文件 (必需)
├── app.config.ts           # 应用配置 (推荐)
├── error.vue               # 全局错误页面 (推荐)
└── package.json            # 依赖配置 (必需)
```

**架构演进指导**：

- **起步阶段**: 新功能可以直接在全局 `pages/` 和 `components/` 中开发
- **模块化时机**: 当某个业务领域有 3+ 个页面或组件时，考虑创建专门的 Layer
- **Layer 创建标准**: 
  - 功能相对独立，有清晰的业务边界
  - 包含多个相关的页面、组件或API
  - 需要独立的状态管理
- **文件创建原则**: 从最小可用结构开始，根据业务复杂度逐步添加目录和文件

**主配置文件 `nuxt.config.ts`**:

通过 `extends` 属性来组合所有 layers。Nuxt 会智能地将根目录及所有 layers 的配置进行深度合并。

```typescript
export default defineNuxtConfig({
  // 按顺序组合 layers，后面的会覆盖前面的
  extends: [
    './layers/ui-kit',
    './layers/auth',
  ],
  
  // 可以在此定义全局配置
})
```

---

### 3. Layer 开发规范

- **自包含原则**: 每个 Layer 都应是一个功能完整的迷你 Nuxt 应用，包含自己的页面、组件、组合式函数和状态。
- **职责划分**: 
  - **Layers 封装"业务能力"**: 提供可复用的"能力单元"
  - **主应用编排"业务流程"**: 组合各个 Layers 的能力，构建最终的应用页面
- **组件作用域**:
    - 业务强相关的组件，保留在各自的业务 Layer 中
    - 纯 UI、可跨业务复用的组件，应抽离到 `layers/ui-kit` 中
- **组合式函数**:
    - **全局组合式函数**: 跨业务模块复用的工具函数，放在根目录的 `composables/`
    - **业务组合式函数**: 与特定业务逻辑相关的函数，放在对应 Layer 的 `composables/`
- **Layer 专属后端接口**: 每个 Layer 都可以拥有自己的 `server/` 目录，用于创建与该领域紧密相关的 BFF (Backend for Frontend) API 接口
- **资源路径处理**: 在 Layer 中引用静态资源时，使用 `#assets` 别名或 `import.meta.url` 来构造绝对路径，确保路径在合并后依然正确

#### Layer 注册（重要）

新创建的 Layer 必须在 `nuxt.config.ts` 中注册才能生效：


#### 组件自动导入

**分层注册策略**：
- **全局组件**：根目录 `components/` 和 `layers/ui-kit/components/` 在所有地方自动导入
- **Layer组件**：各Layer的 `components/` 仅在本Layer内自动导入
- **跨Layer使用**：需要显式导入，如 `import RoleForm from '~/layers/rbac/components/RoleForm.vue'`

**配置示例**：
```typescript
// 主 nuxt.config.ts - 只注册全局组件
components: [
  { path: './components', pathPrefix: false },           // 项目全局组件
  { path: './layers/ui-kit/components', pathPrefix: false }, // UI组件库
]

// layers/*/nuxt.config.ts - Layer内组件自动导入
components: [
  { path: './components', pathPrefix: false }  // 仅本Layer内可用
]
```

#### 页面数据获取

**核心原则**：优先使用 SSR 友好的数据获取方式（`useApiData` 或 `await api.getData()`），避免仅在 `onMounted` 中获取数据导致页面刷新时数据丢失。

#### 嵌套路由

**关键要求**：
- **必须**在父页面中使用 `<NuxtPage>` 组件来渲染子页面
- 例如：`pages/users/[id].vue` 要渲染 `pages/users/[id]/edit.vue`，父页面必须包含 `<NuxtPage>`
- **建议**使用条件渲染避免同时显示父页面内容和子页面内容

---

### 4. UI 与样式 (`@nuxt/ui v4`)

-   **技术选型**: 使用 `@nuxt/ui v4` 作为核心 UI 库，基于 `Tailwind CSS v4` 和 `Reka UI` 构建
-   **版本要求**: **必须使用 v4 版本**，已从 Headless UI 迁移到 Reka UI
-   **核心优势**:
    -   与 Nuxt 无缝集成，组件自动导入
    -   开箱即用的深色模式
    -   通过 `app.config.ts` 进行全局主题定制
-   **使用规范**:
    1.  **全局定制**: 在根目录的 `app.config.ts` 中修改颜色、边距、圆角等
    2.  **局部覆盖**: 使用 `class` 属性添加 `Tailwind CSS` 的功能类
    3.  **组件使用**: 直接使用 `<UButton>`, `<UCard>` 等组件，无需手动导入

---

### 5. 状态管理 (`Pinia`)

- **Pinia 优先**: 采用 [Pinia](https://pinia.vuejs.org) 作为首选的状态管理库
- **模块化 Store**: 每个 Store 归属于其业务 Layer，定义在 `stores/` 目录下，实现状态的领域隔离
- **状态持久化**: 使用 `pinia-plugin-persistedstate` 将需要持久化的 Store 存储在本地

---

### 6. 认证与权限 (`nuxt-auth-utils` + RBAC)

-   **技术选型**: 采用 `nuxt-auth-utils` 模块处理用户认证和会话管理，结合 RBAC 系统实现细粒度权限控制
-   **工作模式**: 通过加密的会话Cookie管理用户状态，使用 `useUserSession()` 组合式函数访问认证状态和权限信息

#### 核心架构

**关键组件**：
- **认证初始化**: `plugins/auth-init.client.ts` 统一处理应用启动时的认证状态和权限预加载
- **3层路由守卫**: `middleware/route-guard.global.ts` 实现3层权限检查
- **统一权限配置**: `config/routes.ts` 中 `ROUTE_CONFIG` 统一管理所有路由权限与导航
- **权限常量定义**: `config/permissions.ts` 与后端完全一致的权限常量定义
- **权限检查逻辑**: `composables/usePermissions.ts` 核心权限检查和常用封装
- **API处理**: `composables/useApi.ts` 统一处理API请求和401错误
- **错误处理**: `plugins/error-handler.client.ts` 全局错误捕获和处理

**设计特点**：统一配置、简单清晰、性能优化、极简开发

#### 使用规范

- **认证状态**: `useUserSession()` 获取登录状态和用户数据
- **权限检查**: `usePermissions()` 提供核心权限检查和常用封装
- **统一路由保护**: 所有权限检查在 `ROUTE_CONFIG` 中统一配置
- **超管快速通道**: 管理员无需等待权限加载，直接访问
- **错误处理**: 401错误自动登出，权限不足自动重定向

---

### 7. SSR 渲染与数据获取 ⚠️

> **重要提醒**: SSR 渲染问题是 Nuxt 开发中的**常见且核心**问题，时刻需要留意！

#### 核心原则

**SSR/CSR 一致性**: 服务端渲染和客户端渲染的 HTML 必须完全一致，否则会导致 Hydration Mismatch。

#### 数据获取方法选择

| 场景 | 推荐方法 | 原因 |
|------|----------|------|
| 简单 API 调用 | `useFetch('/api/data')` | 自动处理 SSR/CSR，防止重复请求 |
| 复杂数据处理 | `useAsyncData('key', () => ...)` | 支持自定义逻辑和数据转换 |
| 客户端操作 | `$fetch('/api/data')` | 表单提交、按钮点击等事件驱动 |
| Store 集成 | `onMounted` + Store | 避免 Pinia SSR hydration 问题 |

#### 常见问题与解决方案

**1. 动态内容 Hydration Mismatch**
```vue
<!-- ❌ 错误：服务端无数据，客户端有数据 -->
<UCheckbox v-for="item in permissions" :checked="item.selected" />

<!-- ✅ 正确：使用 ClientOnly 包装动态内容 -->
<ClientOnly>
  <template #fallback><div>正在加载...</div></template>
  <UCheckbox v-for="item in permissions" :model-value="item.selected" />
</ClientOnly>
```

**2. Store 数据 Hydration 问题**
```typescript
// ❌ Setup Store 可能导致 SSR hydration 问题
export const useStore = defineStore('name', () => ({ data: ref([]) }));

// ✅ Options API Store 更 SSR 友好
export const useStore = defineStore('name', {
  state: () => ({ data: [] })
});
```

#### 必须使用 ClientOnly 的场景

- **复杂动态内容**: 分页、搜索、图表、复选框列表
- **第三方库**: ECharts、富文本编辑器等仅限客户端的库
- **浏览器 API**: 使用 `window`、`localStorage`、`document` 等
- **用户交互状态**: 依赖用户操作的 UI 状态

#### ClientOnly 最佳实践

```vue
<ClientOnly>
  <!-- 1. 提供有意义的 fallback -->
  <template #fallback>
    <div class="flex items-center justify-center py-8">
      <UIcon name="i-heroicons-arrow-path" class="animate-spin h-6 w-6" />
      <span class="ml-2">正在加载数据...</span>
    </div>
  </template>
  
  <!-- 2. 包装完整的功能块 -->
  <div class="space-y-4">
    <UTable :data="tableData" :columns="columns" />
    <UPagination v-model:page="currentPage" :total="total" />
  </div>
</ClientOnly>
```

#### 避免 Hydration Mismatch 的关键规则

1. **禁止随机值**: 不在模板中使用 `Math.random()`、`Date.now()` 等
2. **条件渲染一致**: 确保服务端和客户端的 `v-if` 条件完全相同
3. **数据初始化**: 使用 `watch` 而非仅 `onMounted` 初始化状态
4. **异步数据**: 优先使用 `useFetch`/`useAsyncData`，避免手动异步获取

### SSR 响应式参数传递（比如分页数据处理）

- **推荐**使用封装的业务 API 方法，支持响应式参数
- **必须**在 `query` 中直接传递响应式变量，让 Nuxt 自动监听
- **必须**使用动态 `key` 确保不同参数独立缓存

```typescript
// ✅ 最佳实践：使用封装的业务 API 方法
const usersApi = useUsersApi();
const { data } = usersApi.getUsers({
  page: currentPage,      // 响应式变量，自动监听变化
  page_size: pageSize     // 响应式变量，自动监听变化
});

---

### 8. API 通信与统一处理

**核心工具**: 使用全局 `composables/useApi.ts` 进行所有后端 API 交互。

#### 主要方法
- **`apiRequest()`**: 基于 `$fetch`，用于客户端操作（表单提交、登录等）
- **`useApiData()`**: 基于 `useFetch`，用于数据获取，支持 SSR

#### 统一处理特性
- **路径管理**: 通过 `nuxt.config.ts` 中的 `runtimeConfig.public.apiBase` 统一管理 API 基础路径
- **错误处理**: 自动解析 HTTP 错误响应，显示统一的 Toast 通知
- **认证处理**: 401错误自动触发登出并重定向到登录页
- **业务封装**: 在各 Layer 的 composables 中封装特定的业务 API

---

### 9. 客户端渲染与数据可视化

#### 数据可视化: `ECharts`

**基本使用规范**：
- **`<ClientOnly>` 组件**: 包裹所有仅限客户端的库，特别是 `ECharts` 图表
- **Fallback 内容**: 为 `<ClientOnly>` 提供 `fallback` 内容，提升用户体验
- **useCharts 组合函数**: 使用项目提供的 `useCharts` 组合函数，而非直接调用 ECharts API

**参考示例**：查看 `pages/charts.vue` 获取完整的使用示例。

**最佳实践**：
```vue
<ClientOnly>
  <template #fallback>
    <div class="flex items-center justify-center h-64">
      <UIcon name="i-heroicons-arrow-path" class="animate-spin h-8 w-8" />
      <span class="ml-2">正在加载图表...</span>
    </div>
  </template>
  
  <div ref="chartContainer" class="w-full h-64"></div>
</ClientOnly>
```

---

### 10. API认证处理

**处理方式**: 认证逻辑已内联到 `server/api/v1/[...].ts`

**功能**：简化的API认证检查，自动处理公开路径和认证路径。

```typescript
// server/api/v1/[...].ts - 内联认证逻辑
export default defineEventHandler(async (event) => {
  const cleanPath = getApiPath(event)
  
  // 简化的公开路径检查
  const publicPaths = [
    '/auth/login', 
    '/auth/register', 
    '/auth/token', 
    '/auth/logout'
  ]
  const needsAuth = cleanPath && !publicPaths.some(p => 
    cleanPath === p || cleanPath.startsWith(p + '/')
  )
  
  // 认证检查逻辑...
})
```

**优势**：
- 无需单独的配置文件，减少维护成本
- 认证逻辑更加直接易懂
- 新增公开路径直接在代理中修改

---

### 11. 新模块添加流程

完整的模块开发流程见 [`docs/MODULAR_DEVELOPMENT.md`](../docs/MODULAR_DEVELOPMENT.md)

快速步骤：
1. 后端定义权限：`*create_module_permissions("module", ["access", "read"])`
2. 创建前端 Layer：在 `layers/` 目录下创建模块结构
3. 配置路由权限：在 `config/routes.ts` 中添加权限映射
4. 重启服务：`pnpm dev` 自动同步权限

---

### 12. 本地开发工作流

1. **启动开发环境**:
   - 确保 Docker Desktop 正在运行
   - 在项目根目录执行 `pnpm dev` 启动完整开发环境

2. **前端开发**:
   - **安装依赖**: `pnpm fe:install`
   - **启动开发服务器**: `pnpm fe:dev`
   - **添加依赖**: `pnpm fe:add <package-name>`
   - **构建**: `pnpm fe:build`

3. **访问应用**:
   - 前端应用位于 [http://localhost:3000](http://localhost:3000)
   - 后端 API 文档位于 [http://localhost:8000/docs](http://localhost:8000/docs)

4. **开发流程**:
   - 使用统一处理工具（`useApi`, `useFormValidation` 等）进行开发
   - 遵循 Layer 架构，将业务逻辑封装在对应的 Layer 中
   - 使用 `@nuxt/ui` 组件库构建界面
