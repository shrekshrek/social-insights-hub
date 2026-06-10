# 🚀 部署指南

## 三步部署流程

| 步骤 | 命令 | 配置文件 | 说明 |
|------|------|----------|------|
| 1. 本地开发 | `pnpm dev` | `.env` | 热重载，后端容器化 |
| 2. 本地验证生产 | `pnpm prod:local` | `.env.production.local` | 用生产镜像在本地跑 |
| 3. 服务器部署 | `pnpm prod:build && pnpm prod:up` | `.env.production` | 正式生产环境 |

## 📁 配置文件

- **开发环境**: `.env`
- **本地生产验证**: `.env.production.local`
- **生产环境**: `.env.production`
- **详细配置说明**: 参见 [配置管理指南](docs/CONFIGURATION.md)

## 🔧 开发环境

### 启动开发环境
```bash
# 一键启动开发环境
pnpm dev

# 这会启动：
# - 后端容器 (FastAPI + 数据库 + Redis)
# - 前端本地服务器 (Nuxt.js)
```

### 开发环境访问
- 🌐 前端: http://localhost:3000
- 🔧 后端API: http://localhost:8000
- 📖 API文档: http://localhost:8000/docs

## 🧪 部署前本地验证

在正式推送到服务器之前，用 `docker-compose.prod.yml` 在本地跑完整的生产镜像，提前发现构建或运行时问题。

### 1. 准备本地生产配置

```bash
# 基于 .env.production 复制，覆盖本地需要修改的值
cp .env.production .env.production.local
```

编辑 `.env.production.local`，只需改一处：
```bash
# CORS 改为 localhost（本地访问）
BACKEND_CORS_ORIGINS=http://localhost
```

> 其余配置（密码、密钥、AI Key 等）与 `.env.production` 保持一致，确保测试环境与生产完全一致。

### 2. 本地启动生产栈

```bash
pnpm prod:local
```

### 3. 验证

- 🌐 前端: http://localhost
- 🔧 API 文档: http://localhost/docs
- 登录测试、核心功能流程跑通后，再部署到服务器。

### 4. 清理

```bash
pnpm prod:local:down
```

---

## 🚀 生产环境

### 首次部署准备

1. **创建生产环境配置**
   ```bash
   # 复制配置模板
   cp .env.production.example .env.production
   
   # 编辑配置文件
   nano .env.production
   
   # 重要：更新以下配置
   # - POSTGRES_PASSWORD: 使用强密码
   # - SECRET_KEY: 使用 openssl rand -hex 32 生成
   # - NUXT_SESSION_PASSWORD: 使用 openssl rand -base64 32 生成
   # - APP_NAME: （可选）应用显示名称（API 文档 title / 网站 title）
   # - DATABASE_URL: 必须使用 postgresql+psycopg://（psycopg v3，非 psycopg2；代码自动为 FastAPI 转换为 asyncpg，Celery 同步引擎保留 psycopg v3 同步模式），并确保密码与 POSTGRES_PASSWORD 一致
   # - BACKEND_CORS_ORIGINS: 设置为实际域名
   # - NUXT_PUBLIC_API_BASE: 指向后端暴露的完整地址（含协议和 /api/v1），如 https://api.example.com/api/v1
   #   若生产环境通过统一域名或反向代理/CDN 暴露服务，也必须在部署脚本或容器环境变量中显式设置该值
   ```

2. **部署到生产环境**
   ```bash
   # 方式1: 使用部署脚本 (推荐)
   pnpm prod:deploy
   
   # 方式2: 手动部署
   pnpm prod:build && pnpm prod:up
   ```

   > ⚠️ **重要**：每次部署时需确保将**根目录配置文件**一并上传到服务器，包括：
   > - `docker-compose.prod.yml` — Docker 服务编排，含网络、资源限制等关键配置
   > - `nginx.conf` — Nginx 反代配置
   >
   > 如果只上传 `backend/` 或 `frontend/` 子目录，根目录文件不会更新，可能导致服务器运行旧配置。

### 生产环境管理

```bash
# 查看服务状态
docker-compose --env-file .env.production -f docker-compose.prod.yml ps

# 查看日志
pnpm prod:logs

# 重启服务
pnpm prod:restart

# 停止服务
pnpm prod:down
```

### 生产环境访问
- 🌐 应用: http://localhost (通过Nginx代理)
- 🔧 API: http://localhost/api/v1
- 📖 API文档: http://localhost/docs

> ℹ️ **生产迁移提示**：生产环境的后端容器启动不会自动执行 Alembic 迁移。
> 如有新增迁移，请在部署后手动执行一次：`pnpm be:migrate:up`。

> 🤖 **CI/CD 自动部署**：项目目前已 100% 接入了更智能、更敏捷的 **GitHub Actions** 自动化 CI/CD 部署。
> 您只需在本地将代码推送到 GitHub 的 `main` 分支（`git push origin main`），新加坡生产服务器便会自动拉取最新代码、智能增量重构镜像、平滑滚动重启，完全解放手动部署的劳动力。
> 
> ### 🤖 自动化 CI/CD 部署指南 (GitHub Actions)
> 
> 流水线配置文件位于项目根目录的 `.github/workflows/deploy.yml` 下。
> 
> ⛔ **lint 前置门禁**：push 到 main 后，流水线先执行静态检查（后端 ruff + 前端 eslint/vue-tsc，复用 `.github/workflows/lint.yml`），**任一检查失败则不会部署**。本地提交前跑 `pnpm be:lint` / `pnpm fe:lint` 可避免被门禁拦下。多次连续 push 时部署串行排队，不会并发交错。
> 
> #### 1. 服务器端 GitOps 一次性改造
> 为确保新加坡服务器具备免密拉取您 GitHub 私有仓库的最高安全级别权限，需进行如下注册：
> 1. **在服务器生成 SSH 密钥对**：
>    ```bash
   ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
   cat ~/.ssh/id_ed25519.pub
   ```
> 2. **在 GitHub 授权**：打开 GitHub 项目主页 -> **Settings -> Deploy keys -> Add deploy key**，将上述服务器公钥粘贴进去并保存（只读权限即可）。
> 3. **服务器端目录托管化**：
>    * 将原有手工覆盖的运行目录重命名备份：`mv /root/social-insights-hub /root/social-insights-hub_backup`
>    * 克隆官方仓库到运行目录：`git clone git@github.com:shrekshrek/social-insights-hub.git /root/social-insights-hub`
>    * 迁回本地敏感配置文件：`cp /root/social-insights-hub_backup/.env.production /root/social-insights-hub/`（及 SSL 证书文件夹等）。
> 
> #### 2. GitHub 仓库 Secrets 密钥注入
> 请前往您的 GitHub 仓库页面 -> **Settings -> Secrets and variables -> Actions -> 点击 New repository secret**，添加以下 3 个加密机密变量：
> 
> | 变量名 (Secret Name) | 对应值内容 (Value) | 如何获取或填写？ |
> | :--- | :--- | :--- |
> | **`DEPLOY_HOST`** | `43.159.61.34` | 新加坡生产服务器的公网 IP 地址 |
> | **`DEPLOY_USER`** | `root` | 登录服务器使用的用户名 |
> | **`SSH_PRIVATE_KEY`** | `您本地 Mac 上的 id_rsa 私钥文本` | 完整复制您本地 `~/.ssh/id_rsa` 的私钥内容（包含 BEGIN/END 首尾标识行）。<br>💡 *Mac 本地终端极速复制命令*：`cat ~/.ssh/id_rsa | pbcopy`（直接进剪贴板，Cmd+V 即可）。 |
> 
> #### 3. 智能增量判定构建优势 (Smart Increment Sensor)
> 本部署流内置了全行业最先进的「前后端增量感知过滤器」：
> *   **当只修改后端 Python 代码或提示词链时**：流水线自动识别，**跳过**最耗时（1-2分钟）的前端 Nuxt 全量重编译，在 **10 秒** 内实现秒级热更新重启，极力降低生产服务器的负荷与停机干扰！
> *   **当修改了前端 Vue 页面代码时**：流水线自动判定，强制触发前端无缓存重新编译打包，并在成功后执行内存缓存刷新。
> 
> ---

## 🔐 安全配置

### 生产环境密钥生成（写入 `.env.production`）
```bash
openssl rand -hex 32     # SECRET_KEY
openssl rand -base64 32  # NUXT_SESSION_PASSWORD（至少32字符）
openssl rand -base64 24  # POSTGRES_PASSWORD（强密码）
```

> ⚠️ 记得同步更新 `DATABASE_URL` 中的数据库密码部分，确保与 `POSTGRES_PASSWORD` 一致。

## 🛠️ 故障排除

### 常见问题

1. **生产环境无法访问**
   ```bash
   # 检查容器状态
   docker-compose --env-file .env.production -f docker-compose.prod.yml ps
   
   # 查看后端日志
   docker-compose --env-file .env.production -f docker-compose.prod.yml logs backend
   ```

2. **数据库连接失败**
   ```bash
   # 检查数据库容器
   docker-compose --env-file .env.production -f docker-compose.prod.yml logs postgres_db
   ```

3. **前端无法访问后端API**
   ```bash
   # 检查Nginx配置
   docker-compose --env-file .env.production -f docker-compose.prod.yml logs nginx
   ```

4. **服务间 DNS 失联（采集结果全为0、服务间无法互相访问）**

   **原因**：单独重建某个容器（如 `prod-crawl4ai`）时，若未用完整的 compose 文件，Docker 会为其创建新网络，导致与其他容器网络隔离。

   **排查**：
   ```bash
   docker inspect prod-crawl4ai | grep -A5 Networks
   # 如果网络名不是 sih_prod_network，说明已漂移
   ```

   **临时修复**（不重启其他服务）：
   ```bash
   docker network connect --alias crawl4ai sih_prod_network prod-crawl4ai
   ```

   **根本解决**：确保 `docker-compose.prod.yml` 中所有服务都声明了 `networks: - sih_net`，且 `networks` 段使用 `name: sih_prod_network` 固定网络名。之后任何单容器重建都不会产生网络漂移。

## 📊 监控和维护

### 健康检查
```bash
# 检查后端健康状态
curl http://localhost/health

# 检查前端状态
curl http://localhost
```

### 数据备份
```bash
# 备份生产数据库（使用环境变量）
docker-compose --env-file .env.production -f docker-compose.prod.yml exec postgres_db sh -c 'pg_dump -U $POSTGRES_USER $POSTGRES_DB' > backup.sql
```
