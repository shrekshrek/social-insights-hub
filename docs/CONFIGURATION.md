# 📋 配置管理指南

## 🎯 概述

本项目使用统一的配置管理策略，确保开发、测试和生产环境之间的配置一致性和安全性。

## 📁 配置文件

- `.env` - 开发环境配置
- `.env.example` - 开发环境配置模板
- `.env.production` - 生产环境统一配置 ⭐
- `.env.production.example` - 生产环境配置模板


## 🛠️ 环境配置详解

### 开发环境 (.env)

开发环境配置用于本地开发，包含所有服务的配置：

```bash
# ===== 环境标识 =====
ENVIRONMENT=development

# ===== PostgreSQL 配置 =====
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=fastapi_db

# ===== 后端配置 =====
DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres_db:5432/fastapi_db
REDIS_URL=redis://redis:6379
SECRET_KEY=your-secret-key-for-development-only
PROJECT_NAME=Full-Stack Starter API
API_PREFIX=/api/v1
ACCESS_TOKEN_EXPIRE_MINUTES=30

# ===== 前端配置 =====
NUXT_PUBLIC_API_BASE=http://localhost:8000/api/v1
NUXT_SESSION_PASSWORD=this-is-a-32-character-string-for-dev-only!
```

### 生产环境 (.env.production)

生产环境配置用于服务器部署，包含所有安全敏感的配置：

```bash
# ===== 环境标识 =====
ENVIRONMENT=production

# ===== PostgreSQL 配置 =====
POSTGRES_USER=postgres
POSTGRES_PASSWORD=CHANGE_THIS_STRONG_PASSWORD
POSTGRES_DB=fastapi_db

# ===== 后端配置 =====
DATABASE_URL=postgresql+psycopg://postgres:CHANGE_THIS_STRONG_PASSWORD@postgres_db:5432/fastapi_db
REDIS_URL=redis://redis:6379
SECRET_KEY=CHANGE_THIS_USE_OPENSSL_RAND_HEX_32_TO_GENERATE
PROJECT_NAME=Production API
API_PREFIX=/api/v1
ACCESS_TOKEN_EXPIRE_MINUTES=15
BACKEND_CORS_ORIGINS=["https://yourdomain.com"]

# ===== 前端配置 =====
NUXT_PUBLIC_API_BASE=https://yourdomain.com/api/v1
NUXT_SESSION_PASSWORD=CHANGE_THIS_MUST_BE_AT_LEAST_32_CHARS_USE_OPENSSL

```

> ℹ️ **提示**：应用在初始化数据库引擎时会自动将 `postgresql+psycopg://` 的连接字符串转换为异步驱动 `postgresql+asyncpg://`，因此无需手动修改上述配置。

> ⚠️ **注意**：`NUXT_PUBLIC_API_BASE` 必须是带协议的完整地址（如 `https://example.com/api/v1`），否则前端代理会拒绝请求并返回 500。

## 🔐 安全密钥生成

### 生成安全密钥的命令

```bash
# 生成后端JWT密钥（32字节十六进制）
openssl rand -hex 32

# 生成前端Session密码（32字符Base64）
openssl rand -base64 32

# 生成数据库强密码（24字符Base64）
openssl rand -base64 24
```

### 密钥更新步骤

1. **生成新密钥**
   ```bash
   # 生成所有需要的密钥
   echo "SECRET_KEY: $(openssl rand -hex 32)"
   echo "NUXT_SESSION_PASSWORD: $(openssl rand -base64 32)"
   echo "POSTGRES_PASSWORD: $(openssl rand -base64 24)"
   ```

2. **更新配置文件**
   - 打开 `.env.production`
   - 替换所有 `CHANGE_THIS_` 开头的占位符
   - 确保 `DATABASE_URL` 中的密码与 `POSTGRES_PASSWORD` 一致

3. **验证配置**
   ```bash
   # 检查配置文件语法
   docker-compose -f docker-compose.prod.yml config
   ```

## 🚀 Docker Compose 集成

### 配置加载机制

Docker Compose 通过 `env_file` 指令加载配置：

```yaml
# docker-compose.prod.yml
services:
  backend:
    env_file:
      - .env.production  # 统一配置文件
  
  frontend:
    env_file:
      - .env.production  # 统一配置文件
  
  postgres_db:
    env_file:
      - .env.production  # 统一配置文件
```

### 环境变量优先级

1. Docker Compose 文件中的 `environment` 定义（最高优先级）
2. `env_file` 指定的文件
3. Shell 环境变量
4. `.env` 文件（Docker Compose 默认加载）

## 📝 配置最佳实践

### 1. 密钥管理
- **永不提交**: 绝不将包含真实密钥的配置文件提交到Git
- **定期轮换**: 定期更新生产环境的密钥
- **强密码**: 使用密码生成器创建强密码
- **备份密钥**: 安全地备份生产环境密钥

### 2. 环境隔离
- **开发配置**: 使用弱密钥，方便开发调试
- **生产配置**: 使用强密钥，确保安全性
- **测试配置**: 可以复制开发配置，独立的数据库

### 3. 配置验证
```bash
# 验证开发环境配置
docker-compose config

# 验证生产环境配置
docker-compose -f docker-compose.prod.yml config

# 检查环境变量
docker-compose run backend env | grep -E "(DATABASE|SECRET|API)"
```

### 4. 配置文档化
- 在 `.env.example` 中记录所有配置项
- 为每个配置项添加注释说明
- 标记必需和可选的配置项

## 🔄 配置更新流程

### 添加新配置项

1. **更新模板文件**
   ```bash
   # 编辑开发环境模板
   nano .env.example
   
   # 编辑生产环境模板
   nano .env.production.example
   ```

2. **更新实际配置**
   ```bash
   # 更新开发环境
   nano .env
   
   # 更新生产环境（仅在服务器上）
   nano .env.production
   ```

3. **更新代码**
   - 后端: 更新 `backend/src/config.py`
   - 前端: 更新 `frontend/nuxt.config.ts`

4. **更新文档**
   - 更新本文档
   - 更新 `README.md` 中的配置说明

## 🐛 故障排除

### 常见配置问题

#### 1. 数据库连接失败
```bash
# 检查数据库配置
echo $DATABASE_URL

# 测试连接
docker-compose exec backend python -c "from src.database import engine; print('Connected!')"
```

#### 2. 前后端通信失败
```bash
# 检查API地址配置
echo $NUXT_PUBLIC_API_BASE

# 检查CORS配置
echo $BACKEND_CORS_ORIGINS
```

#### 3. 认证失败
```bash
# 检查密钥长度
echo -n $SECRET_KEY | wc -c           # 应该是64字符（32字节十六进制）
echo -n $NUXT_SESSION_PASSWORD | wc -c # 应该至少32字符
```

### 配置检查清单

- [ ] 所有 `CHANGE_THIS_` 占位符已替换
- [ ] `DATABASE_URL` 中的密码与 `POSTGRES_PASSWORD` 一致
- [ ] `NUXT_SESSION_PASSWORD` 至少32字符
- [ ] `SECRET_KEY` 使用 `openssl rand -hex 32` 生成
- [ ] `BACKEND_CORS_ORIGINS` 包含正确的域名

## 📊 配置对照表

| 配置项 | 开发环境默认值 | 生产环境要求 | 说明 |
|--------|---------------|-------------|------|
| `ENVIRONMENT` | development | production | 环境标识 |
| `POSTGRES_PASSWORD` | postgres | 强密码 | 数据库密码 |
| `SECRET_KEY` | 弱密钥 | 64字符十六进制 | JWT签名密钥 |
| `NUXT_SESSION_PASSWORD` | 32字符示例 | 32+字符强密码 | Session加密 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 30 | 15 | Token过期时间 |
| `BACKEND_CORS_ORIGINS` | ["http://localhost:3000"] | ["https://yourdomain.com"] | 允许的源 |

## 🔗 相关文档

- [部署指南](../DEPLOYMENT.md) - 完整的部署流程
- [后端架构](./backend-architecture.md) - 后端配置详解
- [GitLab CI/CD变量](./GITLAB_CI_VARIABLES.md) - CI/CD配置
- [开发规范](../AGENTS.md) - 项目开发规范

---
