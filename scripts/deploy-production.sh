#!/bin/bash

# 生产环境部署脚本
# 使用方法: ./scripts/deploy-production.sh

set -e  # 遇到错误立即退出

echo "🚀 Starting production deployment..."
echo "=================================="

# 检查根目录的统一配置文件
if [ ! -f ".env.production" ]; then
    echo "❌ Error: .env.production not found in root directory!"
    
    # 尝试从示例文件创建
    if [ -f ".env.production.example" ]; then
        echo "📋 Creating from example file..."
        cp .env.production.example .env.production
        echo "⚠️  IMPORTANT: Edit .env.production with your production values:"
        echo "   - Generate SECRET_KEY: openssl rand -hex 32"
        echo "   - Generate NUXT_SESSION_PASSWORD: openssl rand -base64 32"
        echo "   - Update POSTGRES_PASSWORD with a strong password"
        echo "   - Configure SMTP settings for your mail service"
        echo "   - Update BACKEND_CORS_ORIGINS with your domain"
        exit 1
    else
        echo "💡 Please create production environment configuration first."
        echo "   Copy .env.production.example to .env.production and update values."
        exit 1
    fi
fi

# 检查配置是否已更改
if grep -q "CHANGE_THIS" .env.production; then
    echo "⚠️  WARNING: Some configuration values have not been changed from defaults!"
    echo ""
    echo "   Please update ALL values containing 'CHANGE_THIS' in .env.production:"
    echo "   - POSTGRES_PASSWORD: Use a strong password"
    echo "   - SECRET_KEY: Generate with 'openssl rand -hex 32'"
    echo "   - NUXT_SESSION_PASSWORD: Generate with 'openssl rand -base64 32'"
    echo "   - SMTP settings: Configure your email service"
    echo ""
    exit 1
fi

# 验证关键配置的一致性
echo "🔍 Validating configuration consistency..."
POSTGRES_PWD=$(grep "^POSTGRES_PASSWORD=" .env.production | cut -d '=' -f2 | tr -d '"')
if ! grep -q "postgresql.*$POSTGRES_PWD@postgres_db" .env.production; then
    echo "⚠️  WARNING: DATABASE_URL password doesn't match POSTGRES_PASSWORD!"
    echo "   Ensure both use the same password value."
    exit 1
fi

if [ ! -f "docker-compose.prod.yml" ]; then
    echo "❌ Error: docker-compose.prod.yml not found!"
    exit 1
fi

# 停止现有的生产环境容器（如果存在）
echo "🛑 Stopping existing production containers..."
docker-compose -f docker-compose.prod.yml down 2>/dev/null || true

# 构建生产环境镜像
echo "🏗️ Building production images..."
docker-compose -f docker-compose.prod.yml build --no-cache

# 启动生产环境
echo "🚀 Starting production services..."
docker-compose -f docker-compose.prod.yml up -d

# 等待服务启动
echo "⏳ Waiting for services to start..."
sleep 10

# 检查服务状态
echo "🔍 Checking service status..."
docker-compose -f docker-compose.prod.yml ps

# 检查后端健康状态
echo "🏥 Checking backend health..."
if curl -f -s http://localhost/api/v1/docs > /dev/null 2>&1; then
    echo "✅ Backend API docs are accessible!"
elif curl -f -s http://localhost:8000/docs > /dev/null 2>&1; then
    echo "✅ Backend is running (direct access)!"
else
    echo "⚠️ Backend health check failed. Checking logs..."
    docker-compose -f docker-compose.prod.yml logs --tail=20 backend
fi

echo "=================================="
echo "🎉 Production deployment completed!"
echo ""
echo "📍 Services:"
echo "   🌐 Application: http://localhost"
echo "   🔧 API: http://localhost/api/v1"
echo "   📖 API Docs: http://localhost/api/v1/docs"
echo "   📧 MailHog: http://localhost:8025"
echo ""
echo "📊 To view logs:"
echo "   docker-compose -f docker-compose.prod.yml logs -f"
echo ""
echo "🛑 To stop:"
echo "   pnpm prod:down" 