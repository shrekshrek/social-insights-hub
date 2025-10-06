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


class CrawlerAccountUpdateStatus(CustomBaseModel):
    is_active: bool = Field(..., description="是否启用")


class CrawlerAccountResponse(CustomBaseModel):
    id: int
    platform: PlatformType
    account_name: str
    is_active: bool
    locked_by_task_id: Optional[int]
    last_used_at: Optional[datetime]
    failure_count: int
    created_at: datetime
    updated_at: datetime


class CrawlerProxyCreate(CustomBaseModel):
    label: str | None = Field(default=None, max_length=255, description="代理标识")
    protocol: str = Field(default="http", description="协议")
    host: str = Field(..., description="主机地址")
    port: int = Field(..., ge=1, le=65535, description="端口")
    username: str | None = Field(default=None, description="代理用户名")
    password: str | None = Field(default=None, description="代理密码")


class CrawlerProxyUpdateStatus(CustomBaseModel):
    is_active: bool = Field(..., description="是否启用")


class CrawlerProxyResponse(CustomBaseModel):
    id: int
    label: str | None
    protocol: str
    host: str
    port: int
    username: str | None
    is_active: bool
    locked_by_task_id: Optional[int]
    last_used_at: Optional[datetime]
    failure_count: int
    created_at: datetime
    updated_at: datetime
