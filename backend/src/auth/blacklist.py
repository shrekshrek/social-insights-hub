from datetime import timedelta

import redis.asyncio as redis
from src.auth.constants import REDIS_BLACKLIST_PREFIX


async def add_token_to_blacklist(
    redis_client: redis.Redis, token: str, expires_in: timedelta
):
    """
    Adds a token to the blacklist with an expiration time.

    Args:
        redis_client: Redis client instance
        token: JWT token to blacklist
        expires_in: Time until the token expires naturally
    """
    await redis_client.set(f"{REDIS_BLACKLIST_PREFIX}{token}", "true", ex=expires_in)


async def is_token_blacklisted(redis_client: redis.Redis, token: str) -> bool:
    """
    Checks if a token is in the blacklist.

    Args:
        redis_client: Redis client instance
        token: JWT token to check

    Returns:
        bool: True if token is blacklisted, False otherwise
    """
    return await redis_client.exists(f"{REDIS_BLACKLIST_PREFIX}{token}")
