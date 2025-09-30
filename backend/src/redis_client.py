import redis.asyncio as redis
from src.config import settings

redis_pool = redis.ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True)


async def get_redis_client() -> redis.Redis:
    """
    Dependency that provides an asynchronous Redis client from a connection pool.
    """
    async with redis.Redis(connection_pool=redis_pool) as client:
        yield client
