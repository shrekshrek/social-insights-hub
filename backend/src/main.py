import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi import status
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession
from src.schemas import CustomBaseModel

from src.auth.router import router as auth_router
from src.users.router import router as users_router
from src.rbac.router import router as rbac_router
from src.config import settings
from src.database import get_async_db, AsyncSessionLocal
from src.rbac.init_data import init_rbac_data
from src.middleware import (
    RequestLoggingMiddleware,
    GlobalExceptionHandlerMiddleware,
    SecurityHeadersMiddleware,
)
from src.rate_limit import limiter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("🚀 启动应用...")

    # 启动时同步权限
    try:
        async with AsyncSessionLocal() as db:
            logger.info("开始权限同步...")
            await init_rbac_data(db)
            logger.info("✅ 权限同步成功")
    except Exception as e:
        logger.error(f"❌ 权限同步失败: {e}", exc_info=True)
        # 权限同步失败不阻止应用启动（开发环境容错）
        logger.warning("⚠️ 应用将以现有权限配置启动")

    yield  # 应用运行期间

    # 关闭时清理
    logger.info("📴 应用关闭")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API for the full-stack starter project.",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# 响应模型定义
class HealthCheckDetail(CustomBaseModel):
    status: str
    message: str = None


class HealthResponse(CustomBaseModel):
    status: str
    service: str
    version: str = None
    checks: dict[str, str] = None


class RootResponse(CustomBaseModel):
    message: str
    version: str


# 添加中间件（注意顺序很重要）
# 1. 安全头中间件
app.add_middleware(SecurityHeadersMiddleware)

# 2. 全局异常处理中间件
app.add_middleware(GlobalExceptionHandlerMiddleware)

# 3. 请求日志中间件
app.add_middleware(RequestLoggingMiddleware)

# 4. CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "X-Requested-With",
    ],
)


# 健康检查端点
@app.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    tags=["Health"],
    summary="Health check",
)
async def health_check(
    db: AsyncSession = Depends(get_async_db), include_details: bool = False
):
    """
    健康检查端点

    Args:
        include_details: 是否包含详细的检查信息
    """
    from sqlalchemy import text
    from src.redis_client import get_redis_client

    health_status = {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION if include_details else None,
        "checks": {} if include_details else None,
    }

    if include_details:
        # 检查数据库连接
        try:
            await db.execute(text("SELECT 1"))
            health_status["checks"]["database"] = "ok"
        except Exception as e:
            health_status["checks"]["database"] = f"error: {str(e)}"
            health_status["status"] = "unhealthy"

        # 检查 Redis 连接
        try:
            redis_client = None
            async for client in get_redis_client():
                redis_client = client
                break

            if redis_client:
                await redis_client.ping()
                health_status["checks"]["redis"] = "ok"
            else:
                health_status["checks"]["redis"] = "error: unable to connect"
                health_status["status"] = (
                    "degraded"  # Redis 不是必需的，所以标记为 degraded
                )
        except Exception as e:
            health_status["checks"]["redis"] = f"error: {str(e)}"
            health_status["status"] = "degraded"

    return HealthResponse(**health_status)


# 根路径
@app.get(
    "/",
    response_model=RootResponse,
    status_code=status.HTTP_200_OK,
    tags=["Root"],
    summary="Root endpoint",
)
async def read_root():
    """根路径欢迎信息"""
    return RootResponse(
        message=f"Welcome to the {settings.PROJECT_NAME}", version=settings.VERSION
    )


# API路由
app.include_router(auth_router, prefix=settings.API_PREFIX)
app.include_router(users_router, prefix=settings.API_PREFIX)
app.include_router(rbac_router, prefix=settings.API_PREFIX)

# Here we will include routers from different modules
# For example:
# from .auth.router import router as auth_router
# app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
