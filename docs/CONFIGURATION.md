# 📋 配置管理指南

本项目以 `.env.example` / `.env.production.example` 为准；本文只保留“需要改什么 + 怎么验证”，避免重复粘贴整份模板。

## ✅ 30 秒配置

### 开发（本地）
1. `cp .env.example .env`
2. 编辑 `.env`：只需要改 `PROJECT_NAME`（必填）与 `APP_NAME`（可选）
3. `pnpm dev`

### 生产（服务器）
1. `cp .env.production.example .env.production`
2. 编辑 `.env.production`：替换所有 `CHANGE_THIS...`（含 `ADMIN_PASSWORD`）
3. （推荐）**本地先验证**：`cp .env.production .env.production.local` → 将 CORS 改为 `http://localhost` → 用 `docker-compose.prod.yml --env-file .env.production.local` 启动验证
4. `pnpm prod:deploy`（或 `pnpm prod:build && pnpm prod:up`）

### .env.production.local 说明

`.env.production.local` 是本地验证生产配置的专用文件，**不进版本库**。

用途：在本机用 `docker-compose.prod.yml` 跑一遍完整的生产环境，验证配置正确后再部署到服务器。与 `.env.production` 的区别通常只有 `BACKEND_CORS_ORIGINS=http://localhost`（线上是服务器 IP/域名）。

```bash
# 本地验证生产环境启动命令
docker-compose -f docker-compose.prod.yml --env-file .env.production.local up --build
```

## 🔑 必改项（生产环境）

- `POSTGRES_PASSWORD`：强密码
- `DATABASE_URL`：必须使用 `postgresql+psycopg://`（psycopg **v3**，非 psycopg2），并确保密码与 `POSTGRES_PASSWORD` 一致
- `SECRET_KEY`：`openssl rand -hex 32`
- `NUXT_SESSION_PASSWORD`：`openssl rand -base64 32`（至少 32 字符）
- `ADMIN_PASSWORD`：初始超管账号密码，**若仍为默认值 `admin123`，服务将拒绝启动**
- `BACKEND_CORS_ORIGINS`：填真实域名，支持逗号分隔或 JSON 数组（推荐逗号分隔）
- `NUXT_PUBLIC_API_BASE`：建议填带协议的完整地址（如 `https://example.com/api/v1`）
- `APP_NAME`：对外展示名（可选）

> ℹ️ `DATABASE_URL` 必须使用 `postgresql+psycopg://`（psycopg **v3**，非 psycopg2）：psycopg v3 同时支持同步和异步，`database.py` 的异步引擎会自动将其转换为 `asyncpg` 供 FastAPI 使用，而 Celery 同步引擎直接使用原始 URL（psycopg v3 同步模式）。若误用 psycopg2（`psycopg2://`）或直接填 `asyncpg`，Celery 任务将无法访问数据库。

## 🧪 验证与自查

```bash
# 验证开发 compose 配置
docker-compose config

# 验证生产 compose 配置
docker-compose --env-file .env.production -f docker-compose.prod.yml config
```

```bash
# 数据库连通性（容器内）
docker-compose exec postgres_db sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT 1;"'

# 服务健康检查
curl http://localhost/health
```

## 🔗 相关文档

- [后端架构](./backend-architecture.md) - 后端配置详解
- [GitLab CI/CD变量](./GITLAB_CI_VARIABLES.md) - CI/CD配置
- [开发规范](../CLAUDE.md) - 项目开发规范

---
