"""Resource management API routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.database import get_async_db

from . import schemas, service
from .models import CrawlerAccount
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
    "/proxy-providers",
    response_model=schemas.ProxyProviderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建代理服务商配置",
)
async def create_proxy_provider(
    data: schemas.ProxyProviderCreate,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_resources_write),
):
    provider = await service.create_proxy_provider(db, data)
    return schemas.ProxyProviderResponse.model_validate(provider)


@router.get(
    "/proxy-providers",
    response_model=List[schemas.ProxyProviderResponse],
    summary="代理服务商列表",
)
async def list_proxy_providers(
    active: bool | None = None,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_resources_read),
):
    providers = await service.list_proxy_providers(db, active)
    return [
        schemas.ProxyProviderResponse.model_validate(provider)
        for provider in providers
    ]


@router.get(
    "/proxy-providers/{provider_id}",
    response_model=schemas.ProxyProviderResponse,
    summary="代理服务商详情",
)
async def get_proxy_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_resources_read),
):
    provider = await service.get_proxy_provider(db, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="代理服务商不存在")
    return schemas.ProxyProviderResponse.model_validate(provider)


@router.patch(
    "/proxy-providers/{provider_id}",
    response_model=schemas.ProxyProviderResponse,
    summary="更新代理服务商配置",
)
async def update_proxy_provider(
    provider_id: int,
    payload: schemas.ProxyProviderUpdate,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_resources_write),
):
    provider = await service.update_proxy_provider(db, provider_id, payload)
    if not provider:
        raise HTTPException(status_code=404, detail="代理服务商不存在")
    return schemas.ProxyProviderResponse.model_validate(provider)


@router.post(
    "/proxy-providers/{provider_id}/refresh",
    response_model=schemas.ProxyPoolStatus,
    summary="立即刷新代理池",
)
async def refresh_proxy_provider_pool(
    provider_id: int,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_resources_write),
):
    try:
        status_info = await service.refresh_proxy_pool(db, provider_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.ProxyPoolStatus.model_validate(status_info)


@router.get(
    "/proxy-providers/{provider_id}/status",
    response_model=schemas.ProxyPoolStatus,
    summary="代理池状态",
)
async def get_proxy_provider_status(
    provider_id: int,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_resources_read),
):
    status_info = await service.get_proxy_pool_status(db, provider_id)
    if not status_info:
        raise HTTPException(status_code=404, detail="代理服务商不存在")
    return schemas.ProxyPoolStatus.model_validate(status_info)
