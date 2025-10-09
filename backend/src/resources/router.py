"""Resource management API routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.database import get_async_db

from . import schemas, service
from .models import CrawlerAccount, CrawlerProxy
from .dependencies import (
    require_resources_read,
    require_resources_write,
)

router = APIRouter(prefix="/resources", tags=["Resources"])


@router.post(
    "/accounts",
    response_model=schemas.CrawlerAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建账号资源",
)
async def create_account(
    data: schemas.CrawlerAccountCreate,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_resources_write),
):
    account = await service.create_account(db, data)
    return schemas.CrawlerAccountResponse.model_validate(account)


@router.get(
    "/accounts/{account_id}",
    response_model=schemas.CrawlerAccountResponse,
    summary="账号资源详情",
)
async def get_account(
    account_id: int,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_resources_read),
):
    account = await service.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    return schemas.CrawlerAccountResponse.model_validate(account)


@router.get(
    "/accounts",
    response_model=List[schemas.CrawlerAccountResponse],
    summary="账号资源列表",
)
async def list_accounts(
    platform: str | None = None,
    active: bool | None = None,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_resources_read),
):
    platform_enum = None
    if platform:
        from src.tasks.models import PlatformType

        try:
            platform_enum = PlatformType(platform)
        except ValueError as exc:  # pragma: no cover - invalid query
            raise HTTPException(status_code=400, detail="无效的平台标识") from exc
    accounts = await service.list_accounts(db, platform_enum, active)
    return [schemas.CrawlerAccountResponse.model_validate(acc) for acc in accounts]


@router.patch(
    "/accounts/{account_id}",
    response_model=schemas.CrawlerAccountResponse,
    summary="更新账号信息",
)
async def update_account(
    account_id: int,
    payload: schemas.CrawlerAccountUpdate,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_resources_write),
):
    account = await service.update_account(db, account_id, payload)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    return schemas.CrawlerAccountResponse.model_validate(account)


@router.patch(
    "/accounts/{account_id}/status",
    response_model=schemas.CrawlerAccountResponse,
    summary="更新账号状态",
)
async def update_account_status(
    account_id: int,
    payload: schemas.CrawlerAccountUpdateStatus,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_resources_write),
):
    account = await db.get(CrawlerAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    account.is_active = payload.is_active
    await db.commit()
    await db.refresh(account)
    return schemas.CrawlerAccountResponse.model_validate(account)


@router.post(
    "/proxies",
    response_model=schemas.CrawlerProxyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建代理资源",
)
async def create_proxy(
    data: schemas.CrawlerProxyCreate,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_resources_write),
):
    proxy = await service.create_proxy(db, data)
    return schemas.CrawlerProxyResponse.model_validate(proxy)


@router.get(
    "/proxies/{proxy_id}",
    response_model=schemas.CrawlerProxyResponse,
    summary="代理资源详情",
)
async def get_proxy(
    proxy_id: int,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_resources_read),
):
    proxy = await service.get_proxy(db, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="代理不存在")
    return schemas.CrawlerProxyResponse.model_validate(proxy)


@router.get(
    "/proxies",
    response_model=List[schemas.CrawlerProxyResponse],
    summary="代理资源列表",
)
async def list_proxies(
    active: bool | None = None,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_resources_read),
):
    proxies = await service.list_proxies(db, active)
    return [schemas.CrawlerProxyResponse.model_validate(proxy) for proxy in proxies]


@router.patch(
    "/proxies/{proxy_id}",
    response_model=schemas.CrawlerProxyResponse,
    summary="更新代理信息",
)
async def update_proxy(
    proxy_id: int,
    payload: schemas.CrawlerProxyUpdate,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_resources_write),
):
    proxy = await service.update_proxy(db, proxy_id, payload)
    if not proxy:
        raise HTTPException(status_code=404, detail="代理不存在")
    return schemas.CrawlerProxyResponse.model_validate(proxy)


@router.patch(
    "/proxies/{proxy_id}/status",
    response_model=schemas.CrawlerProxyResponse,
    summary="更新代理状态",
)
async def update_proxy_status(
    proxy_id: int,
    payload: schemas.CrawlerProxyUpdateStatus,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_resources_write),
):
    proxy = await db.get(CrawlerProxy, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="代理不存在")
    proxy.is_active = payload.is_active
    await db.commit()
    await db.refresh(proxy)
    return schemas.CrawlerProxyResponse.model_validate(proxy)
