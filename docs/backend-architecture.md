# 后端架构文档

> 本文档描述后端整体拓扑、模块边界、数据模型和分析管线。
> 模块内部实现细节以各模块 CLAUDE.md（`src/*/CLAUDE.md`）为权威源。

---

## 1. 部署拓扑

```
用户浏览器
    │ HTTP(S)
    ▼
Nginx (Port 80/443)
    ├──▶ Nuxt SSR (Port 3000)  ──HTTP──▶  FastAPI (Port 8000)
    └──▶ FastAPI (Port 8000)                    │
                                    ┌───────────┼──────────┐
                                    ▼           ▼          ▼
                              PostgreSQL 16   Redis 7  DeepSeek API
                                                │
                                                ▼
                                        Celery Worker (gevent)
```

| Docker 服务 | 端口 | 职责 |
|-------------|------|------|
| postgres_db | 5432 | 数据持久化 |
| redis | 6379 | Celery Broker + Result Backend + 缓存 |
| backend | 8000 | FastAPI API 服务 + APScheduler 定时任务 |
| celery-worker | — | 异步 LLM 分析任务执行 |
| frontend | 3000 | Nuxt SSR（开发环境为宿主机 pnpm dev） |

---

## 2. 项目结构

```
backend/src/
├── auth/                    # JWT 认证、登录注册、令牌黑名单
├── rbac/                    # 角色权限管理、代码驱动启动时自动同步
├── users/                   # 用户 CRUD、角色分配
├── social_media/
│   ├── monitors/            # 社媒监测项目、平台初始化、参与者管理
│   ├── tasks/               # 数据采集任务、多平台适配器
│   │   └── adapters/        # 抖音/小红书/微博/B站/快手/知乎/贴吧
│   └── analysis/            # 社媒 LLM 分析编排（channel-local）
│       └── celery_tasks/    # screening / deep / aggregation / monitor_slice
├── news_media/
│   ├── monitors/            # 新闻监测项目
│   ├── tasks/               # 新闻采集任务 + Celery 任务
│   │   └── news_search/     # 百度/搜狗 默认双渠道 + 可选微信公众号（Bing 已下线）
│   └── analysis/            # 新闻切片分析（NewsSlice）+ AnalysisJob 封装
├── strategies/              # 策略研究引擎
├── knowledge_base/          # 市场知识库 + 文档向量化
├── research_agent/          # 专题研究 Agent（LangGraph，开发中）
├── jobs/                    # 跨渠道 AnalysisJob：models/schemas/crud/factory/router
├── llm/                     # LLM 实例管理 + 分析链（无独立 API 路由）
│   └── chains/              # 分析链按渠道分目录
├── agent/                   # 爬虫代理 API（API Key 认证）
├── config.py                # 全局配置（pydantic-settings）
├── database.py              # 数据库连接池（async + sync）
├── redis_client.py          # Redis 连接
├── celery_app.py            # Celery 应用配置
├── scheduler.py             # APScheduler 定时任务注册
├── middleware.py            # 全局中间件
├── exceptions.py            # 全局异常定义
├── pagination.py            # 分页工具
└── main.py                  # 应用入口、路由注册、lifespan
```

---

## 3. 模块边界与依赖

### 3.1 依赖关系

```
                ┌─────────────────────────────────────────┐
                │          strategies                      │
                └──────┬────────────┬──────────────────────┘
                       │            │
           ┌───────────▼──┐   ┌─────▼──────────┐   ┌──────────────────┐
           │ social_media  │   │  news_media    │   │ knowledge_base   │
           │  monitors/    │   │  monitors/     │   │                  │
           │  tasks/       │   │  tasks/        │   └──────────────────┘
           │  analysis/ ───┼───┼─ analysis/     │
           └───────────────┘   └────────────────┘
                    │                   │
                    └──────────┬────────┘
                               ▼
                    ┌──────────────────┐    ┌──────────────────┐
                    │      jobs/       │    │      llm/        │
                    │ (跨渠道 AnalysisJob)│    │ (LLM 引擎)       │
                    └──────────────────┘    └──────────────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
              ┌──────────┐          ┌──────────┐
              │   auth   │          │   rbac   │
              └──────────┘          └──────────┘
                    │
                    ▼
          ┌─────────────────────────────┐
          │  基础设施（config, database,  │
          │  redis, celery, middleware） │
          └─────────────────────────────┘
```

禁止反向依赖：`jobs/` 和 `llm/` 不得 import 任何渠道模块。

### 3.2 模块职责总表

| 模块 | 职责 | API 前缀 |
|------|------|----------|
| auth | JWT 认证、登录注册、令牌黑名单 | `/api/v1/auth` |
| rbac | 角色权限 CRUD、代码驱动同步 | `/api/v1/rbac` |
| users | 用户 CRUD、角色分配 | `/api/v1/users` |
| social_media/monitors | 社媒监测项目、平台初始化 | `/api/v1/social-media/monitors` |
| social_media/tasks | 任务管理、多平台适配器、原文/评论存储 | `/api/v1/social-media/tasks` |
| social_media/analysis | 社媒 LLM 分析编排（channel-local） | `/api/v1/social-media/analysis` |
| news_media | 新闻监测、采集、分析（channel-local） | `/api/v1/news-media` |
| strategies | 策略研究引擎 | `/api/v1/strategies` |
| knowledge_base | 市场知识库、文档向量化 | `/api/v1/knowledge-base` |
| research_agent | 专题研究 LangGraph Agent（开发中） | `/api/v1/research-agent` |
| jobs | 跨渠道 AnalysisJob 管理 | `/api/v1/jobs` |
| llm | LLM 实例 + 分析链（无 API 路由） | — |
| agent | 外部爬虫数据上传（API Key 认证） | `/api/v1/agent` |

---

## 4. 核心模块说明

### 4.1 认证模块 auth/

- JWT 令牌生成/验证、密码哈希
- 令牌黑名单（Redis 存储，登出时写入）
- 依赖：`get_current_user()` 供所有模块使用

### 4.2 权限模块 rbac/

- 代码驱动：权限在 `init_data.py` 定义，启动时自动同步数据库
- `permission_strategy` 字段控制角色权限获取方式：
  - `all`：自动获得所有权限（super_admin）
  - `admin`：自动获得管理员权限（admin）
  - `explicit`：仅拥有明确分配的权限（自定义角色）
- 超管安全保护：不能删除最后一个 super_admin；不能自修改角色；不能让 super_admin 无人持有
- 详见 [`docs/PERMISSION_MANAGEMENT.md`](./PERMISSION_MANAGEMENT.md)

### 4.3 社媒模块 social_media/

**分析管线**（channel-local，归属 `social_media/analysis/`）：

```
Stage 1 screening    → LLM 初筛: spam/value/relevance/sentiment → PostAnalysis
Stage 2 deep         → LLM 深度: 实体/观点/摘要 → PostAnalysis.deep_result
Stage 3 aggregation  → 聚合: NSR/SERP/IPA/四象限/实体/话题/KOL → SocialTask.analysis_result
        monitor_slice → 监测切片: 跨任务合并 + LLM 报告 → AnalysisSlice.result_data
```

关键指标：**NSR**（净情感率 [-2,+2]）、**CII**（内容互动指数）、**SERP**（搜索健康度 [0,100]）、营销浓度、4D Spam 分布。

**任务触发模型**：Pull（外部爬虫通过 `agent/` API 认领任务，social_media 无 `/execute` 端点）。

### 4.4 新闻模块 news_media/

- 独立监测：一步式 collect，`/tasks/{id}/execute` 触发 Celery 采集
- 策略研究场景：两段式 probe（搜索卡片）→ collect（抓全文），由 `strategies/service.py` 编排，probe/collect 各是独立的 NewsTask 记录
- 分析（channel-local）：NewsSlice 切片分析 + NEWS_TAGGING/NEWS_INSIGHT AnalysisJob 封装

### 4.5 strategies/

多渠道数据汇聚（social_media + news_media + knowledge_base），LLM 辅助生成品牌策略报告。详见 [`docs/strategy-multi-source-architecture.md`](./strategy-multi-source-architecture.md)。

### 4.6 research_agent/（开发中）

基于 LangGraph 的 agentic 搜索分析，替代 KB 预存模式。详见 [`docs/research-agent-design.md`](./research-agent-design.md)。

### 4.7 jobs/

跨渠道 AnalysisJob 的唯一归属地。所有渠道创建/查询/取消 AnalysisJob 都通过这里，自动记录 token 用量和费用。

### 4.8 agent/

外部爬虫通过 `X-API-Key` 认证上传数据。支持 `auto_analyze=True` 参数自动触发完整分析管线。

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
| platforms | social_media/monitors | 社交平台定义（7 个平台） |
| social_monitors, social_monitor_participants | social_media/monitors | 社媒监测项目 |
| social_tasks | social_media/tasks | 社媒采集任务 |
| social_posts, social_comments | social_media/tasks | 原文/评论数据 |
| post_analysis | social_media/analysis | 原文分析结果（1:1 SocialPost） |
| social_slices | social_media/analysis | 社媒项目级合并分析切片 |
| analysis_jobs | jobs | 跨渠道分析任务状态 + LLM 成本 |
| news_monitors, news_monitor_participants | news_media | 新闻监测项目 |
| news_tasks | news_media | 新闻采集任务 |
| news_articles | news_media | 新闻文章 |
| news_slices | news_media/analysis | 新闻项目级切片（独立 insight 分析） |
| strategies, strategy_participants | strategies | 策略研究（社媒/新闻切片均通过 monitor_id 隐式关联，无显式关联表） |
| knowledge_documents, knowledge_chunks | knowledge_base | 知识文档 + 向量嵌入 |

---

## 6. 跨模块数据流

### 社媒采集到报告

```
外部爬虫 ──POST──▶ agent/router (X-API-Key)
                      │
                agent/service.upload_result()
                      │ tasks/adapters 转换 → tasks/crud 写入
                      ▼
               SocialPost, SocialComment
                      │ auto_analyze=True
                      ▼
    social_media/analysis/celery_tasks (screening → deep → aggregation)
                      │ llm/chains/social_media/*
                      ▼
               SocialTask.analysis_result
                      │ 前端读取
                      ▼
               TaskAnalysisReport.vue
```

### 权限贯穿

```
前端 route-guard → usePermissions() → session.user.roles
      │
server/api/v1/[...].ts → 注入 Authorization header
      │
后端 router → Depends(get_current_user) + Depends(require_*_permission)
      │
service → check_monitor_access(user_id, monitor_id)（项目级权限）
```

---

## 7. 关键架构模式

| 模式 | 应用场景 |
|------|---------|
| Service Layer | 业务逻辑集中在 `service.py`，router 只做参数校验和路由 |
| Dependency Injection | FastAPI `Depends()` 管理 DB session、当前用户、权限检查 |
| Adapter Pattern | `tasks/adapters/` 处理各平台数据格式差异，输出统一内部格式 |
| Channel-Local Analysis | 分析逻辑归属各渠道，通过 `jobs/` 统一管理 AnalysisJob |
| Pull vs Push Tasks | social_media 用 Pull（爬虫认领）；news_media/knowledge_base 用 Push（Celery dispatch） |
| Async Task Chain | Celery 编排多阶段分析管线（screening → deep → aggregation） |
| Slice Pattern | `AnalysisSlice` 保存不可变报告历史 |
| Cost Tracking | 每次 LLM 调用自动记录 token 用量 + 费用到 AnalysisJob |
| Code-Driven RBAC | 权限在代码中定义，启动时自动同步到数据库 |
| API Proxy | 前端统一注入 JWT，转发到后端 |

---

## 8. 中间件系统

执行顺序（从外到内）：

1. **SecurityHeadersMiddleware** — 添加 HSTS、X-Content-Type-Options 等安全头
2. **GlobalExceptionHandlerMiddleware** — 统一捕获异常，转为标准 HTTP 响应
3. **RequestLoggingMiddleware** — 记录所有请求、响应时间、错误信息
4. **CORSMiddleware** — 跨域处理（由 `BACKEND_CORS_ORIGINS` 配置）

---

## 9. 开发快速参考

```bash
# 启动开发环境
pnpm dev

# 创建数据库迁移
pnpm be:migrate:make "描述"
pnpm be:migrate:up

# 代码检查
pnpm be:lint

# API 文档
open http://localhost:8000/docs
```

新模块开发全流程见 [`docs/MODULAR_DEVELOPMENT.md`](./MODULAR_DEVELOPMENT.md)。
