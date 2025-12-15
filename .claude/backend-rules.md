# FastAPI 后端开发核心规则

详细规范见：`backend/CONTRIBUTING.md`

## 核心技术栈
- **框架**: FastAPI
- **数据库**: PostgreSQL + SQLAlchemy (异步ORM) + Alembic
- **异步任务**: Celery + Redis
- **LLM框架**: LangChain 1.0+
- **包管理器**: uv

## 关键编码规范

### 设计原则
- **KISS原则**: 保持简单，避免过度工程化
- **统一处理**: 使用全局中间件确保API一致性
- **FastAPI原生优先**: 充分利用框架特性

### 异步与性能
- I/O密集型操作**必须**使用 `async def`
- CPU密集型任务使用 `run_in_threadpool`
- 广泛使用依赖注入系统

### API规范
- 所有端点**必须**包含:
  - `response_model` - 响应模型
  - `status_code` - HTTP状态码
  - `tags` - API分组标签
  - `summary` - 端点描述
- 直接返回业务数据，让框架处理序列化
- 使用 `HTTPException` 处理业务错误

### Pydantic 模型规范
- 所有 Pydantic 模型**必须**继承 `CustomBaseModel` (定义在 `src/schemas.py`)
- 使用 Pydantic v2 的 `ConfigDict` 配置方式
- 不要直接继承 `pydantic.BaseModel`

### 项目结构
```
backend/src/
├── [domain]/        # 领域模块
│   ├── router.py    # API路由
│   ├── schemas.py   # Pydantic模型
│   ├── models.py    # SQLAlchemy模型
│   ├── service.py   # 业务逻辑
│   ├── tasks.py     # Celery任务
│   └── dependencies.py # 依赖注入
├── config.py        # 全局配置
├── database.py      # 数据库连接
├── middleware.py    # 全局中间件
├── utils.py         # 通用工具函数（CPU密集型任务处理等）
└── main.py         # 应用入口
```

### 数据库规范
- 表名：小写蛇形复数 (如 `users`, `post_likes`)
- 时间戳字段：使用 `_at` 后缀
- 外键关系：必须建立双向ORM关系

### 测试要求
- 使用 `pytest` 作为测试框架
- 使用 `httpx.AsyncClient` 编写异步测试
- 测试数据库隔离，使用事务回滚