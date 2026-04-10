"""社交媒体数据任务模型"""

from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Text, DateTime, Boolean, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.database import Base

if TYPE_CHECKING:
    from src.social_media.monitors.models import SocialMonitor, Platform
    from src.auth.models import User
    from src.strategies.models import Strategy


class SocialTask(Base):
    """数据获取任务模型

    每个任务代表一次数据采集操作，可以通过远程爬虫或本地上传获取数据。
    任务采用快照模式，每次执行创建新任务，数据独立存储。
    """

    __tablename__ = "social_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 任务基本信息
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 关联关系
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("social_monitors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform_id: Mapped[int] = mapped_column(
        ForeignKey("platforms.id"), nullable=False, index=True
    )
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    # 任务配置
    task_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="任务类型: search/detail/creator/homefeed",
    )
    keywords: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="搜索关键词（仅search类型）"
    )
    task_params: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="任务参数（JSON格式）"
    )

    # 数据源
    data_source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="数据源: remote_crawler/local_upload",
    )

    # 策略关联（可选，通过 FK 反查）
    strategy_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="所属策略 ID（策略流程专用，普通任务为 NULL）",
    )

    # 采集阶段（策略流程专用）
    phase: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment="采集阶段: probe（探测）/ collect（全量）",
    )

    # 任务状态
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
        comment="任务状态: pending/accepted/running/probe_ready/approved/completed/failed",
    )

    # 爬虫任务优先级和进度
    priority: Mapped[int] = mapped_column(
        Integer, default=0, comment="任务优先级（越大越优先）"
    )
    crawled_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="已爬取数量（进度）"
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="爬虫接收时间"
    )
    accepted_by: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="执行客户端标识"
    )

    # 统计信息
    posts_count: Mapped[int] = mapped_column(Integer, default=0, comment="原文数量")
    comments_count: Mapped[int] = mapped_column(Integer, default=0, comment="评论数量")

    # 执行信息
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 自动分析配置
    auto_analyze: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="数据上传完成后自动执行全流程分析"
    )

    # AI分析聚合结果
    analysis_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="任务级AI分析聚合结果（NSR、SERP、实体、IPA等）"
    )
    analysis_result_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="聚合分析生成时间"
    )

    # 软删除
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    monitor: Mapped["SocialMonitor"] = relationship(
        "src.social_media.monitors.models.SocialMonitor",
        foreign_keys=[monitor_id],
        back_populates="social_tasks",
        lazy="selectin",
    )
    platform: Mapped["Platform"] = relationship(
        "src.social_media.monitors.models.Platform",
        foreign_keys=[platform_id],
        lazy="selectin",
    )
    creator: Mapped["User"] = relationship(
        "src.auth.models.User", foreign_keys=[creator_id], lazy="selectin"
    )
    strategy: Mapped["Strategy | None"] = relationship(
        "Strategy",
        foreign_keys=[strategy_id],
        lazy="select",
        back_populates="social_tasks",
    )

    posts: Mapped[list["SocialPost"]] = relationship(
        "SocialPost",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    comments: Mapped[list["SocialComment"]] = relationship(
        "SocialComment",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self):
        return f"<SocialTask(id={self.id}, name='{self.name}', type='{self.task_type}', status='{self.status}')>"


class SocialPost(Base):
    """社交媒体原文数据模型

    存储从各平台采集的原文数据，每条记录强关联到task_id。
    通过post_id_on_platform字段支持跨任务查询同一原文。
    """

    __tablename__ = "social_posts"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 任务关联（强关联）
    task_id: Mapped[int] = mapped_column(
        ForeignKey("social_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform_id: Mapped[int] = mapped_column(
        ForeignKey("platforms.id"), nullable=False, index=True
    )

    # 平台数据
    post_id_on_platform: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="平台上的原文ID"
    )
    post_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="原文类型"
    )

    # 内容数据
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="作者ID"
    )
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 互动数据
    likes_count: Mapped[int] = mapped_column(Integer, default=0, comment="点赞数")
    comments_count: Mapped[int] = mapped_column(Integer, default=0, comment="评论数")
    shares_count: Mapped[int] = mapped_column(Integer, default=0, comment="分享/转发数")
    collected_count: Mapped[int] = mapped_column(Integer, default=0, comment="收藏数")
    views_count: Mapped[int] = mapped_column(Integer, default=0, comment="播放/浏览数")
    danmaku_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="弹幕数(B站特有)"
    )

    # 媒体资源
    images: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="图片URL列表"
    )
    videos: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="视频URL列表"
    )

    # 发布信息
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    url: Mapped[str | None] = mapped_column(Text, nullable=True, comment="原文URL")

    # 原始数据
    raw_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="平台返回的原始JSON"
    )

    # 采集信息
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="数据采集时间"
    )

    # 软删除
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    task: Mapped["SocialTask"] = relationship(
        "SocialTask", back_populates="posts", lazy="selectin"
    )
    platform: Mapped["Platform"] = relationship(
        "src.social_media.monitors.models.Platform",
        foreign_keys=[platform_id],
        lazy="selectin",
    )
    comments: Mapped[list["SocialComment"]] = relationship(
        "SocialComment",
        back_populates="post",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # 索引：支持跨任务查询同一原文
    __table_args__ = (
        Index("ix_post_platform_postid", "platform_id", "post_id_on_platform"),
    )

    def __repr__(self):
        return f"<SocialPost(id={self.id}, task_id={self.task_id}, post_id='{self.post_id_on_platform}')>"


class SocialComment(Base):
    """社交媒体评论数据模型

    存储原文的评论数据，强关联到task_id和post_id。
    通过comment_id_on_platform支持评论去重显示。
    """

    __tablename__ = "social_comments"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 任务和原文关联（强关联）
    task_id: Mapped[int] = mapped_column(
        ForeignKey("social_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    post_id: Mapped[int] = mapped_column(
        ForeignKey("social_posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform_id: Mapped[int] = mapped_column(
        ForeignKey("platforms.id"), nullable=False, index=True
    )

    # 平台数据
    comment_id_on_platform: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="平台上的评论ID"
    )
    parent_comment_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="父评论ID（用于楼中楼）"
    )

    # 评论内容
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 互动数据
    likes_count: Mapped[int] = mapped_column(Integer, default=0)
    sub_comments_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="子评论数"
    )

    # 媒体资源
    images: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # 发布信息
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # 原始数据
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 采集信息
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="数据采集时间"
    )

    # 软删除
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    task: Mapped["SocialTask"] = relationship(
        "SocialTask", back_populates="comments", lazy="selectin"
    )
    post: Mapped["SocialPost"] = relationship(
        "SocialPost", back_populates="comments", lazy="selectin"
    )
    platform: Mapped["Platform"] = relationship(
        "src.social_media.monitors.models.Platform",
        foreign_keys=[platform_id],
        lazy="selectin",
    )

    # 索引：支持评论去重和查询优化
    __table_args__ = (
        Index("ix_comment_platform_commentid", "platform_id", "comment_id_on_platform"),
        Index("ix_comment_post", "post_id", "collected_at"),
    )

    def __repr__(self):
        return f"<SocialComment(id={self.id}, task_id={self.task_id}, comment_id='{self.comment_id_on_platform}')>"
