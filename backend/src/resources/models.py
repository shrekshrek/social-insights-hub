"""Resource models for crawler accounts and proxies."""

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
        SQLEnum(PlatformType, name="platformtype", create_type=False),
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


class CrawlerProxy(Base):
    """Proxy resource for crawler execution."""

    __tablename__ = "crawler_proxies"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(255), nullable=True, comment="代理标识")
    protocol = Column(String(32), nullable=False, default="http", comment="协议")
    host = Column(String(255), nullable=False, comment="主机地址")
    port = Column(Integer, nullable=False, comment="端口")
    username = Column(String(255), nullable=True, comment="认证用户名")
    password = Column(String(255), nullable=True, comment="认证密码")
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

    @property
    def display_host(self) -> str:  # pragma: no cover - simple helper
        return f"{self.protocol}://{self.host}:{self.port}"
