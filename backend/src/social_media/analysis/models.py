"""分析模块数据模型

简化设计：
- AnalysisJob: 统一的AI分析任务记录（合并原 TaskAnalysisResult 和 ProjectAnalysisResult）
- PostAnalysis: 帖子级分析结果，包含初筛 + 帖子深度 + 评论深度
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from sqlalchemy import String, Integer, Float, ForeignKey, Text, DateTime, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.database import Base

if TYPE_CHECKING:
    from src.social_media.tasks.models import DataTask, SocialPost
    from src.social_media.projects.models import SocialProject
    from src.auth.models import User


class AnalysisType(str, Enum):
    """分析类型枚举"""
    # 任务级分析（需要 task_id）
    SCREENING_POSTS = "screening_posts"      # 帖子初筛
    DEEP_POSTS = "deep_posts"                # 帖子深度分析
    DEEP_COMMENTS = "deep_comments"          # 评论深度分析
    ENTITY_NORMALIZATION = "entity_normalization"    # 实体归一化
    OPINION_NORMALIZATION = "opinion_normalization"  # 观点归一化
    AGGREGATION = "aggregation"              # 聚合分析

    # 项目级分析（task_id 为空）
    TOPIC_CLUSTERING = "topic_clustering"    # 主题聚类
    COMPETITIVE_ANALYSIS = "competitive"     # 竞品分析


class AnalysisStatus(str, Enum):
    """分析状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PostAnalysis(Base):
    """帖子AI分析结果

    功能：
    1. 初筛分析：spam_score, value_score, relevance_score, sentiment
    2. 互动指数：cii (Content Interaction Index)
    3. 帖子深度分析：post_deep_result (实体、观点、摘要)
    4. 评论深度分析：comment_deep_result (评论的实体和观点聚合)
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
        comment="广告分（0-10，分数越高越像广告/营销内容）"
    )
    value_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="价值分（0-10，分数越高内容价值越大）"
    )
    relevance_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="相关度分（0-10，分数越高相关度越高）"
    )
    sentiment: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="情感倾向（-2: 强烈负面, -1: 负面, 0: 中性, 1: 正面, 2: 强烈正面）"
    )

    # ===== 互动指数 =====
    cii: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="内容互动指数 (Content Interaction Index)，基于互动数据计算"
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


class AnalysisJob(Base):
    """AI分析任务（统一模型）

    合并原 TaskAnalysisResult 和 ProjectAnalysisResult，
    通过 task_id 是否为空来区分任务级/项目级分析。

    任务级分析类型：screening_posts, deep_posts, deep_comments
    项目级分析类型：topic_clustering, competitive
    """

    __tablename__ = "analysis_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)

    # ===== 关联关系 =====
    project_id: Mapped[int] = mapped_column(
        ForeignKey("social_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联的项目ID（必填）"
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("social_data_tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="关联的数据任务ID（任务级分析时填写，项目级分析时为空）"
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        comment="执行分析的用户ID"
    )

    # ===== 分析类型 =====
    analysis_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="分析类型: screening_posts/deep_posts/deep_comments/topic_clustering/competitive"
    )

    # ===== 分析配置（主要用于项目级分析）=====
    analysis_config: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="分析配置参数（如聚类数量、竞品关键词等）"
    )
    source_task_ids: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment="源任务ID列表（项目级分析时指定的任务范围）"
    )

    # ===== 统计信息 =====
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

    # ===== 结果数据 =====
    result_data: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="聚合统计结果"
    )
    analysis_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="分析摘要"
    )

    # ===== Celery任务信息 =====
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

    # ===== 性能指标 =====
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

    # ===== Token使用统计 =====
    token_usage: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Token使用统计（包含成本信息）"
    )

    # ===== 错误信息 =====
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="错误信息"
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
    project: Mapped["SocialProject"] = relationship(
        "src.social_media.projects.models.SocialProject",
        foreign_keys=[project_id],
        lazy="selectin"
    )
    task: Mapped["DataTask | None"] = relationship(
        "src.social_media.tasks.models.DataTask",
        foreign_keys=[task_id],
        lazy="selectin"
    )
    user: Mapped["User"] = relationship(
        "src.auth.models.User",
        foreign_keys=[user_id],
        lazy="selectin"
    )

    # ===== 索引 =====
    __table_args__ = (
        Index('idx_analysis_job_project', 'project_id'),
        Index('idx_analysis_job_task', 'task_id'),
        Index('idx_analysis_job_type_status', 'analysis_type', 'status'),
        Index('idx_analysis_job_created_at', 'created_at'),
        Index('idx_analysis_job_user', 'user_id'),
    )

    def __repr__(self):
        return f"<AnalysisJob(id={self.id}, type='{self.analysis_type}', status='{self.status}')>"

    @property
    def is_task_level(self) -> bool:
        """是否为任务级分析"""
        return self.task_id is not None

    @property
    def is_project_level(self) -> bool:
        """是否为项目级分析"""
        return self.task_id is None


