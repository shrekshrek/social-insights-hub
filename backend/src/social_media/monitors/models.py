"""社交媒体数据模型"""

from typing import TYPE_CHECKING
from datetime import datetime
from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    Table,
    Column,
    Integer,
    JSON,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.auth.models import User


# 项目-参与者关联表（多对多）
monitor_participants = Table(
    "monitor_participants",
    Base.metadata,
    Column(
        "monitor_id",
        Integer,
        ForeignKey("monitors.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    ),
)


class Platform(Base):
    """社交媒体平台模型

    存储可用的社交媒体平台信息（小红书、抖音等7个平台）
    """

    __tablename__ = "platforms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    code: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False
    )  # 平台代码：xhs, dy等
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return f"<Platform(id={self.id}, name='{self.name}', code='{self.code}')>"


class Monitor(Base):
    """社交舆情项目模型

    项目是数据管理的基本单位，每个项目可以关联多个平台，
    包含多个数据获取任务和分析结果。
    """

    __tablename__ = "monitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    # 项目元数据
    start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # AI分析配置（JSON格式）
    deep_analysis_settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    owner: Mapped["User"] = relationship(
        "src.auth.models.User", foreign_keys=[owner_id], lazy="selectin"
    )

    participants: Mapped[list["User"]] = relationship(
        "src.auth.models.User", secondary=monitor_participants, lazy="selectin"
    )

    # TODO: 添加以下关系（在后续阶段实现）
    # data_tasks: Mapped[list["DataTask"]] = relationship(back_populates="monitor")

    def __repr__(self):
        return f"<Monitor(id={self.id}, name='{self.name}', owner_id={self.owner_id})>"
