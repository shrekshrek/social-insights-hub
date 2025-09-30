# 🚀 部署指南

本项目支持开发环境和生产环境的分离部署。

## 📁 配置文件

- **开发环境**: `.env`
- **生产环境**: `.env.production` (所有服务共享)
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
- 📧 邮件测试: http://localhost:8025

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
   # - DATABASE_URL: 确保密码与POSTGRES_PASSWORD一致
   # - BACKEND_CORS_ORIGINS: 设置为实际域名
   # - NUXT_PUBLIC_API_BASE: 指向后端暴露的完整地址（含协议和 /api/v1），如 https://api.example.com/api/v1
   #   若生产环境通过统一域名或反向代理/CDN 暴露服务，也必须在部署脚本或容器环境变量中显式设置该值
   ```

2. **部署到生产环境**
   ```bash
   # 方式1: 使用部署脚本 (推荐)
   pnpm prod:deploy
   
   # 方式2: 手动部署
   pnpm prod:up
   ```

### 生产环境管理

```bash
# 查看服务状态
docker-compose -f docker-compose.prod.yml ps

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
- 📖 API文档: http://localhost/api/v1/docs
- 📧 邮件管理: http://localhost:8025

## 🔐 安全配置

### 生产环境密钥生成
```bash
# 生成后端JWT密钥
openssl rand -hex 32
# 将生成的密钥更新到 .env.production 中的 SECRET_KEY

# 生成前端Session密码
openssl rand -base64 32
# 将生成的密码更新到 .env.production 中的 NUXT_SESSION_PASSWORD

# 生成强密码（用于数据库）
openssl rand -base64 24
# 将生成的密码更新到 .env.production 中的 POSTGRES_PASSWORD
# 注意：同时更新 DATABASE_URL 中的密码部分
```

### 环境变量说明

| 变量名 | 开发环境 | 生产环境 | 说明 |
|--------|----------|----------|------|
| `ENVIRONMENT` | development | production | 环境标识 |
| `POSTGRES_PASSWORD` | postgres | 强密码 | PostgreSQL密码 |
| `SECRET_KEY` | 弱密钥(开发用) | 强密钥(生产用) | JWT签名密钥 |
| `DATABASE_URL` | localhost:5432 | postgres_db:5432 | 数据库连接 |
| `NUXT_SESSION_PASSWORD` | 示例值 | 强密码(生产用) | Session加密密码 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 30 | 15 | Token过期时间 |

## 🛠️ 故障排除

### 常见问题

1. **生产环境无法访问**
   ```bash
   # 检查容器状态
   docker-compose -f docker-compose.prod.yml ps
   
   # 查看后端日志
   docker-compose -f docker-compose.prod.yml logs backend
   ```

2. **数据库连接失败**
   ```bash
   # 检查数据库容器
   docker-compose -f docker-compose.prod.yml logs postgres_db
   ```

3. **前端无法访问后端API**
   ```bash
   # 检查Nginx配置
   docker-compose -f docker-compose.prod.yml logs nginx
   ```

## 📊 监控和维护

### 健康检查
```bash
# 检查后端健康状态
curl http://localhost/api/v1/health

# 检查前端状态
curl http://localhost
```

### 数据备份
```bash
# 备份生产数据库
docker-compose -f docker-compose.prod.yml exec postgres_db pg_dump -U postgres fastapi_db > backup.sql
```

## 🎯 最佳实践

1. **安全性**
   - 生产环境使用强密钥
   - 定期更新依赖包
   - 监控安全漏洞

2. **性能**
   - 定期清理Docker镜像
   - 监控资源使用情况
   - 优化数据库查询

3. **维护**
   - 定期备份数据
   - 监控日志异常
   - 及时更新配置 
