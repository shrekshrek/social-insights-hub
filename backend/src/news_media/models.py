"""新闻媒体数据模型"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.database import Base

if TYPE_CHECKING:
    from src.auth.models import User
    from src.strategies.models import Strategy


class NewsMonitor(Base):
    """新闻监测项目"""

    __tablename__ = "news_monitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="监测项目名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="项目描述")
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True, comment="创建者用户ID"
    )
    search_provider: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="serpapi_baidu", comment="搜索提供商"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship(
        "src.auth.models.User", foreign_keys=[owner_id], lazy="selectin"
    )
    tasks: Mapped[list["NewsTask"]] = relationship(
        back_populates="monitor", cascade="all, delete-orphan", lazy="select"
    )


class NewsTask(Base):
    """新闻采集任务"""

    __tablename__ = "news_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="任务名称")
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("news_monitors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属监测项目ID",
    )
    strategy_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="所属策略ID（策略流程专用）",
    )
    keywords: Mapped[str] = mapped_column(Text, nullable=False, comment="搜索关键词")
    phase: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True, comment="采集阶段: probe / collect"
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="pending",
        index=True,
        comment="任务状态: pending / running / completed / failed",
    )
    search_provider: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="serpapi_baidu", comment="搜索提供商"
    )
    search_params: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="搜索参数（时间范围、地区、最大结果数等）"
    )
    articles_count: Mapped[int] = mapped_column(
        Integer, server_default="0", comment="采集到的文章数量"
    )
    analysis_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="分析结果（结构化洞察）"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True, comment="创建者用户ID"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    monitor: Mapped["NewsMonitor"] = relationship(
        back_populates="tasks", lazy="selectin"
    )
    creator: Mapped["User"] = relationship(
        "src.auth.models.User", foreign_keys=[created_by], lazy="selectin"
    )
    strategy: Mapped["Strategy | None"] = relationship(
        "Strategy", foreign_keys=[strategy_id], lazy="select", back_populates="news_tasks"
    )
