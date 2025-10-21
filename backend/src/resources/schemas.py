"""Pydantic schemas for crawler resources."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field

from src.schemas import CustomBaseModel
from src.tasks.models import PlatformType


class CrawlerAccountCreate(CustomBaseModel):
    platform: PlatformType = Field(..., description="平台类型")
    account_name: str = Field(..., max_length=255, description="账号标识")
    cookies: str = Field(..., description="登录Cookies")


class CrawlerAccountUpdate(CustomBaseModel):
    account_name: str | None = Field(
        default=None, max_length=255, description="账号标识"
    )
    cookies: str | None = Field(default=None, description="登录Cookies")
    is_active: bool | None = Field(default=None, description="是否启用")


class CrawlerAccountUpdateStatus(CustomBaseModel):
    is_active: bool = Field(..., description="是否启用")


class CrawlerAccountResponse(CustomBaseModel):
    id: int
    platform: PlatformType
    account_name: str
    cookies: Optional[str] = Field(
        default=None, description="登录Cookies（编辑时需要）"
    )
    is_active: bool
    locked_by_task_id: Optional[int]
    last_used_at: Optional[datetime]
    failure_count: int
    created_at: datetime
    updated_at: datetime


class ProxyProviderCreate(CustomBaseModel):
    name: str = Field(..., max_length=255, description="配置名称")
    provider_type: str = Field(
        default="kuaidaili", description="代理商类型，当前仅支持快代理"
    )
    secret_id: str = Field(..., max_length=255, description="快代理 secret_id")
    signature: str = Field(..., max_length=255, description="快代理 signature")
    username: str = Field(..., max_length=255, description="代理用户名")
    password: str = Field(..., max_length=255, description="代理密码")
    pool_size: int = Field(default=10, ge=1, le=200, description="期望的代理池容量")
    validate_enabled: bool = Field(default=True, description="是否启用代理可用性校验")
    sync_interval_minutes: int = Field(
        default=5, ge=1, le=120, description="同步间隔（分钟）"
    )
    is_active: bool = Field(default=True, description="是否启用该配置")


class ProxyProviderUpdate(CustomBaseModel):
    name: str | None = Field(default=None, max_length=255, description="配置名称")
    provider_type: str | None = Field(
        default=None, description="代理商类型，当前仅支持快代理"
    )
    secret_id: str | None = Field(
        default=None, max_length=255, description="快代理 secret_id"
    )
    signature: str | None = Field(
        default=None, max_length=255, description="快代理 signature"
    )
    username: str | None = Field(default=None, max_length=255, description="代理用户名")
    password: str | None = Field(default=None, max_length=255, description="代理密码")
    pool_size: int | None = Field(
        default=None, ge=1, le=200, description="期望的代理池容量"
    )
    validate_enabled: bool | None = Field(
        default=None, description="是否启用代理可用性校验"
    )
    sync_interval_minutes: int | None = Field(
        default=None, ge=1, le=120, description="同步间隔（分钟）"
    )
    is_active: bool | None = Field(default=None, description="是否启用该配置")


class ProxyProviderResponse(CustomBaseModel):
    id: int
    name: str
    provider_type: str
    secret_id: str
    signature: str
    username: str
    password: str
    pool_size: int
    validate_enabled: bool
    sync_interval_minutes: int
    is_active: bool
    last_synced_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ProxyPoolStatus(CustomBaseModel):
    provider_id: int
    available: int = Field(..., ge=0, description="当前可用代理数量")
    last_synced_at: Optional[datetime]
    checked_at: datetime
