# 全栈脚手架：FastAPI + Nuxt 4

这是一个功能强大、开箱即用的全栈Web应用脚手架，基于 **FastAPI (后端)** 和 **Nuxt 4 (前端)** 构建。它旨在为需要快速启动新项目的开发者提供一个坚实、现代化的起点。

---

## ✨ 核心特性

-   **现代化技术栈**:
    -   **后端**: FastAPI, PostgreSQL, SQLAlchemy (异步), Celery, Redis
    -   **前端**: Nuxt 4, Vue 3, Pinia, `@nuxt/ui`, Tailwind CSS
-   **完全容器化**: 使用 Docker 和 Docker Compose 提供一致、可复现的开发与生产环境。
-   **代码驱动RBAC权限系统**:
    -   权限在代码中定义，启动时自动同步到数据库，确保一致性。
    -   前端 `usePermissions` 组合式函数和 `<PermissionGuard>` 组件，轻松实现细粒度权限控制。
    -   支持权限的完全自动化管理（增删改），开发者零配置。
-   **Nuxt Layers 架构**: 前端采用领域驱动设计，模块化、可扩展性强。
-   **统一的API与错误处理**: 全局 `useApi` 组合式函数，简化API调用，自动处理加载状态、错误和认证。
-   **类型安全**: 从数据库到API，再到前端组件，全程使用 TypeScript 和 Pydantic，提供端到端的类型安全。
-   **清晰的工作流与部署方案**: 提供了从开发到部署的完整文档和脚本。

---

## 🚀 快速开始

### 1. 环境准备

-   安装 [Docker](https://www.docker.com/products/docker-desktop/) 和 [pnpm](https://pnpm.io/installation)。
-   克隆本项目：`git clone <your-repo-url>`
-   进入项目目录：`cd <your-repo-folder>`

### 2. 初始化设置

1.  **复制环境变量文件**:
    ```bash
    cp .env.example .env
    ```
2.  **设置项目名称** (重要！):
    
    编辑 `.env` 文件，设置唯一的 `PROJECT_NAME`：
    ```bash
    # 使用有意义的项目名称，如: crm, admin, api_v2
    PROJECT_NAME=your_project_name
    ```
    
    > 💡 **多项目开发**: 如果你基于此脚手架开发多个项目，每个项目的 `PROJECT_NAME` 必须不同。这样可以避免 Docker 容器和数据库冲突，让多个项目同时运行。

3.  **一键安装与构建**:
    ```bash
    pnpm setup
    ```
    *此命令会安装所有前后端依赖，并首次构建 Docker 镜像。*

### 3. 启动开发环境

执行以下命令，一键启动所有服务：

```bash
pnpm dev
```

启动后：
-   **前端应用** 访问: `http://localhost:3000`
-   **后端API文档** 访问: `http://localhost:8000/docs`

---

## 📚 主要命令

所有命令都应在项目**根目录**下执行。

| 命令 | 描述 |
| :--- | :--- |
| `pnpm setup` | **首次安装**：安装所有依赖并预构建Docker镜像。|
| `pnpm dev` | **日常开发**：一键启动整个开发环境。 |
| `pnpm stop` | **停止服务**：停止并移除所有开发容器。 |
| `pnpm cleanup` | **清理资源**：交互式清理 Docker 容器和数据卷。 |

### 后端命令 (`be:*`)

| 命令 | 描述 |
| :--- | :--- |
| `pnpm be:install` | 安装后端的 Python 依赖。 |
| `pnpm be:add <包名>` | 向后端添加一个新的 Python 依赖。 |
| `pnpm be:migrate:make "<信息>"` | **(常用)** 生成一个新的数据库迁移脚本。 |
| `pnpm be:migrate:up` | **(常用)** 应用所有数据库迁移。 |
| `pnpm be:shell` | 进入正在运行的后端容器的 Shell 环境。 |

### 生产部署命令 (`prod:*`)

| 命令 | 描述 |
| :--- | :--- |
| `pnpm build` | 构建用于生产环境的前后端 Docker 镜像。 |
| `pnpm prod:deploy`| **(推荐)** 执行部署脚本，在生产服务器上启动应用。|
| `pnpm prod:up` | 在生产模式下（后台）启动所有服务。 |
| `pnpm prod:down`| 停止并移除所有生产模式下的服务。 |

---

## 📚 文档导航

**🚀 快速上手**：
- 新项目开始：本文档 → [快速开始](#🚀-快速开始)
- 开发环境：本文档 → [主要命令](#📚-主要命令)

**👨‍💻 开发指南**：
- 模块化开发：[`docs/MODULAR_DEVELOPMENT.md`](docs/MODULAR_DEVELOPMENT.md) ⭐ 新手必读
- 后端规范：[`backend/CONTRIBUTING.md`](backend/CONTRIBUTING.md)
- 前端规范：[`frontend/CONTRIBUTING.md`](frontend/CONTRIBUTING.md)
- 工作流程：[`docs/WORKFLOW.md`](docs/WORKFLOW.md)

**⚙️ 专项功能**：
- 权限管理：[`docs/PERMISSION_MANAGEMENT.md`](docs/PERMISSION_MANAGEMENT.md)
- 配置管理：[`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)
- Claude配置：[`CLAUDE.md`](CLAUDE.md)

---

## 🔄 多项目开发

如果你基于此脚手架开发多个项目，需要注意：

### 项目隔离机制

每个项目通过 `PROJECT_NAME` 环境变量实现资源隔离：
- **Docker 容器名**: `{PROJECT_NAME}_postgres_db_1`, `{PROJECT_NAME}_backend_1`
- **数据卷名**: `{PROJECT_NAME}_postgres_data`, `{PROJECT_NAME}_redis_data`
- **数据库名**: `{PROJECT_NAME}_db`

### 最佳实践

1. **设置唯一的项目名**
   ```bash
   # 项目 A (.env)
   PROJECT_NAME=crm_app
   
   # 项目 B (.env)
   PROJECT_NAME=admin_panel
   ```

2. **同时运行多个项目**
   ```bash
   # 项目 A
   cd /path/to/project-a
   pnpm dev  # 运行在 localhost:3000
   
   # 项目 B (新终端)
   cd /path/to/project-b
   # 需要修改前端端口或停止项目 A 的前端
   ```

3. **切换项目时的注意事项**
   - 确保每个项目的 `.env` 文件都设置了不同的 `PROJECT_NAME`
   - 使用 `pnpm cleanup` 清理不用的 Docker 资源
   - 数据库数据会保留在各自的数据卷中

4. **端口占用处理**
   - PostgreSQL (5432)、Redis (6379)、Backend (8000) 端口会被共享
   - 如需同时运行多个项目，需要修改 `docker-compose.yml` 中的端口映射

---

## 🧭 深入了解

想要更深入地理解本项目的设计和工作流程？请查阅以下文档：

-   **部署指南**: [`DEPLOYMENT.md`](./DEPLOYMENT.md) - **(必读)** 获取生产环境部署、配置和维护的详细步骤。
-   **配置管理**: [`docs/CONFIGURATION.md`](./docs/CONFIGURATION.md) - 了解环境配置的统一管理策略。
-   **开发工作流**: [`docs/WORKFLOW.md`](./docs/WORKFLOW.md) - 了解如何从零开始开发一个新功能。
-   **前端架构**: [`docs/frontend-architecture.md`](./docs/frontend-architecture.md) - 深入理解前端 Nuxt Layers 架构。
-   **后端架构**: [`docs/backend-architecture.md`](./docs/backend-architecture.md) - 深入理解后端 FastAPI 模块化设计。
-   **权限管理指南**: [`docs/PERMISSION_MANAGEMENT.md`](./docs/PERMISSION_MANAGEMENT.md) - 代码驱动的权限管理系统详解。 
