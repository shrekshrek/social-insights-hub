# 后端架构说明文档

- **版本**: `v1.0`
- **日期**: `2025-01-19`
- **状态**: `完成`

---

## 目录

1. [系统概览](#1-系统概览)
2. [核心架构](#2-核心架构)
3. [模块详细说明](#3-模块详细说明)
4. [数据库设计](#4-数据库设计)
5. [API 概览](#5-api-概览)
6. [中间件系统](#6-中间件系统)
7. [配置管理](#7-配置管理)
8. [开发指南](#8-开发指南)

---

## 1. 系统概览

### 1.1 技术栈
- **核心框架**: FastAPI
- **数据库**: PostgreSQL + SQLAlchemy (ORM) + Alembic (迁移)
- **异步任务**: Celery + Redis
- **部署**: Docker
- **认证**: JWT + OAuth2
- **权限**: RBAC (Role-Based Access Control 基于角色的访问控制)
- **任务队列**: Celery + Redis
- **迁移**: Alembic
- **包管理**: uv

### 1.2 架构特点
- **领域驱动设计**: 按业务领域划分模块
- **异步优先**: 所有I/O操作使用异步处理
- **依赖注入**: 广泛使用FastAPI的依赖注入系统
- **统一处理**: 全局中间件处理异常、日志、安全头等
- **配置驱动**: 通过环境变量和配置文件管理设置

---

## 2. 核心架构

### 2.1 项目结构
```
backend/
├── src/                      # 主源码目录
│   ├── auth/                # 认证与授权模块
│   ├── rbac/                # 权限管理模块  
│   ├── users/               # 用户管理模块
│   ├── main.py              # FastAPI应用入口
│   ├── config.py            # 全局配置
│   ├── database.py          # 数据库连接配置
│   ├── middleware.py        # 全局中间件
│   ├── exceptions.py        # 全局异常定义
│   ├── pagination.py        # 分页工具
│   ├── utils.py             # 通用工具函数
│   ├── redis_client.py      # Redis连接配置
│   └── celery_app.py        # Celery应用配置
├── alembic/                 # 数据库迁移
└── tests/                   # 测试文件
```

### 2.2 模块设计原则
- **单一职责**: 每个模块专注于特定的业务领域
- **渐进式架构**: 从简单开始，按需增加复杂度
- **标准化结构**: 每个模块包含router、schemas、models、service等标准文件

---

## 3. 模块详细说明

### 3.1 认证模块 (auth/)
**职责**: 用户认证、JWT令牌管理

**主要组件**:
- `models.py`: User数据模型
- `router.py`: 注册、登录、令牌刷新等API端点
- `service.py`: 用户创建、验证、密码处理等业务逻辑
- `security.py`: JWT生成/验证、密码哈希等安全工具
- `dependencies.py`: 获取当前用户、令牌验证等依赖
- `blacklist.py`: JWT黑名单管理
- `schemas.py`: 认证相关的Pydantic模型

**核心功能**:
- 用户注册和登录
- JWT令牌生成和验证
- 令牌黑名单管理

### 3.2 权限管理模块 (rbac/)
**职责**: 基于角色的访问控制系统

**主要组件**:
- `models.py`: Role、Permission、RolePermission、UserRole数据模型
- `router.py`: 角色、权限管理API端点
- `service.py`: 权限检查、角色分配等业务逻辑
- `dependencies.py`: 权限检查依赖函数
- `init_data.py`: 基础角色和权限初始化数据
- `schemas.py`: RBAC相关的Pydantic模型

**核心功能**:
- 角色和权限管理
- 用户角色分配
- 权限检查和验证
- 基础数据初始化
- **系统级保护机制**: 防止核心角色和权限被误删除或篡改

**系统级保护机制**:
- **删除保护**: 标记为 `is_system=True` 的角色和权限无法被删除
- **更新保护**: 系统级角色和权限只能修改显示名称和描述，核心字段受保护
- **数据完整性**: 确保系统核心功能不会因误操作而失效
- **安全边界**: 区分系统核心权限和业务权限，提供不同的保护级别

### 3.3 用户管理模块 (users/)
**职责**: 用户信息管理和用户相关操作

**主要组件**:
- `router.py`: 用户CRUD操作API端点
- `service.py`: 用户查询、更新等业务逻辑
- `schemas.py`: 用户相关的Pydantic模型

**核心功能**:
- 用户信息查询和更新
- 用户列表和分页
- 当前用户信息获取

### 3.4 核心模块
**全局组件**:
- `main.py`: FastAPI应用入口，路由注册，中间件配置
- `config.py`: 配置管理，环境变量加载
- `database.py`: 数据库连接，会话管理
- `middleware.py`: 全局中间件（异常处理、日志、安全头等）
- `exceptions.py`: 自定义异常类定义
- `pagination.py`: 分页工具函数
- `utils.py`: 通用工具函数（CPU密集型任务处理等）

---

## 4. 数据库设计

### 4.1 数据表概览
- `users`: 用户基础信息
- `roles`: 角色定义
- `permissions`: 权限定义
- `role_permissions`: 角色-权限关联表
- `user_roles`: 用户-角色关联表

### 4.2 表结构详情

#### users 表
```sql
- id: SERIAL PRIMARY KEY
- username: VARCHAR(50) UNIQUE NOT NULL
- email: VARCHAR(100) UNIQUE NULL  
- hashed_password: VARCHAR NOT NULL
- created_at: TIMESTAMP DEFAULT NOW()
- updated_at: TIMESTAMP DEFAULT NOW()
```

#### roles 表
```sql
- id: SERIAL PRIMARY KEY
- name: VARCHAR(50) UNIQUE NOT NULL        # 如: admin, user
- display_name: VARCHAR(100) NOT NULL      # 如: 管理员, 普通用户
- description: TEXT                        # 角色描述
- is_system: BOOLEAN DEFAULT FALSE         # 系统角色标记
- created_at: TIMESTAMP DEFAULT NOW()
- updated_at: TIMESTAMP DEFAULT NOW()
```

#### permissions 表
```sql
- id: SERIAL PRIMARY KEY
- name: VARCHAR(100) UNIQUE NOT NULL       # 如: user:read, page:dashboard
- display_name: VARCHAR(100) NOT NULL      # 如: 查看用户, 访问工作台
- resource: VARCHAR(50) NOT NULL           # 资源类型: user, page, system
- action: VARCHAR(50) NOT NULL             # 操作类型: read, write, delete, access
- description: TEXT                        # 权限描述
- is_system: BOOLEAN DEFAULT FALSE         # 系统权限标记（不可删除）
- created_at: TIMESTAMP DEFAULT NOW()
- updated_at: TIMESTAMP DEFAULT NOW()
```

### 4.3 关系设计
- **用户-角色**: 多对多关系，通过`user_roles`表关联
- **角色-权限**: 多对多关系，通过`role_permissions`表关联

### 4.4 预设数据

**系统级角色** (不可删除):
- `super_admin`: 超级管理员，拥有所有权限
- `admin`: 管理员，拥有管理权限
- `user`: 普通用户，只能访问基础功能

**系统级权限** (不可删除):
- 用户管理: `user:read`, `user:write`, `user:delete`
- 角色管理: `role:read`, `role:write`, `role:delete`
- 权限管理: `permission:read`, `permission:write`, `permission:delete`

**业务级权限** (可删除):
- 页面访问: `page:dashboard`, `page:users`, `page:roles`, `page:permissions`

**保护机制说明**:
- **系统级项目**: 标记为 `is_system=True`，确保系统核心功能不被破坏
- **业务级项目**: 标记为 `is_system=False`，可根据业务需求灵活调整
- **安全边界**: 系统级权限涉及用户、角色、权限管理等核心功能，业务级权限主要涉及页面访问等扩展功能

---

## 5. API 概览

### 5.1 API 前缀
所有API都使用统一前缀: `/api/v1`

### 5.2 认证端点 (/api/v1/auth)
- `POST /register`: 用户注册
- `POST /token`: 用户登录，获取访问令牌
- `POST /token/refresh`: 刷新访问令牌
- `POST /logout`: 用户登出

### 5.3 用户管理端点 (/api/v1/users)
- `GET /me`: 获取当前用户信息
- `PUT /me`: 更新当前用户信息
- `GET /`: 获取用户列表 (需要权限)
- `GET /{user_id}`: 获取特定用户信息 (需要权限)
- `PUT /{user_id}`: 更新用户信息 (需要权限)
- `DELETE /{user_id}`: 删除用户 (需要权限)

### 5.4 权限管理端点 (/api/v1/rbac)
- `GET /permissions`: 获取权限列表
- `POST /permissions`: 创建新权限
- `GET /roles`: 获取角色列表
- `POST /roles`: 创建新角色
- `PUT /roles/{role_id}`: 更新角色
- `DELETE /roles/{role_id}`: 删除角色
- `POST /users/{user_id}/roles`: 为用户分配角色
- `DELETE /users/{user_id}/roles/{role_id}`: 移除用户角色

### 5.5 系统端点
- `GET /health`: 健康检查

---

## 6. 中间件系统

### 6.1 中间件执行顺序
1. **SecurityHeadersMiddleware**: 添加安全响应头
2. **GlobalExceptionHandlerMiddleware**: 全局异常处理
3. **RequestLoggingMiddleware**: 请求日志记录
4. **CORSMiddleware**: 跨域资源共享处理

### 6.2 功能说明
- **异常处理**: 自动捕获并转换为标准HTTP响应
- **请求日志**: 记录所有API请求、响应时间、错误信息
- **安全头**: 添加HSTS、内容类型等安全响应头
- **CORS**: 配置跨域访问规则

---

## 7. 配置管理

使用 `pydantic-settings` 从环境变量和 `.env` 文件加载配置。

详细配置说明见：[配置管理指南](./CONFIGURATION.md)

---

## 8. 开发指南

### 8.1 添加新模块
1. 在`src/`下创建新的模块目录
2. 按需添加标准文件：`router.py`, `models.py`, `schemas.py`, `service.py`
3. 在`main.py`中注册路由器
4. 创建对应的数据库迁移

### 8.2 权限管理
1. 在`rbac/init_data.py`中定义新权限
2. 使用`rbac/dependencies.py`中的权限检查依赖
3. 在路由中应用权限检查：`Depends(require_permission)`

**系统级保护注意事项**:
- 新增系统级权限时，在 `BASE_PERMISSIONS` 中添加权限定义
- 新增系统级角色时，在 `BASE_ROLES` 中添加角色定义
- 系统级项目的 `is_system` 字段会在初始化时自动设置
- 删除和更新系统级项目会被自动拦截，确保系统稳定性

### 8.3 数据库操作
- 使用异步Session：`AsyncSession = Depends(get_async_db)`
- 所有数据库操作使用`async def`
- 遵循SQLAlchemy 2.0风格的查询语法

### 8.4 API开发规范
- 必须包含：`response_model`, `status_code`, `tags`, `summary`
- 使用HTTPException处理业务错误
- 直接返回业务数据，让框架处理序列化

---

## 9. 常见问题

### 9.1 权限检查
**问题**: 如何为API端点添加权限检查？
**解决**: 使用`rbac/dependencies.py`中的权限依赖：
```python
@router.get("/users", dependencies=[Depends(require_user_read)])
async def get_users(): ...
```

### 9.2 系统级保护机制
**问题**: 如何理解系统级角色和权限的保护机制？
**解决**: 
- **删除保护**: 系统级项目无法通过API删除，会返回400错误
- **更新保护**: 系统级角色只能修改显示名称和描述，权限分配不会生效
- **数据初始化**: 通过 `init_rbac_data()` 函数自动标记系统级项目
- **安全边界**: 系统级权限确保核心功能，业务级权限支持灵活扩展

### 9.3 数据库迁移
**问题**: 如何创建和应用数据库迁移？
**解决**: 
```bash
# 创建迁移
pnpm be:migrate:make "migration description"

# 应用迁移
pnpm be:migrate:up
```

### 9.4 异步操作
**问题**: 什么时候使用async/await？
**解决**: 所有涉及数据库、外部API、文件I/O的操作都应该使用async/await

---

*本文档将随着系统的演进持续更新。如有疑问或建议，请提交Issue或联系开发团队。* 