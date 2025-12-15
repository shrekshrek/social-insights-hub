# Claude Code 项目配置

本项目是一个全栈Web应用，基于 FastAPI (后端) 和 Nuxt 4 (前端) 构建。

## 项目结构
- `/backend` - FastAPI后端应用
- `/frontend` - Nuxt前端应用  
- `/docs` - 项目文档
- `/.claude` - Claude AI专用规则

## 核心开发规则
- **后端规则**: 见 `.claude/backend-rules.md`
- **前端规则**: 见 `.claude/frontend-rules.md`
- **工作流规则**: 见 `.claude/workflow-rules.md`

## 详细开发文档
- **后端详细规范**: `backend/CONTRIBUTING.md`
- **前端详细规范**: `frontend/CONTRIBUTING.md`

## 核心配置文件

### 环境配置
- **开发环境**: `.env` - 本地开发配置
- **生产环境**: `.env.production` - 所有服务统一配置
- **配置文档**: `docs/CONFIGURATION.md` - 详细配置管理指南

### 前端配置
- **统一路由权限**: `frontend/config/routes.ts` - 统一管理所有路由权限配置
- **权限常量定义**: `frontend/config/permissions.ts` - 与后端完全一致的权限常量
- **模块注册**: `frontend/nuxt.config.ts` - 新增模块时必须在 `extends` 数组中添加对应 layer

## 权限管理

权限采用代码驱动模式，启动时自动同步。

**快速添加权限**：
```python
*create_module_permissions("new_module", ["access", "read", "write"])
# 重启服务后自动同步
```

**详细指南**：
- 模块开发流程见 [`docs/MODULAR_DEVELOPMENT.md`](docs/MODULAR_DEVELOPMENT.md)
- 权限系统原理见 [`docs/PERMISSION_MANAGEMENT.md`](docs/PERMISSION_MANAGEMENT.md)

## 当前版本信息
- **Nuxt版本**: 4.1.0（注：4.1.1存在reka-ui兼容性问题，暂不升级）


### 代码修改原则
1. **优先编辑现有文件**，避免创建新文件
2. **不主动创建文档文件** (*.md) 除非明确要求
3. **遵循现有代码风格**，查看相邻文件了解规范
4. **保持简单** (KISS原则)，避免过度工程化

### 必需执行的检查
完成代码修改后，必须运行以下检查命令：

#### 后端检查
```bash
# Lint和格式化
pnpm be:lint    # 或 cd backend && uv run ruff check --fix && uv run ruff format

# 测试
pnpm be:test    # 或 cd backend && uv run pytest
```

#### 前端检查
```bash
# 类型检查
pnpm fe:typecheck   # 或 cd frontend && pnpm typecheck

# Lint检查
pnpm fe:lint        # 或 cd frontend && pnpm lint
```

### 常用开发命令

#### 环境管理
- `pnpm setup` - 首次安装所有依赖
- `pnpm dev` - 启动完整开发环境（自动执行数据库迁移和初始化）
- `pnpm stop` - 停止所有服务

> 注：首次运行 `pnpm dev` 时会自动创建：
> - 所有数据库表结构
> - 基础权限和角色数据
> - 默认管理员账号（admin/admin123）

#### 数据库操作
- `pnpm be:migrate:make "描述"` - 创建数据库迁移
- `pnpm be:migrate:up` - 执行数据库迁移（自动包含初始化数据）

#### 依赖管理
- `pnpm be:add <package>` - 添加后端依赖
- `pnpm fe:add <package>` - 添加前端依赖