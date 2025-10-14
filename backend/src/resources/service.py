"""Service layer for crawler resources."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import httpx
import redis.asyncio as redis
from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.redis_client import get_redis_client
from src.tasks.models import PlatformType

from . import models, schemas


logger = logging.getLogger(__name__)

PROXY_CACHE_PREFIX = "proxy_pool"
KDL_API_URL = "https://dps.kdlapi.com/api/getdps/"
PROXY_TTL_DELTA = 5


@dataclass
class ProxyEndpoint:
    """Runtime proxy information allocated to crawler tasks."""

    host: str
    port: int
    protocol: str = "http"
    username: str | None = None
    password: str | None = None
    expires_in: int | None = None

    @property
    def display_host(self) -> str:
        auth = f"{self.username}@" if self.username else ""
        return f"{self.protocol}://{auth}{self.host}:{self.port}"


async def _acquire_redis_client() -> redis.Redis | None:
    """
    Attempt to obtain a Redis client from the shared pool.
    Returns None silently if Redis is unavailable so the caller can fallback.
    """
    try:
        async for client in get_redis_client():
            return client
    except Exception as exc:  # pragma: no cover - redis failure
        logger.warning("Unable to acquire redis client: %s", exc)
    return None


async def _cache_proxy(
    redis_client: redis.Redis, provider_id: int, proxy: ProxyEndpoint
) -> None:
    key = f"{PROXY_CACHE_PREFIX}:{provider_id}:{proxy.host}:{proxy.port}"
    ttl = proxy.expires_in or 60
    if ttl <= 0:
        ttl = 60
    payload = json.dumps(
        {
            "host": proxy.host,
            "port": proxy.port,
            "protocol": proxy.protocol,
            "username": proxy.username,
            "password": proxy.password,
        }
    )
    await redis_client.setex(key, ttl, payload)


async def _pop_cached_proxy(
    redis_client: redis.Redis, provider_id: int
) -> ProxyEndpoint | None:
    pattern = f"{PROXY_CACHE_PREFIX}:{provider_id}:*"
    async for key in redis_client.scan_iter(match=pattern):
        value = await redis_client.get(key)
        if not value:
            await redis_client.delete(key)
            continue
        await redis_client.delete(key)
        data = json.loads(value)
        return ProxyEndpoint(
            host=data["host"],
            port=int(data["port"]),
            protocol=data.get("protocol", "http"),
            username=data.get("username"),
            password=data.get("password"),
        )
    return None


async def _count_cached_proxies(
    redis_client: redis.Redis, provider_id: int
) -> int:
    pattern = f"{PROXY_CACHE_PREFIX}:{provider_id}:*"
    count = 0
    async for _ in redis_client.scan_iter(match=pattern):
        count += 1
    return count


async def _fetch_proxies_from_kdl(
    provider: models.CrawlerProxyProvider, count: int
) -> List[ProxyEndpoint]:
    params = {
        "secret_id": provider.secret_id,
        "signature": provider.signature,
        "num": count,
        "pt": 1,
        "format": "json",
        "sep": 1,
        "f_et": 1,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(KDL_API_URL, params=params)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(payload.get("msg", "failed to fetch proxies"))

    proxy_list = payload.get("data", {}).get("proxy_list", [])
    proxies: List[ProxyEndpoint] = []
    for raw in proxy_list:
        try:
            ip_port, expire_str = raw.split(",", 1)
            host, port_str = ip_port.split(":")
            expires_in = max(int(expire_str) - PROXY_TTL_DELTA, PROXY_TTL_DELTA)
        except (ValueError, AttributeError) as exc:  # pragma: no cover - malformed data
            logger.warning("无法解析快代理返回值 %s: %s", raw, exc)
            continue
        proxies.append(
            ProxyEndpoint(
                host=host,
                port=int(port_str),
                protocol="http",
                username=provider.username,
                password=provider.password,
                expires_in=expires_in,
            )
        )
    return proxies


async def _populate_provider_cache(
    db: AsyncSession,
    provider: models.CrawlerProxyProvider,
    redis_client: redis.Redis | None,
    requested: int,
) -> List[ProxyEndpoint]:
    fetch_count = max(requested, provider.pool_size or requested, 1)
    proxies = await _fetch_proxies_from_kdl(provider, fetch_count)
    if redis_client:
        for proxy in proxies:
            await _cache_proxy(redis_client, provider.id, proxy)
    provider.last_synced_at = datetime.utcnow()
    await db.commit()
    await db.refresh(provider)
    return proxies


# ---------------------------------------------------------------------------
# Account operations
# ---------------------------------------------------------------------------


async def create_account(
    db: AsyncSession, data: schemas.CrawlerAccountCreate
) -> models.CrawlerAccount:
    account = models.CrawlerAccount(
        platform=data.platform,
        account_name=data.account_name,
        cookies=data.cookies,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


async def list_accounts(
    db: AsyncSession,
    platform: PlatformType | None = None,
    is_active: bool | None = None,
) -> List[models.CrawlerAccount]:
    stmt: Select[models.CrawlerAccount] = select(models.CrawlerAccount)
    if platform is not None:
        stmt = stmt.where(models.CrawlerAccount.platform == platform)
    if is_active is not None:
        stmt = stmt.where(models.CrawlerAccount.is_active == is_active)
    stmt = stmt.order_by(models.CrawlerAccount.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_account(
    db: AsyncSession, account_id: int
) -> models.CrawlerAccount | None:
    return await db.get(models.CrawlerAccount, account_id)


async def update_account(
    db: AsyncSession, account_id: int, data: schemas.CrawlerAccountUpdate
) -> models.CrawlerAccount | None:
    account = await get_account(db, account_id)
    if not account:
        return None

    update_dict = data.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in update_dict.items():
        setattr(account, field, value)
    account.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(account)
    return account


async def allocate_account(
    db: AsyncSession, platform: PlatformType, task_id: int
) -> Optional[models.CrawlerAccount]:
    async def _select_account(active_only: bool) -> models.CrawlerAccount | None:
        filters = [
            models.CrawlerAccount.platform == platform,
            models.CrawlerAccount.locked_by_task_id.is_(None),
        ]
        if active_only:
            filters.append(models.CrawlerAccount.is_active.is_(True))

        stmt = (
            select(models.CrawlerAccount)
            .where(*filters)
            .order_by(
                models.CrawlerAccount.last_used_at.is_(None).desc(),
                models.CrawlerAccount.last_used_at.asc(),
            )
            .with_for_update(skip_locked=True)
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    account = await _select_account(active_only=True)
    if not account:
        account = await _select_account(active_only=False)
        if not account:
            return None
        if account.is_active is False:
            account.is_active = True

    account.locked_by_task_id = task_id
    now = datetime.utcnow()
    account.locked_at = now
    account.last_used_at = now
    await db.commit()
    await db.refresh(account)
    return account


async def release_account(
    db: AsyncSession, account_id: int, *, success: bool = True
) -> None:
    stmt = (
        update(models.CrawlerAccount)
        .where(models.CrawlerAccount.id == account_id)
        .values(
            locked_by_task_id=None,
            locked_at=None,
            failure_count=models.CrawlerAccount.failure_count
            if success
            else models.CrawlerAccount.failure_count + 1,
        )
    )
    await db.execute(stmt)
    await db.commit()


# ---------------------------------------------------------------------------
# Proxy provider operations
# ---------------------------------------------------------------------------


async def create_proxy_provider(
    db: AsyncSession, data: schemas.ProxyProviderCreate
) -> models.CrawlerProxyProvider:
    provider = models.CrawlerProxyProvider(
        name=data.name,
        provider_type=data.provider_type or "kuaidaili",
        secret_id=data.secret_id,
        signature=data.signature,
        username=data.username,
        password=data.password,
        pool_size=data.pool_size,
        validate_enabled=data.validate_enabled,
        sync_interval_minutes=data.sync_interval_minutes,
        is_active=data.is_active,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return provider


async def list_proxy_providers(
    db: AsyncSession, is_active: bool | None = None
) -> List[models.CrawlerProxyProvider]:
    stmt: Select[models.CrawlerProxyProvider] = select(models.CrawlerProxyProvider)
    if is_active is not None:
        stmt = stmt.where(models.CrawlerProxyProvider.is_active == is_active)
    stmt = stmt.order_by(models.CrawlerProxyProvider.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_proxy_provider(
    db: AsyncSession, provider_id: int
) -> models.CrawlerProxyProvider | None:
    return await db.get(models.CrawlerProxyProvider, provider_id)


async def update_proxy_provider(
    db: AsyncSession, provider_id: int, data: schemas.ProxyProviderUpdate
) -> models.CrawlerProxyProvider | None:
    provider = await get_proxy_provider(db, provider_id)
    if not provider:
        return None

    update_dict = data.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in update_dict.items():
        setattr(provider, field, value)
    provider.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(provider)
    return provider


async def refresh_proxy_pool(
    db: AsyncSession, provider_id: int
) -> schemas.ProxyPoolStatus:
    provider = await get_proxy_provider(db, provider_id)
    if not provider:
        raise ValueError("代理服务商不存在")
    if not provider.is_active:
        raise ValueError("代理服务商未启用")

    redis_client = await _acquire_redis_client()
    proxies = await _populate_provider_cache(db, provider, redis_client, provider.pool_size)
    available = len(proxies)
    if redis_client:
        available = await _count_cached_proxies(redis_client, provider.id)

    return schemas.ProxyPoolStatus(
        provider_id=provider.id,
        available=available,
        last_synced_at=provider.last_synced_at,
        checked_at=datetime.utcnow(),
    )


async def get_proxy_pool_status(
    db: AsyncSession, provider_id: int
) -> schemas.ProxyPoolStatus | None:
    provider = await get_proxy_provider(db, provider_id)
    if not provider:
        return None
    redis_client = await _acquire_redis_client()
    available = 0
    if redis_client:
        available = await _count_cached_proxies(redis_client, provider.id)
    return schemas.ProxyPoolStatus(
        provider_id=provider.id,
        available=available,
        last_synced_at=provider.last_synced_at,
        checked_at=datetime.utcnow(),
    )


async def allocate_proxy_endpoint(
    db: AsyncSession, provider_id: int | None = None
) -> ProxyEndpoint | None:
    if provider_id is not None:
        provider = await get_proxy_provider(db, provider_id)
    else:
        stmt = (
            select(models.CrawlerProxyProvider)
            .where(models.CrawlerProxyProvider.is_active.is_(True))
            .order_by(models.CrawlerProxyProvider.created_at.asc())
            .limit(1)
        )
        result = await db.execute(stmt)
        provider = result.scalars().first()

    if not provider or not provider.is_active:
        return None

    redis_client = await _acquire_redis_client()
    if redis_client:
        cached = await _pop_cached_proxy(redis_client, provider.id)
        if cached:
            return cached

    proxies = await _populate_provider_cache(
        db, provider, redis_client, max(provider.pool_size, 1)
    )
    if redis_client:
        cached = await _pop_cached_proxy(redis_client, provider.id)
        if cached:
            return cached
    return proxies[0] if proxies else None


async def release_proxy_endpoint(
    db: AsyncSession, proxy: ProxyEndpoint | None, success: bool = True
) -> None:  # pragma: no cover - kept for API compatibility
    # Dynamic代理无需释放，函数保留兼容调用方
    _ = (db, proxy, success)
    return None
