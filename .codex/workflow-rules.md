# 工作流规则

## 核心原则：目录优先
执行任何命令前，**必须**确认当前工作目录

## 前端操作规则
- **工作目录**: 必须在 `/frontend`
- **包管理器**: 使用 `pnpm`
- **优先使用根目录命令**:
  - `pnpm fe:install` - 安装依赖
  - `pnpm fe:add <pkg>` - 添加依赖
  - `pnpm fe:dev` - 启动开发

## 后端操作规则
- **工作目录**: 必须在 `/backend`
- **包管理器**: 使用 `uv`
- **优先使用根目录命令**:
  - `pnpm be:install` - 安装依赖
  - `pnpm be:add <pkg>` - 添加依赖
  - `pnpm be:dev` - 启动开发
  - `pnpm be:migrate:up` - 执行迁移

## 全局命令（在根目录执行）
- `pnpm setup` - 首次安装
- `pnpm dev` - 启动所有服务
- `pnpm stop` - 停止所有服务
- `pnpm build` - 构建生产版本

## 权限系统规则

### 添加简单权限（不创建新模块）
1. **后端定义**: `backend/src/rbac/init_data.py` 添加权限
2. **重启同步**: `pnpm dev` 
3. **前端常量**: `frontend/config/permissions.ts` 添加权限常量
4. **路由配置**: `frontend/config/routes.ts` 配置路由权限

### 创建新模块（含新 Layer）
需额外步骤：
5. **注册Layer**: `frontend/nuxt.config.ts` 的 `extends` 数组添加 Layer

> 📖 完整步骤见 [`docs/MODULAR_DEVELOPMENT.md`](../docs/MODULAR_DEVELOPMENT.md#快速开始30秒创建新模块)

## 重要提醒
1. 不要在错误的目录执行包管理命令
2. 前端用 pnpm，后端用 uv
3. 优先使用根目录的 pnpm 脚本命令
4. 新增权限时保持前后端定义一致