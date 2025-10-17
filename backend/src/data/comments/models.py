"""Comment data models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, Integer, BigInteger, DateTime, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.tasks.models import CrawlerTask


class Comment(Base):
    """评论数据模型（独立存储，不直接关联任务）."""

    __tablename__ = "comments"

    # 主键
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 平台信息
    platform: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, comment="平台类型"
    )
    comment_id: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True, comment="平台评论ID"
    )

    # 评论内容
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="评论内容")

    # 评论来源
    note_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="所属笔记ID"
    )
    note_title: Mapped[str | None] = mapped_column(String(500), comment="笔记标题")

    # 评论层级
    parent_comment_id: Mapped[str | None] = mapped_column(
        String(100), index=True, comment="父评论ID(一级评论为空)"
    )
    sub_comment_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="子评论数量"
    )

    # 作者信息
    author_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="评论者ID"
    )
    author_name: Mapped[str | None] = mapped_column(String(200), comment="评论者昵称")
    author_avatar: Mapped[str | None] = mapped_column(
        String(500), comment="评论者头像URL"
    )

    # 统计数据
    liked_count: Mapped[int] = mapped_column(Integer, default=0, comment="点赞数")
    reply_count: Mapped[int] = mapped_column(Integer, default=0, comment="回复数")

    # 评论元数据
    ip_location: Mapped[str | None] = mapped_column(String(100), comment="IP属地")

    # 平台发布时间
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime, comment="评论发布时间"
    )

    # 数据管理
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="首次爬取时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="数据更新时间"
    )

    # 关联关系
    task_associations: Mapped[list[TaskComment]] = relationship(
        "TaskComment", back_populates="comment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_comments_platform_comment_id", "platform", "comment_id"),
        Index("idx_comments_note_id", "note_id"),
        Index("idx_comments_author_id", "author_id"),
        Index("idx_comments_parent_comment_id", "parent_comment_id"),
        Index("idx_comments_published_at", "published_at"),
        Index("idx_comments_crawled_at", "crawled_at"),
    )


class TaskComment(Base):
    """任务与评论的多对多关联表."""

    __tablename__ = "task_comments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 关联字段
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crawler_tasks.id", ondelete="CASCADE"), nullable=False
    )
    comment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("comments.id", ondelete="CASCADE"), nullable=False
    )

    # 爬取元数据
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="该任务爬取此评论的时间"
    )
    keyword: Mapped[str | None] = mapped_column(
        String(200), comment="爬取时使用的关键词"
    )

    # 关联关系
    task: Mapped[CrawlerTask] = relationship(
        "CrawlerTask", back_populates="comment_associations"
    )
    comment: Mapped[Comment] = relationship(
        "Comment", back_populates="task_associations"
    )

    __table_args__ = (
        Index("idx_task_comments_task_comment", "task_id", "comment_id", unique=True),
        Index("idx_task_comments_task_id", "task_id"),
        Index("idx_task_comments_comment_id", "comment_id"),
    )
