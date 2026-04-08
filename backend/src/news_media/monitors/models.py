"""新闻监测项目数据模型"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.database import Base

if TYPE_CHECKING:
    from src.auth.models import User
    from src.news_media.tasks.models import NewsTask


# 新闻监测-参与者关联表（多对多）
news_monitor_participants = Table(
    "news_monitor_participants",
    Base.metadata,
    Column(
        "monitor_id",
        Integer,
        ForeignKey("news_monitors.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "user_id",
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class NewsMonitor(Base):
    """新闻监测项目"""

    __tablename__ = "news_monitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True, comment="监测项目名称"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="项目描述")
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True, comment="创建者用户ID"
    )
    aggregated_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="跨任务叙事聚合分析结果（按需生成）"
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
    participants: Mapped[list["User"]] = relationship(
        "src.auth.models.User", secondary=news_monitor_participants, lazy="selectin"
    )
    tasks: Mapped[list["NewsTask"]] = relationship(
        "src.news_media.tasks.models.NewsTask",
        back_populates="monitor",
        cascade="all, delete-orphan",
        lazy="select",
    )
