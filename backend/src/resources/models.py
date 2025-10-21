"""Resource models for crawler accounts and proxy providers."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    Integer,
    String,
    Text,
)

from src.database import Base
from src.tasks.models import PlatformType


class CrawlerAccount(Base):
    """Crawler account resource."""

    __tablename__ = "crawler_accounts"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(
        SQLEnum(
            PlatformType,
            name="platformtype",
            create_type=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            validate_strings=True,
        ),
        nullable=False,
        index=True,
        comment="所属平台",
    )
    account_name = Column(String(255), nullable=False, comment="账号标识")
    cookies = Column(Text, nullable=False, comment="登录Cookies")
    is_active = Column(Boolean, nullable=False, default=True, comment="是否可用")
    locked_by_task_id = Column(Integer, nullable=True, comment="当前占用的任务ID")
    locked_at = Column(DateTime, nullable=True, comment="锁定时间")
    last_used_at = Column(DateTime, nullable=True, comment="最近使用时间")
    failure_count = Column(Integer, nullable=False, default=0, comment="连续失败次数")
    created_at = Column(
        DateTime, default=datetime.utcnow, nullable=False, comment="创建时间"
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="更新时间",
    )


class CrawlerProxyProvider(Base):
    """Fast-proxy provider configuration."""

    __tablename__ = "crawler_proxy_providers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, comment="配置名称", index=True)
    provider_type = Column(
        String(64), nullable=False, default="kuaidaili", comment="代理商类型"
    )
    secret_id = Column(String(255), nullable=False, comment="快代理 secret_id")
    signature = Column(String(255), nullable=False, comment="快代理 signature")
    username = Column(String(255), nullable=False, comment="代理用户名")
    password = Column(String(255), nullable=False, comment="代理密码")
    pool_size = Column(Integer, nullable=False, default=10, comment="期望池容量")
    validate_enabled = Column(
        Boolean, nullable=False, default=True, comment="启用有效性校验"
    )
    sync_interval_minutes = Column(
        Integer, nullable=False, default=5, comment="同步间隔(分钟)"
    )
    is_active = Column(
        Boolean, nullable=False, default=True, comment="是否启用", index=True
    )
    last_synced_at = Column(DateTime, nullable=True, comment="最近同步时间")
    created_at = Column(
        DateTime, default=datetime.utcnow, nullable=False, comment="创建时间"
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="更新时间",
    )
