# Social Insights Hub

社交媒体数据智能分析平台。聚合抖音、微博、B站、小红书、快手、知乎、贴吧等平台数据，通过 LLM 进行筛选、实体提取、情感分析和竞品分析，提供项目化的监控与报告。

## 技术栈

| 层 | 选型 | 说明 |
|---|------|------|
| 后端框架 | FastAPI + Python 3.11+ | 异步优先 |
| 数据库 | PostgreSQL 16 + SQLAlchemy 2.0 (async) | Alembic 迁移 |
| 前端框架 | Nuxt 4 + Vue 3 + TypeScript | Nuxt Layers 模块化 |
| UI 库 | @nuxt/ui v4 + Tailwind CSS v4 | 基于 Reka UI |
| 状态管理 | Pinia | 持久化存储 |
| AI/LLM | LangChain 1.0+ + DeepSeek API | 分析链 |
| 任务队列 | Celery + Redis | 异步处理 |
| 认证 | JWT (后端) + nuxt-auth-utils (前端) | RBAC 权限控制 |
| 图表 | ECharts | 必须用 ClientOnly 包装 |
| 部署 | Docker Compose + Nginx | 开发/生产双配置 |
| 包管理 | uv (后端) / pnpm (前端) | monorepo |

## 项目类型

类型：多 tier

| Tier | 目录 | 角色 |
|:-----|:-----|:-----|
| 后端 | backend/ | FastAPI + Python 3.11+, Celery Workers, LangChain |
| 前端 | frontend/ | Nuxt 4 + Vue 3 + TypeScript |

每个 tier 有独立的 `CLAUDE.md` 文件，定义 tier 专属的技术栈、构建命令和编码约定。Tier 约定优先于本文件中的同名约定。

## 项目结构

- `/backend` - FastAPI 后端应用 → 详见 `backend/CLAUDE.md`
- `/frontend` - Nuxt 前端应用 → 详见 `frontend/CLAUDE.md`
- `/docs` - 项目文档

## 模块结构

### 后端模块 (backend/src/)

| 模块 | 职责 |
|------|------|
| auth/ | JWT 认证、用户注册登录、令牌管理 |
| rbac/ | 角色权限管理，代码驱动启动时自动同步 |
| users/ | 用户 CRUD、角色分配 |
| social_media/monitors/ | 监测项目管理，平台初始化 |
| social_media/tasks/ | 数据采集任务管理，多平台适配器 |
| social_media/analysis/ | LLM 分析链、批处理、成本追踪 |
| langchain/ | DeepSeek LLM 集成，筛选/提取/归一化/情感分析链 |
| agent/ | 外部爬虫代理 API，API Key 认证 |

每个模块标准结构: `models.py` -> `schemas.py` -> `service.py` -> `router.py` (按需 `dependencies.py`, `tasks.py`, `utils.py`)

### 前端 Layers (frontend/layers/)

| Layer | 职责 |
|-------|------|
| ui-kit/ | 共享 UI 基础组件 |
| auth/ | 登录注册、认证状态管理 |
| rbac/ | 角色权限管理界面 |
| users/ | 用户管理界面 |
| social-media/ | 监测/任务/分析界面 (含 monitors/, tasks/, analysis/, types/) |

### 前端核心文件

| 文件 | 职责 |
|------|------|
| composables/useApi.ts | 统一 API 请求 (apiRequest + useApiData) |
| composables/usePermissions.ts | 权限检查 |
| config/routes.ts | 统一路由权限配置 |
| config/permissions.ts | 权限常量定义 (与后端一致) |
| middleware/route-guard.global.ts | 全局路由守卫 |
| plugins/auth-init.client.ts | 认证初始化 |
| server/api/v1/[...].ts | API 代理 (内联认证逻辑) |

## 核心编码约定

### 后端

- Pydantic 模型**必须**继承 `src.schemas.CustomBaseModel`，禁止直接继承 `pydantic.BaseModel`
- I/O 操作**必须**使用 `async def`；CPU 密集型用 `src.utils.run_cpu_bound_task`
- API 端点**必须**包含 `response_model`, `status_code`, `tags`, `summary`
- 外键关系**必须**建立双向 ORM 关系 (`back_populates`)
- 表名小写蛇形复数，时间戳字段 `_at` 后缀，日期字段 `_date` 后缀
- 使用 `HTTPException` 处理业务错误，直接返回业务数据让框架序列化
- SQL 优先处理复杂查询，Pydantic 负责 API 边界校验

### 前端

- API 调用**必须**使用 `composables/useApi.ts`（`apiRequest` / `useApiData`），禁止裸 `$fetch` 或 `useFetch`
- 动态内容**必须**用 `<ClientOnly>` 包装并提供有意义的 fallback
- SSR 数据获取优先用 `useApiData()`，避免仅在 `onMounted` 获取
- 渲染函数中从 `#components` 导入组件，禁止 `resolveComponent`
- 导航用组件的 `to` 属性，禁止 `onClick: () => navigateTo()`
- Options API Store 比 Setup Store 更 SSR 友好

### 权限系统

- 后端定义: `src/rbac/init_data.py` 中 `*create_module_permissions("module", ["access", "read", "write"])`
- 前端常量: `frontend/config/permissions.ts`
- 路由权限: `frontend/config/routes.ts` 中的 `ROUTE_CONFIG`
- 重启服务后自动同步到数据库，无需手动迁移

## 开发命令

| 命令 | 说明 |
|------|------|
| `pnpm setup` | 首次安装所有依赖 |
| `pnpm dev` | 启动完整开发环境 (自动迁移+初始化) |
| `pnpm dev:stop` | 停止所有服务 |
| `pnpm be:lint` | 后端 lint + 格式化 (ruff) |
| `pnpm be:test` | 后端测试 (pytest) |
| `pnpm fe:typecheck` | 前端类型检查 |
| `pnpm fe:lint` | 前端 lint |
| `pnpm be:migrate:make "描述"` | 创建数据库迁移 |
| `pnpm be:migrate:up` | 执行数据库迁移 |
| `pnpm be:add <package>` | 添加后端依赖 |
| `pnpm fe:add <package>` | 添加前端依赖 |

> 首次 `pnpm dev` 自动创建数据库表、基础权限和角色数据、默认管理员账号 (admin/admin123)

## 注意事项

- Nuxt 锁定 4.1.0（4.1.1 存在 reka-ui 兼容性问题，暂不升级）
- 新增 Layer 必须在 `frontend/nuxt.config.ts` 的 `extends` 数组中注册
- 新增后端路由必须在 `backend/src/main.py` 中注册
- 后端使用 uv 管理依赖，前端使用 pnpm
- 后端命令在 Docker 容器内执行，前端命令在宿主机执行

## 代码修改原则

1. **优先编辑现有文件**，避免创建新文件
2. **不主动创建文档文件** (*.md) 除非明确要求
3. **遵循现有代码风格**，查看相邻文件了解规范
4. **保持简单** (KISS 原则)，避免过度工程化

## 必需执行的检查

完成代码修改后，必须运行：

- 后端: `pnpm be:lint` + `pnpm be:test`
- 前端: `pnpm fe:typecheck` + `pnpm fe:lint`

## 参考文档

- 系统架构: `docs/architecture.md`
- 后端 tier 约定: `backend/CLAUDE.md`
- 前端 tier 约定: `frontend/CLAUDE.md`
- 后端编码规范 (详细版): `backend/CODING_GUIDE.md`
- 前端编码规范 (详细版): `frontend/CODING_GUIDE.md`
- 模块开发流程: `docs/MODULAR_DEVELOPMENT.md`
- 权限系统原理: `docs/PERMISSION_MANAGEMENT.md`
- 配置管理: `docs/CONFIGURATION.md`
- 开发工作流: `docs/WORKFLOW.md`
- 爬虫数据结构: `docs/CRAWLER_DATA_STRUCTURE.md`
- 分析平台 API: `docs/云端分析平台API规范.md`
