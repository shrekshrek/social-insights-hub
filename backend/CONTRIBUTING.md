# FastAPI 后端开发贡献指南

本指南旨在统一团队在 FastAPI 项目中的开发标准，提高代码质量和协作效率。核心实践基于社区广泛认可的 [fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices)。

---

> 💡 **多项目开发**: 如基于此脚手架开发多个项目，请在各项目的 `.env` 中设置不同的 `PROJECT_NAME`，以实现 Docker 资源隔离。

---

## 目录

1. [项目结构](#1-项目结构-project-structure)
2. [编码规范](#2-编码规范-coding-conventions)
3. [统一处理系统](#3-统一处理系统-unified-handling-system)
4. [工具与依赖](#4-工具与依赖-tooling--dependencies)
5. [本地开发工作流](#5-本地开发工作流)

---

### 1. 项目结构 (Project Structure)

一个清晰、一致的项目结构是高效开发的基础。我们采用按业务领域划分的模块化结构。

```
backend/
├── alembic/              # Alembic 数据库迁移目录
├── src/                  # 项目主源码目录
│   ├── auth/             # 【领域模块】认证与授权
│   │   ├── router.py     # 路由
│   │   ├── schemas.py    # Pydantic 模型
│   │   ├── models.py     # SQLAlchemy 数据库模型
│   │   ├── service.py    # 业务逻辑
│   │   ├── dependencies.py # 依赖项
│   │   ├── constants.py  # 模块级常量
│   │   ├── exceptions.py # 模块级异常
│   │   ├── utils.py      # 模块级工具函数
│   │   ├── security.py   # 密码哈希、JWT等安全工具
│   │   └── blacklist.py  # JWT黑名单管理
│   ├── rbac/             # 【领域模块】权限管理 (RBAC)
│   │   ├── router.py     # 权限、角色管理 API
│   │   ├── schemas.py    # 权限、角色数据模型
│   │   ├── models.py     # 数据库模型
│   │   ├── service.py    # 权限检查、角色管理逻辑
│   │   ├── dependencies.py # 权限检查依赖
│   │   └── init_data.py  # 基础权限和角色定义
│   ├── users/            # 【领域模块】用户管理
│   │   └── ...
│   ├── celery_app.py     # Celery 应用实例
│   ├── database.py       # 数据库连接与配置
│   ├── redis_client.py   # Redis 连接配置
│   ├── config.py         # 全局配置
│   ├── exceptions.py     # 全局异常类定义
│   ├── middleware.py     # 全局中间件（异常处理、日志等）
│   ├── pagination.py     # 分页工具
│   ├── utils.py          # 通用工具函数（CPU密集型任务处理、异步包装器等）
│   └── main.py           # FastAPI 应用入口
├── tests/                # 测试目录
│   ├── conftest.py       # 测试配置和fixtures
│   └── test_*.py         # 具体测试文件
├── .env.example          # 环境变量模板
├── uv.lock                 # 锁定的依赖版本 (由 uv 自动生成)
├── pyproject.toml        # uv 依赖与项目配置 (PEP 621 格式)
├── README.md               # 后端 spezifische Anleitung
├── logging.ini           # 日志配置（生产环境推荐）
└── alembic.ini           # Alembic 配置文件
```

- **`src` 目录**: 所有应用代码的根目录，便于管理 `PYTHONPATH`。
- **领域模块**: 每个核心业务功能（如 `auth`, `rbac`）都是一个独立的 Python 包。
- **渐进式架构**: 项目结构支持从简单到复杂的渐进式发展。新模块可以从最基本的 `router.py` 开始，随着业务复杂度增加再逐步添加其他文件。

**注意**：并非所有模块都需要包含上述所有文件。根据业务复杂度和实际需求，按需创建文件。

---

### 2. 编码规范 (Coding Conventions)

统一的编码规范是保证代码可读性和可维护性的关键。**遵循 KISS 原则：保持简单，避免过度工程化。**

#### 异步优先
- **I/O 密集型任务**: 必须使用 `async def` 定义路由和服务函数。例如：数据库查询、外部 API 调用。
- **CPU 密集型任务**: 如果必须执行同步的、耗时的计算，使用 `src.utils` 中的工具函数（如 `run_cpu_bound_task` 或 `@async_wrap` 装饰器），它们内部使用 `run_in_threadpool` 避免阻塞事件循环。

#### SQL 优先，Pydantic 其次
- **复杂查询**: 优先使用 SQL (或 SQLAlchemy Core/ORM) 在数据库层面完成复杂的 `JOIN`、聚合和数据筛选。数据库通常比 Python 更高效。
- **数据校验**: Pydantic `schemas` 主要负责 API 边界的数据校验和序列化，而不是复杂的业务逻辑。

#### Pydantic 模型规范
- **基类继承**: 所有 Pydantic 模型**必须**继承自 `src.schemas.CustomBaseModel`，而不是直接继承 `pydantic.BaseModel`
- **配置方式**: 使用 Pydantic v2 的 `ConfigDict`，不使用旧版的 `Config` 内部类
- **统一配置**: `CustomBaseModel` 提供了统一的配置，包括：
  - `from_attributes=True` - 支持从 ORM 模型创建
  - `use_enum_values=True` - 使用枚举值而非名称
  - `validate_assignment=True` - 赋值时验证
  - 自定义 JSON 编码器 - datetime 和 Decimal 的序列化
- **示例**:
```python
from src.schemas import CustomBaseModel
from pydantic import Field

class UserResponse(CustomBaseModel):
    id: int
    name: str
    email: str = Field(..., description="用户邮箱")
```

#### 依赖注入 (Dependency Injection)
- **解耦和复用**: 将可重用的逻辑（如获取当前用户、数据库会话）封装在依赖项中，并在多个端点中复用。
- **异步优先**: 优先使用 `async def` 定义依赖项，以保持应用的非阻塞特性。
- **权限检查**: 使用 `src.rbac.dependencies` 中的权限检查依赖进行 API 访问控制：
- **避免过度抽象**: 只在真正需要复用时才创建依赖项，避免为了抽象而抽象。

#### API 响应与错误处理
- **FastAPI 原生优先**: 充分利用 FastAPI 的内置特性，直接返回业务数据，让框架处理序列化
- **使用 response_model**: 通过 `response_model` 参数定义响应结构，实现类型安全和自动文档生成
- **标准错误处理**: 使用 `HTTPException` 处理业务错误，让全局中间件统一处理

```python
from src.schemas import CustomBaseModel
from fastapi import HTTPException, status

class UserResponse(CustomBaseModel):
    id: int
    name: str
    email: str

@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int):
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="User not found"
        )
    return user  # 直接返回业务数据
```

#### API 前缀配置
- **配置统一**: 使用 `config.py` 中的 `API_PREFIX` 配置API路径前缀，避免硬编码
- **路由注册**: 在 `main.py` 中使用 `settings.API_PREFIX` 注册所有路由器
- **标签管理**: 在各路由器模块中定义 `tags`，主应用注册时不重复定义

#### API 文档
- **必要元数据**: 所有 API 路由**必须**包含以下元数据，以便生成高质量的 OpenAPI 文档：
  - `response_model`: 指定默认的成功响应模型
  - `status_code`: 指定明确的成功 HTTP 状态码
  - `tags`: 为端点分组，如 `["Users"]`, `["Authentication"]`
  - `summary`: 提供简明扼要的端点描述

#### ORM 模型关系定义 (ORM Model Relationships)
- **双向关系**: 所有外键关联 (Foreign Key) **必须**建立双向的 ORM 关系。这能极大提升代码的可读性和开发效率，是本项目的标准实践。
- **`relationship` 与 `back_populates`**:
    - 在定义外键的表中，**必须**同时定义一个指向父对象的 `relationship`。
    - 在父表中，**必须**定义一个反向的、指向子对象列表的 `relationship`。
    - 这两个 `relationship` **必须**使用 `back_populates` 参数互相引用，以确保 SQLAlchemy 能正确同步两者状态。

#### 数据库命名约定
- **表名**: 使用小写蛇形 (`snake_case`) 且为单数形式 (e.g., `user`, `post_like`)。
- **字段名**:
  - 时间戳 (`datetime`) 字段使用 `_at` 后缀 (e.g., `created_at`, `updated_at`)。
  - 日期 (`date`) 字段使用 `_date` 后缀 (e.g., `start_date`)。
- **索引/约束**: 配置 Alembic 和 SQLAlchemy 使用统一的命名约定，如 `ix_%(column_0_label)s`。

---

### 3. 统一处理系统 (Unified Handling System)

为了提高代码质量和开发效率，项目采用了统一的处理系统。

#### 全局异常处理
- **文件位置**: `src/exceptions.py` + `src/middleware.py`
- **核心功能**: 
  - 自动捕获和处理所有未处理的异常
  - 转换为标准的 HTTP 错误响应
  - 记录详细的错误日志
- **使用方式**: 在业务代码中直接抛出 `HTTPException` 或自定义异常类

#### 请求日志中间件
- **文件位置**: `src/middleware.py`
- **核心功能**: 
  - 自动记录所有API请求和响应
  - 生成唯一请求ID用于追踪
  - 记录处理时间和性能指标
- **配置**: 在 `main.py` 中自动启用，无需额外配置

#### 分页工具
- **文件位置**: `src/pagination.py` + `src/schemas.py`
- **核心功能**: 
  - 提供标准化的分页参数处理
  - 支持SQLAlchemy查询的自动分页
  - **统一分页响应格式**: 所有分页接口使用 `PaginatedResponse[T]` 基类
- **使用方式**: 通过依赖注入使用分页参数
- **响应格式**: `{"items": [...], "total": 100, "page": 1, "page_size": 10}`

#### 设计原则
- **KISS原则**: 保持简单，避免过度工程化
- **FastAPI 原生**: 优先使用 FastAPI 提供的标准特性
- **渐进式增强**: 基础功能到位，后续按需扩展
- **实用性优先**: 只保留真正会用到的功能
- **标准化**: 遵循FastAPI和Python生态的最佳实践

---

### 4. 工具与依赖 (Tooling & Dependencies)

标准化的工具链可以自动化繁琐任务，保障项目质量。

#### 依赖管理 (uv)
- **强制使用**: **必须**使用 `uv` 作为唯一的包和依赖管理器，以利用其高性能和现代化的工具链。
- **添加依赖**:
  ```bash
  # 在 backend 容器中运行
  uv add <package-name>
  ```
- **安装依赖**:
  ```bash
  # 在 backend 容器中运行
  uv sync
  ```
- **同步依赖**: 当 `pyproject.toml` 变更后，运行 `uv sync` 来同步环境。

#### 数据库迁移 (Alembic)
- **静态迁移**: 迁移脚本应是确定性的，不依赖于动态数据。
- **可读文件名**: 使用 `alembic.ini` 中的 `file_template` 配置，生成带有日期和描述性 slug 的文件名，如 `2023-10-27_add_user_age_column.py`。

#### 代码质量 (Ruff)
- **强制使用**: 使用 `Ruff` 作为 linter 和 formatter，替代 `black`, `isort`, `flake8`。
- **自动化**: 建议配置 pre-commit 钩子或在 CI/CD 流程中集成 `ruff check --fix` 和 `ruff format`。

#### 测试 (Pytest & HTTPX)
- **测试框架**: **必须**使用 `pytest` 作为唯一的测试框架，利用其简洁的语法和强大的 Fixture 系统
- **异步客户端**: **必须**使用 `httpx.AsyncClient` 编写异步集成测试，以模拟对应用的真实 API 调用
- **测试隔离**:
    - **数据库**: 所有测试都通过 `conftest.py` 中的 `db_session` Fixture 使用一个独立的、事务性的数据库会话。这确保了测试之间的数据不会互相干扰
    - **测试数据库**: 项目会在 `backend/` 目录下创建 `test.db` 文件作为测试专用的 SQLite 数据库
    - **依赖覆盖**: FastAPI 的 `app.dependency_overrides` 机制被用来在测试时注入隔离的数据库会话，保证测试环境的纯净性
- **运行测试**: 在 `backend` 目录下，使用 `uv run pytest` 命令来执行完整的测试套件

#### 异步任务队列 (Celery)
- **标准选择**: 使用 `Celery` 作为处理所有后台和异步任务的标准框架。
- **消息代理**: 生产和开发环境均使用 `Redis` 作为消息代理 (Broker) 和结果后端 (Result Backend)。
- **任务定义**: Celery 任务应定义在对应领域模块的 `tasks.py` 文件中，以保持代码的组织性。当模块不需要后台任务时，可以不创建此文件。

#### LLM 应用开发 (LangChain)
- **核心框架**: 使用 `LangChain` 作为构建语言模型应用和工作流的核心框架。
- **版本要求**: 项目锁定使用 `LangChain v0.3+` 系列版本。

#### 权限系统开发 (RBAC)

**快速添加模块权限**:
```python
# src/rbac/init_data.py
*create_module_permissions("new_module", ["access", "read", "write"])
```

详细的模块开发流程见 [`docs/MODULAR_DEVELOPMENT.md`](../docs/MODULAR_DEVELOPMENT.md)  
权限系统技术原理见 [`docs/PERMISSION_MANAGEMENT.md`](../docs/PERMISSION_MANAGEMENT.md)

---

### 5. 本地开发工作流

1.  **启动后台服务**:
    - 确保 Docker Desktop 正在运行。
    - 在项目根目录执行 `docker-compose up -d` 来启动 PostgreSQL 和 Redis。
2.  **启动开发服务器**:
    - 在项目根目录打开 **两个** 终端。
    - **终端 1**: 运行 `pnpm be:dev` 启动 FastAPI 服务器。
    - **终端 2**: 运行 `pnpm be:worker` 启动 Celery Worker（如果有后台任务需要处理）。
3.  **访问 API**:
    - API 文档位于 [http://localhost:8000/docs](http://localhost:8000/docs)。 