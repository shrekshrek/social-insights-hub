# Backend Tier — FastAPI + Python

> Tier 专属约定。与根 `CLAUDE.md` 冲突时以本文件为准。
> 详细编码规范见 `CODING_GUIDE.md`。

## 技术栈

| 项 | 选型 |
|----|------|
| 框架 | FastAPI (async) |
| 语言 | Python 3.11+ |
| ORM | SQLAlchemy 2.0 (async) |
| 迁移 | Alembic |
| 数据库 | PostgreSQL 16 |
| 缓存/队列 | Redis 7 |
| 异步任务 | Celery + gevent（AI 分析流水线）；APScheduler（轻量定时任务） |
| LLM | LangChain 1.0+ + DeepSeek API |
| 包管理 | uv |
| Lint/Format | Ruff |
| 测试 | pytest + httpx |

## 构建与测试命令

所有命令在项目根目录执行（通过 pnpm scripts 代理到容器内）：

```bash
pnpm be:lint          # ruff check + format
pnpm be:test          # pytest
pnpm be:migrate:make "描述"  # alembic revision --autogenerate
pnpm be:migrate:up    # alembic upgrade head
pnpm be:add <pkg>     # uv add
```

开发服务器：

```bash
pnpm be:dev           # uvicorn --reload (port 8000)
# Celery Worker 在 docker-compose up 时自动启动，无需单独命令
```

## 模块结构

```
backend/src/
├── auth/                    # JWT 认证, 登录注册, 令牌黑名单
├── rbac/                    # 角色权限, 代码驱动同步
├── users/                   # 用户 CRUD, 角色分配
├── social_media/
│   ├── monitors/            # 社媒监测项目, 平台初始化
│   ├── tasks/               # 社媒数据采集任务, 多平台适配器
│   │   └── adapters/        # 抖音/小红书/微博等平台适配
│   └── analysis/            # 社媒本地分析（screening / deep / aggregation / slice）
│       └── celery_tasks/    # 社媒 LLM 分析链编排
├── news_media/
│   ├── monitors/            # 新闻监测项目
│   ├── tasks/               # 新闻采集任务 + celery 任务
│   │   └── news_search/     # 百度/搜狗/DuckDuckGo/微信公众号 多渠道搜索
│   └── analysis/            # 新闻切片分析（NewsSlice 模型/CRUD/service + tagging job 封装）
├── jobs/                    # 跨渠道 AnalysisJob: models, schemas, crud, factory, router
├── llm/                     # LLM 实例管理 + 分析链定义（原 langchain/）
│   └── chains/              # 19 条分析链
├── knowledge_base/          # 市场知识库 + 文档向量化
├── strategies/              # 策略研究
├── agent/                   # 爬虫代理 API, API Key 认证
├── config.py, database.py, redis_client.py, celery_app.py
├── middleware.py, exceptions.py, pagination.py, schemas.py
└── main.py                  # 应用入口, 路由注册
```

每个模块标准文件: `models.py` → `schemas.py` → `service.py` → `router.py`（按需 `dependencies.py`, `crud.py`, `utils.py`）

## 编码约定

- Pydantic 模型**必须**继承 `src.schemas.CustomBaseModel`
- I/O 操作**必须**用 `async def`；CPU 密集型用 `src.utils.run_cpu_bound_task`
- API 端点**必须**包含 `response_model`, `status_code`, `tags`, `summary`
- 外键**必须**建立双向 ORM 关系 (`back_populates`)
- 表名小写蛇形复数，时间戳 `_at` 后缀，日期 `_date` 后缀
- **语义字段强制一致**：创建者外键用 `user_id`、状态用 `status`、错误用 `error_message`、流水线结果 JSON 用 `result_data`、统计 JSON 用 `stats`、软删除用 `is_deleted`。新增表若有同语义字段必须沿用此命名，不要自创变体。详见 `CODING_GUIDE.md §2` 语义字段命名表
- 使用 `HTTPException` 处理业务错误
- SQL 优先处理复杂查询，Pydantic 负责 API 边界校验
- 新模块路由在 `main.py` 中注册
- 权限在 `rbac/init_data.py` 中用 `create_module_permissions()` 定义
- **资源型 API 统一使用子资源 URL 风格**：父子关系通过路径表达，例如 `POST /{channel}/monitors/{monitor_id}/tasks`、`/strategies/{id}/participants`、`/news-media/monitors/{id}/participants`。禁止把 parent_id 放 body/query

## 架构约定

### 模块边界（ADR-001 channel-local analysis）

严格单向依赖：`strategies → {social_media, news_media, knowledge_base} → {jobs, llm}`。

- `src/jobs/` — 跨渠道 AnalysisJob 的唯一归属地（models/schemas/crud/factory/router）。任何渠道创建/查询/取消 AnalysisJob 都通过这里
- `src/llm/` — LLM 实例管理与分析链（原 `src/langchain/`，因与 pypi 包同名而重命名）
- 各渠道的 **analysis celery 任务** 与 **分析编排** 归本渠道：
  - `src/social_media/analysis/celery_tasks/` — 社媒 screening/deep/aggregation/slice
  - `src/news_media/analysis/` — 新闻切片（NewsSlice models/crud/service/router）+ tagging job 封装（jobs.py）
- **采集/处理类 celery 任务** 归各自渠道模块：
  - `src/news_media/tasks/tasks.py` — 新闻爬取
  - `src/knowledge_base/tasks.py` — 文档向量化
  - `src/social_media/` 无采集 celery —— 走 agent pull 模型（见下）
- 所有 celery 模块必须在 `src/celery_app.py` 的 `include` 列表中显式注册
- 禁止反向依赖：`src/jobs/` 和 `src/llm/` 不得 import 任何渠道模块

### 任务触发模型

项目有两种任务触发模型，并存且都合理：

| 模型 | 使用者 | 入口 | 状态流转 |
|---|---|---|---|
| **Pull (Agent claim)** | `social_media` | 外部爬虫通过 `agent/` API 认领任务 | `agent/service.py` 把 task.status 置为 `running` |
| **Push (Celery dispatch)** | `news_media` / `knowledge_base` | 后端 router 调 `.delay()` 派发 celery | router 置 status 后派发 celery worker |

→ 因此 social_media 没有、也不需要 `/tasks/{id}/execute` 端点；news_media 必须有。新增渠道时根据数据源特性二选一，不要混用。

**news_media 场景区分**：
- **独立 news monitor**：只支持一步式 collect，`/tasks/{id}/execute` 仅接受 `strategy_id IS NULL` 且 `phase != "probe"`；不提供 approve/refine 探测流程
- **strategy 研究场景**：两段式 probe → collect，每阶段是**独立的 NewsTask 记录**（不做 phase 迁移），probe 只搜索卡片不抓全文不打标；probe/refine/approve 统一由 `strategies/service.py` 的批量端点编排，news_media router 不对外暴露

### 分析编排（channel-local）

分析逻辑归属于所属渠道，没有全局 `analysis/` 模块：

- 社媒分析 → `src/social_media/analysis/`（含 service、router、celery_tasks、models）
- 新闻分析 → `src/news_media/analysis/`（NewsSlice 切片分析 + NEWS_TAGGING / NEWS_INSIGHT AnalysisJob 封装）
- 新增渠道时在 `src/{channel}/analysis/` 下新建本渠道的 service/celery_tasks 即可
- 所有渠道通过 `src/jobs/` 创建和管理 AnalysisJob，通过 `src/llm/` 调用 LLM
- 跨渠道 AnalysisJob 查询/取消/删除端点由 `src/jobs/router.py` 暴露（`/jobs`），前端通过这个统一入口查看所有渠道的分析任务

## 注意事项

- 后端命令在 Docker 容器内执行 (pnpm scripts 自动代理)
- Celery Worker 使用 gevent pool，LLM 调用走异步
- APScheduler 运行在 FastAPI asyncio 事件循环中，负责所有轻量定时任务（策略检测、agent 超时回收、KB 爬虫）；无需 celery-beat 容器
- 每次 LLM 调用记录 token 用量和费用到 AnalysisJob
