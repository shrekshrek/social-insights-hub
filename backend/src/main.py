import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi import status
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession
from src.schemas import HealthResponse, RootResponse

from src.auth.router import router as auth_router
from src.users.router import router as users_router
from src.rbac.router import router as rbac_router
from src.social_media.monitors.router import router as monitors_router
from src.social_media.tasks.router import router as tasks_router
from src.social_media.analysis.router import router as analysis_router
from src.agent.router import router as agent_router
from src.strategies.router import router as strategies_router
from src.knowledge_base.router import router as knowledge_base_router
from src.news_media.router import router as news_media_router
from src.config import settings
from src.database import get_async_db, AsyncSessionLocal
from src.rbac.init_data import init_rbac_data
from src.social_media.monitors.init_data import init_platforms
from src.middleware import (
    GZipRequestMiddleware,
    RequestLoggingMiddleware,
    GlobalExceptionHandlerMiddleware,
    SecurityHeadersMiddleware,
)
from src.rate_limit import limiter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("Application starting...")

    # 启动时同步权限
    try:
        async with AsyncSessionLocal() as db:
            logger.info("Syncing RBAC permissions...")
            await init_rbac_data(db)
            logger.info("RBAC permissions synced")
    except Exception as e:
        logger.error("RBAC sync failed: %s", e, exc_info=True)
        # 生产环境失败即阻止启动；开发环境容错继续
        if (settings.ENVIRONMENT or "").lower() == "production":
            logger.critical("RBAC sync failed in production, aborting startup")
            raise
        logger.warning("RBAC sync failed, starting with existing permissions (dev mode)")

    # 初始化平台数据
    try:
        async with AsyncSessionLocal() as db:
            logger.info("Initializing platform data...")
            await init_platforms(db)
            logger.info("Platform data initialized")
    except Exception as e:
        logger.error("Platform init failed: %s", e, exc_info=True)
        logger.warning("Starting with existing platform config")

    # 启动 APScheduler（轻量定时任务）
    scheduler = None
    try:
        from src.scheduler import create_scheduler
        scheduler = create_scheduler()
        scheduler.start()
        logger.info("APScheduler started")
    except Exception as e:
        logger.error("APScheduler failed to start: %s", e, exc_info=True)

    yield  # 应用运行期间

    if scheduler is not None:
        scheduler.shutdown(wait=False)
    logger.info("Application shutdown")


app_display_name = settings.APP_NAME or settings.PROJECT_NAME

app = FastAPI(
    title=app_display_name,
    description="API for the full-stack starter project.",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 添加中间件（注意顺序很重要，后添加的先执行）
# 1. 安全头中间件
app.add_middleware(SecurityHeadersMiddleware)

# 2. 全局异常处理中间件
app.add_middleware(GlobalExceptionHandlerMiddleware)

# 3. 请求日志中间件
app.add_middleware(RequestLoggingMiddleware)

# 4. GZip 请求体解压中间件（用于爬虫客户端压缩上传）
app.add_middleware(GZipRequestMiddleware)

# 5. CORS中间件
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
    expose_headers=["Content-Disposition"],
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
        "service": app_display_name,
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
        message=f"Welcome to the {app_display_name}", version=settings.VERSION
    )


# API路由
app.include_router(auth_router, prefix=settings.API_PREFIX)
app.include_router(users_router, prefix=settings.API_PREFIX)
app.include_router(rbac_router, prefix=settings.API_PREFIX)
app.include_router(monitors_router, prefix=settings.API_PREFIX)
app.include_router(tasks_router, prefix=settings.API_PREFIX)
app.include_router(analysis_router, prefix=settings.API_PREFIX)
app.include_router(agent_router, prefix=settings.API_PREFIX)
app.include_router(strategies_router, prefix=settings.API_PREFIX)
app.include_router(knowledge_base_router, prefix=settings.API_PREFIX)
app.include_router(news_media_router, prefix=settings.API_PREFIX)
