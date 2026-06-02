import redis.asyncio as redis
from src.config import settings

# max_connections 给连接池设上限：默认上限极大（~2^31），高并发下会无界增长占满文件描述符（Errno 24）。
# backend 为单 uvicorn worker + asyncio，100 已足够支撑并发请求的 Redis 操作。
redis_pool = redis.ConnectionPool.from_url(
    settings.REDIS_URL, decode_responses=True, max_connections=100
)


async def get_redis_client() -> redis.Redis:
    """
    Dependency that provides an asynchronous Redis client from a connection pool.
    """
    async with redis.Redis(connection_pool=redis_pool) as client:
        yield client
