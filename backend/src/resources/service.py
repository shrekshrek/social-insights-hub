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


async def get_proxy(
    db: AsyncSession, proxy_id: int
) -> models.CrawlerProxy | None:
    return await db.get(models.CrawlerProxy, proxy_id)


async def update_proxy(
    db: AsyncSession, proxy_id: int, data: schemas.CrawlerProxyUpdate
) -> models.CrawlerProxy | None:
    proxy = await get_proxy(db, proxy_id)
    if not proxy:
        return None

    update_dict = data.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in update_dict.items():
        setattr(proxy, field, value)
    proxy.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(proxy)
    return proxy


async def allocate_proxy(
    db: AsyncSession, task_id: int
) -> Optional[models.CrawlerProxy]:
    async def _select_proxy(active_only: bool) -> models.CrawlerProxy | None:
        filters = [models.CrawlerProxy.locked_by_task_id.is_(None)]
        if active_only:
            filters.append(models.CrawlerProxy.is_active.is_(True))

        stmt = (
            select(models.CrawlerProxy)
            .where(*filters)
            .order_by(
                models.CrawlerProxy.last_used_at.is_(None).desc(),
                models.CrawlerProxy.last_used_at.asc(),
            )
            .with_for_update(skip_locked=True)
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    proxy = await _select_proxy(active_only=True)
    if not proxy:
        proxy = await _select_proxy(active_only=False)
        if not proxy:
            return None
        if proxy.is_active is False:
            proxy.is_active = True

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
