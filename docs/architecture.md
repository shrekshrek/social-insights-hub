# 系统架构

> Social Insights Hub 全栈架构文档。描述部署拓扑、模块边界、依赖关系和数据流。

---

## 1. 项目分层

项目分为 **前端 (frontend)** 和 **后端 (backend)** 两层，通过 REST API 通信。

```
┌───────────────────────────────────────────────────────┐
│  Frontend (Nuxt 4 + Vue 3 + TypeScript)               │
│                                                       │
│  Layers: ui-kit | auth | users | rbac | jobs |         │
│          social-media | news-media | strategies |       │
│          knowledge-base                                │
│  全局: useApi, usePermissions, route-guard, API Proxy  │
└──────────────────────┬────────────────────────────────┘
                       │ REST API (JWT in Authorization header)
┌──────────────────────▼────────────────────────────────┐
│  Backend (FastAPI + Python 3.11+)                      │
│                                                       │
│  模块: auth | rbac | users | social_media | news_media │
│       | strategies | knowledge_base | jobs | llm |     │
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
   │    llm     │  │ monitors │ │  tasks   │  │   agent   │
   │ (LLM 引擎)  │  │ (监测)    │ │ (任务)    │  │ (爬虫代理) │
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
| monitors | 监测项目管理, 平台初始化 | `social_monitors`, `platforms` | `check_monitor_access()`, 模型 | `/api/v1/social-media/monitors` | auth, rbac |
| tasks | 任务管理, 多平台适配器, 原文/评论存储 | `social_tasks`, `social_posts`, `social_comments` | 模型, `task_crud`, `adapters` | `/api/v1/social-media/tasks` | auth, rbac, monitors |
| analysis | LLM 分析编排, 批处理, 成本追踪 | `post_analysis`, `analysis_jobs`, `analysis_slices` | — (终端模块) | `/api/v1/social-media/analysis` | auth, rbac, monitors, tasks, llm |
| jobs | 跨渠道 AnalysisJob 管理 | `analysis_jobs` | CRUD, factory | `/api/v1/jobs` | auth |
| llm | DeepSeek LLM 实例, 分析链 | — (纯计算) | `get_deepseek_chat()`, 各 chain | — (无 API) | 基础设施 (config) |
| agent | 爬虫代理 API, 数据上传 | — (操作 tasks 数据) | — (面向爬虫) | `/api/v1/agent` | tasks |
| news_media | 新闻监测与采集 | `news_monitors`, `news_tasks`, `news_articles` | 模型, service | `/api/v1/news-media` | auth, rbac, jobs, llm |
| strategies | 策略研究引擎 | `strategies`, `strategy_slices` | 模型, service | `/api/v1/strategies` | auth, social_media, news_media |
| knowledge_base | 市场知识库, 文档向量化 | `knowledge_documents`, `knowledge_chunks` | 模型, service | `/api/v1/knowledge-base` | auth |

### 3.3 LLM 分析链

所有分析链位于 `backend/src/llm/chains/`，按渠道分目录组织（`social_media/` / `news/` / `strategy/`）。链的数量与职责变动较频繁，权威清单见各模块 CLAUDE.md：

- 社媒链（screening / 深度抽取 / 归一化 / 监测切片聚合）→ `backend/CLAUDE.md`
- 新闻链（tagging / insight）→ `backend/src/news_media/analysis/` 内源码
- 策略链（研究设计 / 探测审查 / 覆盖度 / brand_strategy 三层 / market_report 三层）→ `backend/src/strategies/CLAUDE.md`

每次 LLM 调用自动记录 token 用量和费用到 `AnalysisJob`（由 `src/jobs/` 统一管理）。

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
| jobs | 跨渠道分析任务列表 | `useJobs.ts` |
| social-media | 社媒监测/任务/分析 | 见下表 |
| news-media | 新闻监测/任务/分析 | `useNewsMonitors.ts`, `useNewsTasks.ts` |
| strategies | 策略研究全流程 | `useStrategies.ts` |
| knowledge-base | 市场知识库管理 | `useKnowledgeBase.ts` |

### 4.3 social-media Layer 子模块

| 子模块 | 页面 | Composables | 关键组件 |
|--------|------|-------------|----------|
| monitors/ | 列表, 创建, 详情, 切片洞察 | usePlatforms, useMonitors | TaskComparisonSlideover |
| tasks/ | 列表, 创建, 详情, 数据上传 | useTasks, usePosts, useJSONUpload | — |
| analysis/ | — (嵌入 task/monitor 详情页) | useAnalysis, useAnalysisStats, useTokenUsage | TaskAnalysisReport, IpaChart, ContextGraphChart, CompetitorRadarChart, TimeDistributionChart, SpamRatioBar, PostListModal 等 |

---

## 5. 数据模型

### 5.1 ER 关系

```
User ──1:N──▶ UserRole ◀──N:1── Role ──1:N──▶ RolePermission ◀──N:1── Permission

User ──1:N──▶ SocialMonitor (owner)
User ──M:N──▶ SocialMonitor (participants)

Platform ──1:N──▶ SocialTask
SocialMonitor ──1:N──▶ SocialTask

SocialTask ──1:N──▶ SocialPost ──1:1──▶ PostAnalysis
SocialPost ──1:N──▶ SocialComment

SocialMonitor ──1:N──▶ AnalysisSlice
AnalysisJob ──N:1──▶ SocialMonitor (可 NULL)
AnalysisJob ──N:1──▶ SocialTask (可 NULL)
AnalysisJob ──N:1──▶ NewsMonitor (可 NULL)
AnalysisJob ──N:1──▶ NewsTask (可 NULL)

NewsMonitor ──1:N──▶ NewsTask ──1:N──▶ NewsArticle
Strategy ──1:1──▶ SocialMonitor (可 NULL)
Strategy ──1:1──▶ NewsMonitor (可 NULL)
```

### 5.2 核心表

| 表 | 所属模块 | 说明 |
|----|----------|------|
| users | auth | 用户基础信息 |
| roles, permissions, role_permissions, user_roles | rbac | RBAC 权限体系 |
| platforms | monitors | 社交平台定义 (7 个平台) |
| social_monitors, social_monitor_participants | monitors | 社媒监测项目 |
| social_tasks | tasks | 社媒数据采集任务 |
| social_posts, social_comments | tasks | 原文/评论数据 |
| post_analysis | analysis | 原文分析结果 (1:1 SocialPost) |
| analysis_slices | analysis | 项目级分析切片 |
| analysis_jobs | jobs | 跨渠道分析任务状态+成本记录 |
| news_monitors, news_monitor_participants | news_media | 新闻监测项目 |
| news_tasks | news_media | 新闻采集任务 |
| news_articles | news_media | 新闻文章 |
| strategies, strategy_slices, strategy_participants | strategies | 策略研究 |
| knowledge_documents, knowledge_chunks | knowledge_base | 知识文档+向量嵌入 |

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
         原文实体+观点, 评论实体+观点
      ▼
Stage 3: 聚合 (aggregation_tasks)       ← LLM: 归一化
         实体/观点归一化, NSR, SERP, 四象限, IPA, 竞品, 时间分布
      ▼
写入 SocialTask.analysis_result (JSON)
```

### 6.2 项目级分析

```
选择多个 SocialTask
  → Stage 1 (同步): 统计聚合 + spam 分布计算 → 创建 AnalysisSlice
  → Stage 2 (Celery): 跨任务实体/观点合并 (LLM)，传递 spam_distribution
  → Stage 3 (Celery): 项目级报告摘要 (LLM)
  → 更新 AnalysisSlice.result_data
```

Stage 1 通过 outerjoin PostAnalysis 获取 spam_score，构建 `spam_map_by_key`（post_key → high/low），为每个实体/话题计算 4D spam 分布（`high_spam/low_spam × post/comment`）。Stage 2 归一化时累加传递该分布。

### 6.3 自动分析

```
Agent 上传数据 → auto_analyze=True → screening → deep → aggregation (串行)
```

---

## 7. 跨模块数据流

### 7.1 采集到报告（以社媒为例）

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
                      │ llm/chains/* (LLM)
                      ▼
               SocialTask.analysis_result
                      │ 前端读取
                      ▼
               TaskAnalysisReport.vue
```

news_media / strategies / knowledge_base 各有独立编排流程，详见对应模块 CLAUDE.md（`src/news_media/`、`src/strategies/`、`src/knowledge_base/`）。

### 7.2 权限贯穿

```
前端 route-guard → usePermissions() → userStore.permissions
      ↓
server/api/v1/[...].ts → 注入 Authorization header
      ↓
后端 router → Depends(get_current_user) + Depends(require_permission())
      ↓
service → check_monitor_access(user_id, monitor_id)
```

---

## 8. 关键架构模式

| 模式 | 应用 |
|------|------|
| Service Layer | 业务逻辑集中在 `service.py`, router 只做校验和路由 |
| Dependency Injection | FastAPI `Depends()` 管理 DB session, 当前用户, 权限 |
| Adapter Pattern | `tasks/adapters/` 处理各平台数据格式差异 |
| Async Task Chain | Celery 编排多阶段分析管线 |
| Slice Pattern | `AnalysisSlice` 保存不可变报告历史 |
| Cost Tracking | 每次 LLM 调用记录 token 用量+费用 |
| Code-Driven RBAC | 权限在代码中定义, 启动时自动同步到数据库 |
| API Proxy | 前端统一注入 JWT, 转发到后端 |
| Nuxt Layers | 按业务领域隔离前端代码 |
