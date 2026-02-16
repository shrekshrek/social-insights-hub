# 系统架构

> Social Insights Hub 全栈架构文档。描述部署拓扑、模块边界、依赖关系和数据流。

---

## 1. 项目分层

项目分为 **前端 (frontend)** 和 **后端 (backend)** 两层，通过 REST API 通信。

```
┌───────────────────────────────────────────────────────┐
│  Frontend (Nuxt 4 + Vue 3 + TypeScript)               │
│                                                       │
│  Layers: auth | rbac | users | social-media | ui-kit  │
│  全局: useApi, usePermissions, route-guard, API Proxy  │
└──────────────────────┬────────────────────────────────┘
                       │ REST API (JWT in Authorization header)
┌──────────────────────▼────────────────────────────────┐
│  Backend (FastAPI + Python 3.11+)                      │
│                                                       │
│  模块: auth | rbac | users | social_media | langchain  │
│       | agent                                         │
│  异步: Celery Workers (LLM 分析管线)                    │
│  存储: PostgreSQL | Redis                              │
└───────────────────────────────────────────────────────┘
```

前端通过 `server/api/v1/[...].ts` 代理层统一注入 JWT 并转发请求到后端，前后端不直接共享代码或类型。

---

## 2. 部署拓扑

```
用户浏览器
    │ HTTPS
    ▼
Nuxt SSR (Port 3000)  ──HTTP──▶  FastAPI (Port 8000)
                                      │
                          ┌───────────┼───────────┐
                          ▼           ▼           ▼
                    PostgreSQL 16   Redis 7   DeepSeek API
                                      │
                                      ▼
                              Celery Worker (gevent×100)
```

| Docker 服务 | 端口 | 职责 |
|-------------|------|------|
| postgres_db | 5432 | 数据持久化 |
| redis | 6379 | Celery Broker + Result Backend |
| backend | 8000 | FastAPI API 服务 |
| celery-worker | — | 异步 LLM 任务执行 |
| frontend | 3000 | Nuxt SSR (开发环境为宿主机 pnpm dev) |

---

## 3. 后端模块

### 3.1 模块列表与依赖

```
                    ┌──────────────────────────┐
                    │   social_media/analysis   │
                    │  (分析编排, 报告聚合)      │
                    └─┬────┬────┬────┬────┬────┘
                      │    │    │    │    │
          ┌───────────┘    │    │    │    └───────────┐
          ▼                ▼    ▼    ▼                ▼
   ┌────────────┐  ┌──────────┐ ┌──────────┐  ┌───────────┐
   │  langchain  │  │ projects │ │  tasks   │  │   agent   │
   │ (LLM 引擎)  │  │ (项目)    │ │ (任务)    │  │ (爬虫代理) │
   └──────┬─────┘  └────┬─────┘ └────┬─────┘  └─────┬─────┘
          │              │            │              │
          │         ┌────┘      ┌─────┘         ┌────┘
          │         ▼           ▼               ▼
          │    ┌─────────┐ ┌─────────┐    tasks (模型+适配器)
          │    │  auth   │ │  rbac   │
          │    │ (认证)   │ │ (权限)   │
          │    └────┬────┘ └────┬────┘
          │         │           │
          ▼         ▼           ▼
     ┌─────────────────────────────┐
     │  基础设施 (config, database,  │
     │  redis, celery, middleware)  │
     └─────────────────────────────┘
```

箭头方向 = 依赖方向（A→B 表示 A 依赖 B）。反向依赖禁止。

### 3.2 模块边界

| 模块 | 职责 | 数据所有 | 公开接口 | API 前缀 | 依赖 |
|------|------|----------|----------|----------|------|
| auth | JWT 认证, 登录注册, 令牌黑名单 | `users` | `get_current_user()`, `User` 模型 | `/api/v1/auth` | 基础设施 |
| rbac | 角色权限 CRUD, 代码驱动同步 | `roles`, `permissions`, 关联表 | `require_permission()`, `create_module_permissions()` | `/api/v1/rbac` | auth |
| users | 用户 CRUD, 角色分配 | — (操作 auth.users) | — | `/api/v1/users` | auth, rbac |
| projects | 项目管理, 平台初始化 | `social_projects`, `platforms` | `check_project_access()`, 模型 | `/api/v1/social-media/projects` | auth, rbac |
| tasks | 任务管理, 多平台适配器, 帖子/评论存储 | `data_tasks`, `social_posts`, `social_comments` | 模型, `task_crud`, `adapters` | `/api/v1/social-media/tasks` | auth, rbac, projects |
| analysis | LLM 分析编排, 批处理, 成本追踪 | `post_analyses`, `analysis_jobs`, `project_analysis_snapshots` | — (终端模块) | `/api/v1/social-media/analysis` | auth, rbac, projects, tasks, langchain |
| langchain | DeepSeek LLM 实例, 分析链 | — (纯计算) | `get_deepseek_chat()`, 各 chain | — (无 API) | 基础设施 (config) |
| agent | 爬虫代理 API, 数据上传 | — (操作 tasks 数据) | — (面向爬虫) | `/api/v1/agent` | tasks |

### 3.3 LangChain 链清单

| 链 | 输入 | 输出 | 调用方 |
|----|------|------|--------|
| screening_chain | 帖子内容+关键词 | spam/value/relevance/sentiment 分数 | screening_tasks |
| post_extraction_chain | 帖子内容+关键词 | 实体+观点+摘要 | deep_analysis_tasks |
| comment_extraction_chain | 评论内容+关键词 | 评论实体+观点 | deep_analysis_tasks |
| entity_normalization_chain | 实体列表 | 去重+归一化实体 | aggregation/entity |
| opinion_normalization_chain | 观点列表 | 去重+归一化观点 | aggregation/opinion |
| category_normalization_chain | 观点分类 | 归一化分类 | aggregation/opinion |
| attribute_normalization_chain | 实体属性 | 归一化属性 | aggregation/entity |
| project_entity_merge_chain | 多任务实体 | 项目级实体合并 | project_snapshot |
| project_snapshot_reports_chain | 聚合数据 | 项目级报告摘要 | project_snapshot |

---

## 4. 前端 Layers

### 4.1 全局基础设施 (app/)

| 文件 | 职责 |
|------|------|
| `composables/useApi.ts` | 统一 API 请求 (`apiRequest` + `useApiData`) |
| `composables/usePermissions.ts` | 动态 RBAC 权限检查 |
| `middleware/route-guard.global.ts` | 路由守卫 (认证+权限) |
| `plugins/auth-init.client.ts` | 客户端认证初始化 |
| `server/api/v1/[...].ts` | API 代理 (JWT 注入, 转发到后端) |
| `config/routes.ts` | 路由权限配置 |
| `config/permissions.ts` | 权限常量 (与后端一致) |

### 4.2 业务 Layers

| Layer | 职责 | 关键文件 |
|-------|------|----------|
| auth | 登录, 注册, 认证状态 | `useAuthApi.ts`, `stores/user.ts` |
| rbac | 角色/权限管理界面 | `useRbacApi.ts`, RoleForm/Detail 组件 |
| users | 用户管理界面 | `useUsersApi.ts`, UserForm/Detail 组件 |
| ui-kit | 共享 UI 组件 (无业务) | — |
| social-media | 项目/任务/分析全流程 | 见下表 |

### 4.3 social-media Layer 子模块

| 子模块 | 页面 | Composables | 关键组件 |
|--------|------|-------------|----------|
| projects/ | 列表, 创建, 详情, 快照分析 | usePlatforms, useSocialProjects | TaskComparisonSlideover |
| tasks/ | 列表, 创建, 详情, 数据上传 | useTasks, usePosts, useJSONUpload | — |
| analysis/ | — (嵌入 task/project 详情页) | useAnalysis, useAnalysisStats, useTokenUsage | TaskAnalysisReport, IpaChart, ContextGraphChart, CompetitorRadarChart, TimeDistributionChart, SpamRatioBar, PostListModal 等 |

---

## 5. 数据模型

### 5.1 ER 关系

```
User ──1:N──▶ UserRole ◀──N:1── Role ──1:N──▶ RolePermission ◀──N:1── Permission

User ──1:N──▶ SocialProject (owner)
User ──M:N──▶ SocialProject (participants)

Platform ──1:N──▶ SocialProject
SocialProject ──1:N──▶ DataTask
Platform ──1:N──▶ DataTask

DataTask ──1:N──▶ SocialPost ──1:1──▶ PostAnalysis
SocialPost ──1:N──▶ SocialComment

SocialProject ──1:N──▶ AnalysisJob ◀──N:1── DataTask (可 NULL)
User ──1:N──▶ AnalysisJob

SocialProject ──1:N──▶ ProjectAnalysisSnapshot
```

### 5.2 核心表

| 表 | 所属模块 | 说明 |
|----|----------|------|
| users | auth | 用户基础信息 |
| roles, permissions, role_permissions, user_roles | rbac | RBAC 权限体系 |
| platforms | projects | 社交平台定义 (7 个平台) |
| social_projects, social_project_participants | projects | 监控项目 |
| data_tasks | tasks | 数据采集任务 |
| social_posts, social_comments | tasks | 帖子/评论数据 |
| post_analyses | analysis | 帖子分析结果 (1:1 SocialPost) |
| analysis_jobs | analysis | 分析任务状态+成本记录 |
| project_analysis_snapshots | analysis | 项目级分析快照 (不可变) |

---

## 6. 分析管线

### 6.1 任务级分析

```
数据采集/上传
      ▼
Stage 1: 初筛 (screening_tasks)        ← LLM: deepseek-chat
         spam/value/relevance/sentiment
      ▼
Stage 2: 深度分析 (deep_analysis_tasks)  ← LLM: deepseek-chat/reasoner
         帖子实体+观点, 评论实体+观点
      ▼
Stage 3: 聚合 (aggregation_tasks)       ← LLM: 归一化
         实体/观点归一化, NSR, SERP, 四象限, IPA, 竞品, 时间分布
      ▼
写入 DataTask.analysis_result (JSON)
```

### 6.2 项目级分析

```
选择多个 DataTask
  → Stage 1 (同步): 统计聚合 → 创建 ProjectAnalysisSnapshot
  → Stage 2 (Celery): 跨任务实体/观点合并 (LLM)
  → Stage 3 (Celery): 项目级报告摘要 (LLM)
  → 更新 ProjectAnalysisSnapshot.result_data
```

### 6.3 自动分析

```
Agent 上传数据 → auto_analyze=True → screening → deep → aggregation (串行)
```

---

## 7. 跨模块数据流

### 7.1 采集到报告

```
外部爬虫 ──POST──▶ agent/router
                      │
                agent/service.upload_result()
                      │ tasks/adapters 转换 + tasks/crud 写入
                      ▼
               SocialPost, SocialComment
                      │ auto_analyze
                      ▼
          analysis/celery_tasks (screening → deep → aggregation)
                      │ langchain/chains/* (LLM)
                      ▼
               DataTask.analysis_result
                      │ 前端读取
                      ▼
               TaskAnalysisReport.vue
```

### 7.2 权限贯穿

```
前端 route-guard → usePermissions() → userStore.permissions
      ↓
server/api/v1/[...].ts → 注入 Authorization header
      ↓
后端 router → Depends(get_current_user) + Depends(require_permission())
      ↓
service → check_project_access(user_id, project_id)
```

---

## 8. 关键架构模式

| 模式 | 应用 |
|------|------|
| Service Layer | 业务逻辑集中在 `service.py`, router 只做校验和路由 |
| Dependency Injection | FastAPI `Depends()` 管理 DB session, 当前用户, 权限 |
| Adapter Pattern | `tasks/adapters/` 处理各平台数据格式差异 |
| Async Task Chain | Celery 编排多阶段分析管线 |
| Snapshot Pattern | `ProjectAnalysisSnapshot` 保存不可变报告历史 |
| Cost Tracking | 每次 LLM 调用记录 token 用量+费用 |
| Code-Driven RBAC | 权限在代码中定义, 启动时自动同步到数据库 |
| API Proxy | 前端统一注入 JWT, 转发到后端 |
| Nuxt Layers | 按业务领域隔离前端代码 |
