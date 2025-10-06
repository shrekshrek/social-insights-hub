"""Service layer for crawler resources."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.tasks.models import PlatformType

from . import models, schemas


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


async def allocate_account(
    db: AsyncSession, platform: PlatformType, task_id: int
) -> Optional[models.CrawlerAccount]:
    stmt = (
        select(models.CrawlerAccount)
        .where(
            models.CrawlerAccount.platform == platform,
            models.CrawlerAccount.is_active.is_(True),
            models.CrawlerAccount.locked_by_task_id.is_(None),
        )
        .order_by(
            models.CrawlerAccount.last_used_at.is_(None).desc(),
            models.CrawlerAccount.last_used_at.asc(),
        )
        .with_for_update(skip_locked=True)
    )
    result = await db.execute(stmt)
    account = result.scalars().first()
    if not account:
        return None

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
# Proxy operations
# ---------------------------------------------------------------------------


async def create_proxy(
    db: AsyncSession, data: schemas.CrawlerProxyCreate
) -> models.CrawlerProxy:
    proxy = models.CrawlerProxy(
        label=data.label,
        protocol=data.protocol,
        host=data.host,
        port=data.port,
        username=data.username,
        password=data.password,
    )
    db.add(proxy)
    await db.commit()
    await db.refresh(proxy)
    return proxy


async def list_proxies(
    db: AsyncSession,
    is_active: bool | None = None,
) -> List[models.CrawlerProxy]:
    stmt: Select[models.CrawlerProxy] = select(models.CrawlerProxy)
    if is_active is not None:
        stmt = stmt.where(models.CrawlerProxy.is_active == is_active)
    stmt = stmt.order_by(models.CrawlerProxy.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def allocate_proxy(
    db: AsyncSession, task_id: int
) -> Optional[models.CrawlerProxy]:
    stmt = (
        select(models.CrawlerProxy)
        .where(
            models.CrawlerProxy.is_active.is_(True),
            models.CrawlerProxy.locked_by_task_id.is_(None),
        )
        .order_by(
            models.CrawlerProxy.last_used_at.is_(None).desc(),
            models.CrawlerProxy.last_used_at.asc(),
        )
        .with_for_update(skip_locked=True)
    )
    result = await db.execute(stmt)
    proxy = result.scalars().first()
    if not proxy:
        return None

    now = datetime.utcnow()
    proxy.locked_by_task_id = task_id
    proxy.locked_at = now
    proxy.last_used_at = now
    await db.commit()
    await db.refresh(proxy)
    return proxy


async def release_proxy(
    db: AsyncSession, proxy_id: int, *, success: bool = True
) -> None:
    stmt = (
        update(models.CrawlerProxy)
        .where(models.CrawlerProxy.id == proxy_id)
        .values(
            locked_by_task_id=None,
            locked_at=None,
            failure_count=models.CrawlerProxy.failure_count
            if success
            else models.CrawlerProxy.failure_count + 1,
        )
    )
    await db.execute(stmt)
    await db.commit()
