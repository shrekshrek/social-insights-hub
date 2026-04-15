# 脉图智策

社交媒体数据智能分析平台。聚合抖音、微博、B站、小红书、快手、知乎、贴吧等平台数据，通过 LLM 进行筛选、实体提取、情感分析和竞品分析，提供项目化的监控与报告。

---

## ✨ 核心功能

- **社媒监测**：创建多平台监测项目，采集原文与评论，追踪舆情动态
- **新闻监测**：整合新闻渠道，自动切片分析，生成舆情报告
- **策略研究**：多渠道数据汇聚，LLM 辅助生成品牌策略报告
- **AI 统计**：跨渠道 AnalysisJob 管理，实时追踪分析进度与 LLM 成本
- **市场知识库**：上传文档并向量化，支持 RAG 语义检索
- **RBAC 权限系统**：代码驱动的角色权限管理，支持细粒度授权

---

## 🛠️ 技术栈

| 层 | 选型 |
|---|------|
| 后端 | FastAPI + Python 3.11+ + SQLAlchemy 2.0 (async) |
| 前端 | Nuxt 4 + Vue 3 + TypeScript + @nuxt/ui v4 |
| 数据库 | PostgreSQL 16 + Alembic 迁移 |
| 缓存/队列 | Redis 7 + Celery + APScheduler |
| AI/LLM | LangChain 1.0+ + DeepSeek API |
| 部署 | Docker Compose + Nginx |

---

## 🚀 快速开始

### 1. 环境准备

- 安装 [Docker](https://www.docker.com/products/docker-desktop/) 和 [pnpm](https://pnpm.io/installation)
- 克隆项目并进入目录

### 2. 初始化配置

```bash
cp .env.example .env
```

编辑 `.env`，至少设置以下项：

```bash
PROJECT_NAME=your_project_name   # Docker 资源隔离用
APP_NAME=脉图智策                  # 对外显示名称
DEEPSEEK_API_KEY=sk-...          # AI 分析必填
```

### 3. 启动开发环境

```bash
pnpm setup   # 首次：安装依赖、构建镜像
pnpm dev     # 启动所有服务（自动迁移 + 初始化权限数据）
```

启动后：
- **前端**：`http://localhost:3000`
- **API 文档**：`http://localhost:8000/docs`
- **默认账号**：`admin / admin123`（见 `.env` 的 `ADMIN_PASSWORD`）

---

## 📚 常用命令

| 命令 | 说明 |
|------|------|
| `pnpm dev` | 启动开发环境 |
| `pnpm dev:stop` | 停止所有服务 |
| `pnpm be:migrate:make "描述"` | 创建数据库迁移 |
| `pnpm be:migrate:up` | 执行数据库迁移 |
| `pnpm be:lint` | 后端 lint + 格式化 |
| `pnpm be:test` | 后端测试 |
| `pnpm fe:typecheck` | 前端类型检查 |
| `pnpm fe:lint` | 前端 lint |
| `pnpm prod:build` | 构建生产镜像 |
| `pnpm prod:deploy` | **（推荐）** 执行部署脚本，在生产服务器上启动应用 |
| `pnpm prod:up` | 在生产模式下（后台）启动所有服务 |
| `pnpm prod:down` | 停止并移除所有生产模式下的服务 |

> ℹ️ **生产迁移**：`prod:deploy` / `prod:up` 启动时会自动执行 `alembic upgrade head`，无需手动迁移。

---

## 📖 文档导航

**开发指南**：
- 开发流程 + 新模块开发：[`docs/MODULAR_DEVELOPMENT.md`](docs/MODULAR_DEVELOPMENT.md) ⭐ 必读
- 权限系统：[`docs/PERMISSION_MANAGEMENT.md`](docs/PERMISSION_MANAGEMENT.md)
- 配置管理：[`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)
- CI/CD 部署：[`docs/GITLAB_CI_VARIABLES.md`](docs/GITLAB_CI_VARIABLES.md)

**架构参考**：
- 后端架构：[`docs/backend-architecture.md`](docs/backend-architecture.md)
- 前端架构：[`docs/frontend-architecture.md`](docs/frontend-architecture.md)
- 爬虫数据结构：[`docs/CRAWLER_DATA_STRUCTURE.md`](docs/CRAWLER_DATA_STRUCTURE.md)
- 云端 Agent API：[`docs/云端分析平台API规范.md`](docs/云端分析平台API规范.md)

**设计文档**：
- Research Agent 设计：[`docs/research-agent-design.md`](docs/research-agent-design.md)
- 策略多渠道架构：[`docs/strategy-multi-source-architecture.md`](docs/strategy-multi-source-architecture.md)

**编码规范**：
- AI 编码规则：[`CLAUDE.md`](CLAUDE.md)
- 后端规范：[`backend/CODING_GUIDE.md`](backend/CODING_GUIDE.md)
- 前端规范：[`frontend/CODING_GUIDE.md`](frontend/CODING_GUIDE.md)
