"""分析模块数据模型

简化设计：
- PostAnalysis: 唯一的分析表，包含初筛分析 + 帖子深度分析 + 评论深度分析
- TaskAnalysisResult: 任务级分析结果记录
- ProjectAnalysisResult: 项目级分析结果记录（预留）

评论不需要单独的初筛分析，评论深度分析结果聚合存储在帖子记录中。
"""

from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, Integer, Float, ForeignKey, Text, DateTime, Boolean, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.database import Base

if TYPE_CHECKING:
    from src.social_media.tasks.models import DataTask, SocialPost
    from src.social_media.projects.models import SocialProject
    from src.auth.models import User


class PostAnalysis(Base):
    """帖子AI分析结果（唯一的分析表）

    功能：
    1. 初筛分析：spam_score, value_score, relevance_score, sentiment
    2. 帖子深度分析：post_deep_result (实体、观点、摘要)
    3. 评论深度分析：comment_deep_result (评论的实体和观点聚合)
    """

    __tablename__ = "post_analysis"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 关联关系
    task_id: Mapped[int] = mapped_column(
        ForeignKey("social_data_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联的数据任务ID"
    )
    post_id: Mapped[int] = mapped_column(
        ForeignKey("social_posts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # 一个帖子只有一条分析记录
        index=True,
        comment="关联的帖子ID"
    )

    # ===== 初筛分析 (0-10分) =====
    spam_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="垃圾分（0-10，分数越高越像垃圾）"
    )
    value_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="价值分（0-10，分数越高价值越大）"
    )
    relevance_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="相关度分（0-10，分数越高相关度越高）"
    )
    sentiment: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="情感倾向（-1: 负面, 0: 中性, 1: 正面）"
    )

    # ===== 深度分析 (JSON格式) =====
    post_deep_result: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="帖子深度分析结果：实体、观点、摘要"
    )
    comment_deep_result: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="评论深度分析聚合结果：从评论中提取的实体和观点"
    )

    # ===== 元数据 =====
    analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最后分析时间"
    )
    analysis_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="使用的AI模型"
    )

    # ===== 时间戳 =====
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # ===== 关系 =====
    task: Mapped["DataTask"] = relationship(
        "src.social_media.tasks.models.DataTask",
        foreign_keys=[task_id],
        lazy="selectin"
    )
    post: Mapped["SocialPost"] = relationship(
        "src.social_media.tasks.models.SocialPost",
        foreign_keys=[post_id],
        lazy="selectin"
    )

    # ===== 索引 =====
    __table_args__ = (
        Index('idx_post_analysis_task_id', 'task_id'),
        Index('idx_post_analysis_scores', 'spam_score', 'value_score', 'relevance_score'),
    )

    def __repr__(self):
        return f"<PostAnalysis(id={self.id}, post_id={self.post_id})>"


class TaskAnalysisResult(Base):
    """任务级分析结果记录

    记录每次分析任务的执行情况、统计信息和聚合结果
    支持的分析类型：
    - screening_posts: 帖子初筛
    - deep_posts: 帖子深度分析
    - deep_comments: 评论深度分析
    """

    __tablename__ = "task_analysis_results"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 关联关系
    task_id: Mapped[int] = mapped_column(
        ForeignKey("social_data_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联的数据任务ID"
    )

    # 分析类型
    analysis_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="分析类型: screening_posts/deep_posts/deep_comments"
    )

    # 结果数据
    result_data: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="聚合统计结果（如成功率、平均分等）"
    )
    analysis_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="分析摘要"
    )

    # 统计信息
    source_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="源数据数量"
    )
    analyzed_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="成功分析数量"
    )
    failed_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="失败数量"
    )

    # Celery任务信息
    celery_task_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="Celery任务ID"
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
        comment="状态: pending/processing/completed/failed"
    )

    # 性能指标
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="任务开始时间"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="任务完成时间"
    )
    processing_time: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="处理耗时（秒）"
    )

    # Token使用统计
    token_usage: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Token使用统计（包含成本信息）"
    )

    # 错误信息
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="错误信息"
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # 关系
    task: Mapped["DataTask"] = relationship(
        "src.social_media.tasks.models.DataTask",
        foreign_keys=[task_id],
        lazy="selectin"
    )

    # 索引
    __table_args__ = (
        Index('idx_task_analysis_type_status', 'analysis_type', 'status'),
        Index('idx_task_analysis_created_at', 'created_at'),
    )

    def __repr__(self):
        return f"<TaskAnalysisResult(id={self.id}, type='{self.analysis_type}', status='{self.status}')>"


class ProjectAnalysisResult(Base):
    """项目级分析结果模型（预留）

    存储项目级的全局分析结果，如主题聚类、竞品分析等。
    """

    __tablename__ = "project_analysis_results"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 关联关系
    project_id: Mapped[int] = mapped_column(
        ForeignKey("social_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联的项目ID"
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        comment="执行分析的用户ID"
    )

    # 分析配置
    analysis_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="分析类型: topic_clustering/competitive_analysis"
    )
    analysis_config: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="分析配置参数"
    )

    # 数据源（多任务聚合）
    source_task_ids: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment="源任务ID列表"
    )
    source_data_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="源数据总数"
    )

    # 分析结果
    result_data: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="分析结果数据（JSON格式）"
    )
    analysis_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="分析结果摘要"
    )

    # Celery任务信息
    celery_task_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="Celery任务ID"
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
        comment="状态: pending/processing/completed/failed"
    )

    # 性能指标
    processing_time: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="处理耗时（秒）"
    )

    # Token使用统计
    token_usage: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Token使用统计（包含成本信息）"
    )

    # 错误信息
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="错误信息"
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="完成时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # 关系
    project: Mapped["SocialProject"] = relationship(
        "src.social_media.projects.models.SocialProject",
        foreign_keys=[project_id],
        lazy="selectin"
    )
    user: Mapped["User"] = relationship(
        "src.auth.models.User",
        foreign_keys=[user_id],
        lazy="selectin"
    )

    # 索引
    __table_args__ = (
        Index('idx_project_analysis_type_status', 'analysis_type', 'status'),
        Index('idx_project_analysis_created_at', 'created_at'),
        Index('idx_project_analysis_project_user', 'project_id', 'user_id'),
    )

    def __repr__(self):
        return f"<ProjectAnalysisResult(id={self.id}, project_id={self.project_id}, type='{self.analysis_type}', status='{self.status}')>"
