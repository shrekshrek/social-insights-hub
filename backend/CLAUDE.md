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
| 异步任务 | Celery + gevent |
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
│   ├── monitors/            # 监测项目, 平台初始化
│   ├── tasks/               # 数据采集任务, 多平台适配器
│   │   └── adapters/        # 抖音/小红书/微博等平台适配
│   └── analysis/            # LLM 分析编排, 成本追踪
│       ├── celery_tasks/    # screening, deep, aggregation, slice
│       └── jobs/            # AnalysisJob CRUD
├── langchain/               # LLM 实例管理, 分析链定义
│   └── chains/              # 9 条分析链
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
- 使用 `HTTPException` 处理业务错误
- SQL 优先处理复杂查询，Pydantic 负责 API 边界校验
- 新模块路由在 `main.py` 中注册
- 权限在 `rbac/init_data.py` 中用 `create_module_permissions()` 定义

## 注意事项

- 后端命令在 Docker 容器内执行 (pnpm scripts 自动代理)
- Celery Worker 使用 gevent pool，LLM 调用走异步
- 每次 LLM 调用记录 token 用量和费用到 AnalysisJob
