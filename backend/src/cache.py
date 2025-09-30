"""
Simple Redis cache implementation for API endpoints
"""

from functools import wraps
from typing import Any, Callable
import json
import hashlib
import logging

from src.redis_client import get_redis_client

logger = logging.getLogger(__name__)


def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate a unique cache key based on function arguments"""
    key_data = f"{prefix}:{args}:{sorted(kwargs.items())}"
    return hashlib.md5(key_data.encode()).hexdigest()


def redis_cache(expire: int = 300, prefix: str = "cache"):
    """
    Simple Redis cache decorator for async functions

    Args:
        expire: Cache expiration time in seconds (default: 5 minutes)
        prefix: Cache key prefix for namespacing

    Usage:
        @redis_cache(expire=600, prefix="user")
        async def get_user(user_id: int):
            return await fetch_user_from_db(user_id)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Skip cache for non-GET operations or if Redis is unavailable
            try:
                # Get Redis client
                redis_client = None
                async for client in get_redis_client():
                    redis_client = client
                    break

                if not redis_client:
                    logger.warning(
                        f"Redis not available, skipping cache for {func.__name__}"
                    )
                    return await func(*args, **kwargs)

                # Generate cache key
                cache_key = (
                    f"{prefix}:{generate_cache_key(func.__name__, *args, **kwargs)}"
                )

                # Try to get from cache
                cached_value = await redis_client.get(cache_key)
                if cached_value:
                    logger.debug(f"Cache hit for key: {cache_key}")
                    return json.loads(cached_value)

                # Execute function and cache result
                result = await func(*args, **kwargs)

                # Only cache successful results
                if result is not None:
                    await redis_client.setex(
                        cache_key, expire, json.dumps(result, default=str)
                    )
                    logger.debug(f"Cached result for key: {cache_key}")

                return result

            except Exception as e:
                logger.error(f"Cache error in {func.__name__}: {str(e)}")
                # Fall back to executing function without cache
                return await func(*args, **kwargs)

        return wrapper

    return decorator


async def invalidate_cache(pattern: str) -> int:
    """
    Invalidate cache entries matching a pattern

    Args:
        pattern: Redis key pattern (e.g., "user:*")

    Returns:
        Number of keys deleted
    """
    try:
        redis_client = None
        async for client in get_redis_client():
            redis_client = client
            break

        if not redis_client:
            logger.warning("Redis not available for cache invalidation")
            return 0

        # Find all keys matching the pattern
        keys = []
        async for key in redis_client.scan_iter(match=f"cache:{pattern}"):
            keys.append(key)

        # Delete all matching keys
        if keys:
            deleted = await redis_client.delete(*keys)
            logger.info(f"Invalidated {deleted} cache keys matching pattern: {pattern}")
            return deleted

        return 0

    except Exception as e:
        logger.error(f"Cache invalidation error: {str(e)}")
        return 0
