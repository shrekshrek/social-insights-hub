# 📋 配置管理指南

本项目以 `.env.example` / `.env.production.example` 为准；本文只保留“需要改什么 + 怎么验证”，避免重复粘贴整份模板。

## ✅ 30 秒配置

### 开发（本地）
1. `cp .env.example .env`
2. 编辑 `.env`：只需要改 `PROJECT_NAME`（必填）与 `APP_NAME`（可选）
3. `pnpm dev`

### 生产（服务器）
1. `cp .env.production.example .env.production`
2. 编辑 `.env.production`：替换所有 `CHANGE_THIS...`
3. `pnpm prod:deploy`（或 `pnpm build && pnpm prod:up`）
4. 如有新增迁移：`pnpm be:migrate:up`

## 🔑 必改项（生产环境）

- `POSTGRES_PASSWORD`：强密码
- `DATABASE_URL`：保持 `postgresql+psycopg://`，并确保密码与 `POSTGRES_PASSWORD` 一致
- `SECRET_KEY`：`openssl rand -hex 32`
- `NUXT_SESSION_PASSWORD`：`openssl rand -base64 32`（至少 32 字符）
- `BACKEND_CORS_ORIGINS`：填真实域名，支持逗号分隔或 JSON 数组（推荐逗号分隔）
- `NUXT_PUBLIC_API_BASE`：建议填带协议的完整地址（如 `https://example.com/api/v1`）
- `APP_NAME`：对外展示名（可选）

> ℹ️ `DATABASE_URL` 推荐使用 `psycopg`：Alembic 迁移走同步驱动；应用运行时会自动转换为 `postgresql+asyncpg://` 用于异步访问。

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

- [部署指南](../DEPLOYMENT.md) - 完整的部署流程
- [后端架构](./backend-architecture.md) - 后端配置详解
- [GitLab CI/CD变量](./GITLAB_CI_VARIABLES.md) - CI/CD配置
- [开发规范](../AGENTS.md) - 项目开发规范

---
