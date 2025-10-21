"""Note data models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, Integer, BigInteger, DateTime, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.tasks.models import CrawlerTask


class Note(Base):
    """笔记数据模型（独立存储，不直接关联任务）."""

    __tablename__ = "notes"

    # 主键
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 平台信息
    platform: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, comment="平台类型"
    )
    note_id: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True, comment="平台笔记ID"
    )

    # 笔记基本信息
    title: Mapped[str] = mapped_column(String(500), nullable=False, comment="笔记标题")
    content: Mapped[str | None] = mapped_column(Text, comment="笔记内容")
    note_type: Mapped[str | None] = mapped_column(
        String(50), comment="笔记类型(video/image/note)"
    )

    # 作者信息
    author_id: Mapped[str | None] = mapped_column(
        String(100), index=True, comment="作者ID"
    )
    author_name: Mapped[str | None] = mapped_column(String(200), comment="作者昵称")

    # 统计数据
    liked_count: Mapped[int] = mapped_column(Integer, default=0, comment="点赞数")
    collected_count: Mapped[int] = mapped_column(Integer, default=0, comment="收藏数")
    comment_count: Mapped[int] = mapped_column(Integer, default=0, comment="评论数")
    shared_count: Mapped[int] = mapped_column(Integer, default=0, comment="分享数")
    view_count: Mapped[int] = mapped_column(Integer, default=0, comment="浏览数")

    # 媒体信息
    images: Mapped[str | None] = mapped_column(Text, comment="图片URL列表(JSON)")
    video_url: Mapped[str | None] = mapped_column(String(500), comment="视频URL")

    # 笔记元数据
    note_url: Mapped[str | None] = mapped_column(String(500), comment="笔记链接")
    ip_location: Mapped[str | None] = mapped_column(String(100), comment="IP属地")
    tags: Mapped[str | None] = mapped_column(Text, comment="标签列表(JSON)")

    # 平台发布时间
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime, comment="笔记发布时间"
    )

    # 数据管理
    last_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime, comment="笔记最后修改时间"
    )
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="首次爬取时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="数据更新时间"
    )

    # 关联关系
    task_associations: Mapped[list[TaskNote]] = relationship(
        "TaskNote", back_populates="note", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_platform_note_id", "platform", "note_id"),
        Index("idx_author_id", "author_id"),
        Index("idx_published_at", "published_at"),
        Index("idx_crawled_at", "crawled_at"),
    )


class TaskNote(Base):
    """任务与笔记的多对多关联表."""

    __tablename__ = "task_notes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 关联字段
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crawler_tasks.id", ondelete="CASCADE"), nullable=False
    )
    note_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
    )

    # 爬取元数据
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="该任务爬取此笔记的时间"
    )
    keyword: Mapped[str | None] = mapped_column(
        String(200), comment="爬取时使用的关键词"
    )

    # 关联关系
    task: Mapped[CrawlerTask] = relationship(
        "CrawlerTask", back_populates="note_associations"
    )
    note: Mapped[Note] = relationship("Note", back_populates="task_associations")

    __table_args__ = (
        Index("idx_task_note", "task_id", "note_id", unique=True),
        Index("idx_task_id", "task_id"),
        Index("idx_note_id", "note_id"),
    )
