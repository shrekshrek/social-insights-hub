"""分析模块数据模型

简化设计：
- AnalysisJob: 统一的AI分析任务记录（合并原 TaskAnalysisResult 和 ProjectAnalysisResult）
- PostAnalysis: 原文级分析结果，包含初筛 + 原文深度 + 评论深度
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from sqlalchemy import String, Integer, Float, ForeignKey, Text, DateTime, JSON, Index
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.database import Base

if TYPE_CHECKING:
    from src.social_media.tasks.models import SocialTask as SocialTask, SocialPost
    from src.social_media.monitors.models import SocialMonitor as SocialMonitor
    from src.news_media.models import NewsMonitor, NewsTask
    from src.auth.models import User


class AnalysisType(str, Enum):
    """分析类型枚举

    仅包含涉及 LLM API 调用的分析类型。
    聚合分析（aggregation）不涉及 LLM，不应创建 AnalysisJob 记录。
    """

    # 社媒任务级分析（需要 social_task_id）
    SCREENING_POSTS = "screening_posts"  # 原文初筛
    DEEP_POSTS = "deep_posts"  # 原文深度分析
    DEEP_COMMENTS = "deep_comments"  # 评论深度分析
    ENTITY_NORMALIZATION = "entity_normalization"  # 实体归一化
    OPINION_NORMALIZATION = "opinion_normalization"  # 观点归一化

    # 社媒项目级分析（social_task_id 为空）
    TOPIC_CLUSTERING = "topic_clustering"  # 主题聚类
    COMPETITIVE_ANALYSIS = "competitive"  # 竞品分析
    MONITOR_SLICE_SUMMARY = "monitor_slice_summary"  # 监测切片整体总结（Stage3）

    # 策略链（关联 strategy.social_monitor_id 或 strategy.news_monitor_id）
    STRATEGY_PROBE_REVIEW = "strategy_probe_review"  # 探测审查
    STRATEGY_COVERAGE_CHECK = "strategy_coverage_check"  # 覆盖度验证
    STRATEGY_PHASE1 = "strategy_phase1"  # Phase 1 洞察层
    STRATEGY_PHASE2 = "strategy_phase2"  # Phase 2 策略层
    STRATEGY_PHASE3 = "strategy_phase3"  # Phase 3 创意层

    # 新闻媒体分析（关联 news_monitor_id / news_task_id）
    NEWS_TAGGING = "news_tagging"  # 逐篇标注（news_tagging_chain）
    NEWS_INSIGHT = "news_insight"  # 整体洞察（news_insight_chain）


class AnalysisStatus(str, Enum):
    """分析状态枚举"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PostAnalysis(Base):
    """原文AI分析结果

    功能：
    1. 初筛分析：spam_score, value_score, relevance_score, sentiment
    2. 互动指数：cii (Content Interaction Index)
    3. 原文深度分析：post_deep_result (实体、观点、摘要)
    4. 评论深度分析：comment_deep_result (评论的实体和观点聚合)
    """

    __tablename__ = "post_analysis"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 关联关系
    task_id: Mapped[int] = mapped_column(
        ForeignKey("social_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联的数据任务ID",
    )
    post_id: Mapped[int] = mapped_column(
        ForeignKey("social_posts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # 一个原文只有一条分析记录
        index=True,
        comment="关联的原文ID",
    )

    # ===== 初筛分析 (0-10分) =====
    spam_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="广告分（0-10，分数越高越像广告/营销内容）"
    )
    value_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="价值分（0-10，分数越高内容价值越大）"
    )
    relevance_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="相关度分（0-10，分数越高相关度越高）"
    )
    sentiment: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="情感倾向（-2: 强烈负面, -1: 负面, 0: 中性, 1: 正面, 2: 强烈正面）",
    )

    # ===== 互动指数 =====
    cii: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="内容互动指数 (Content Interaction Index)，基于互动数据计算",
    )

    # ===== 深度分析 (JSON格式) =====
    post_deep_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="原文深度分析结果：实体、观点、摘要"
    )
    comment_deep_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="评论深度分析聚合结果：从评论中提取的实体和观点"
    )

    # ===== 元数据 =====
    analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最后分析时间"
    )
    analysis_model: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="使用的AI模型"
    )

    # ===== 时间戳 =====
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ===== 关系 =====
    task: Mapped["SocialTask"] = relationship(
        "src.social_media.tasks.models.SocialTask",
        foreign_keys=[task_id],
        lazy="selectin",
    )
    post: Mapped["SocialPost"] = relationship(
        "src.social_media.tasks.models.SocialPost",
        foreign_keys=[post_id],
        lazy="selectin",
    )

    # ===== 索引 =====
    __table_args__ = (
        Index("idx_post_analysis_task_id", "task_id"),
        Index(
            "idx_post_analysis_scores", "spam_score", "value_score", "relevance_score"
        ),
    )

    def __repr__(self):
        return f"<PostAnalysis(id={self.id}, post_id={self.post_id})>"


class AnalysisJob(Base):
    """AI分析任务（统一模型）

    统一记录社媒分析、新闻媒体分析、策略分析的 LLM 调用。
    通过各关联 ID 字段区分来源模块：
    - social_monitor_id / social_task_id: 社媒监测模块
    - news_monitor_id / news_task_id: 新闻媒体模块
    - 策略分析通过 social_monitor_id 或 news_monitor_id 关联（analysis_config 中存 strategy_id）
    """

    __tablename__ = "analysis_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)

    # ===== 关联关系 =====
    social_monitor_id: Mapped[int | None] = mapped_column(
        ForeignKey("social_monitors.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="关联的社媒监测项目ID",
    )
    social_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("social_tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="关联的社媒采集任务ID（任务级分析时填写）",
    )
    news_monitor_id: Mapped[int | None] = mapped_column(
        ForeignKey("news_monitors.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="关联的新闻监测项目ID",
    )
    news_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("news_tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="关联的新闻采集任务ID（任务级分析时填写）",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True, comment="执行分析的用户ID"
    )

    # ===== 分析类型 =====
    analysis_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="分析类型: screening_posts/deep_posts/deep_comments/topic_clustering/competitive",
    )

    # ===== 分析配置（主要用于项目级分析）=====
    analysis_config: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="分析配置参数（如聚类数量、竞品关键词等）"
    )
    source_task_ids: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="源任务ID列表（项目级分析时指定的任务范围）"
    )

    # ===== 统计信息 =====
    source_count: Mapped[int] = mapped_column(Integer, default=0, comment="源数据数量")
    analyzed_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="成功分析数量"
    )
    failed_count: Mapped[int] = mapped_column(Integer, default=0, comment="失败数量")

    # ===== 结果数据 =====
    result_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="聚合统计结果"
    )
    analysis_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="分析摘要"
    )

    # ===== Celery任务信息 =====
    celery_task_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True, comment="Celery任务ID"
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
        comment="状态: pending/processing/completed/failed",
    )

    # ===== 性能指标 =====
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="任务开始时间"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="任务完成时间"
    )
    processing_time: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="处理耗时（秒）"
    )

    # ===== Token使用统计 =====
    token_usage: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Token使用统计（包含成本信息）"
    )

    # ===== 错误信息 =====
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="错误信息"
    )

    # ===== 时间戳 =====
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ===== 关系 =====
    social_monitor: Mapped["SocialMonitor | None"] = relationship(
        "src.social_media.monitors.models.SocialMonitor",
        foreign_keys=[social_monitor_id],
        lazy="selectin",
    )
    social_task: Mapped["SocialTask | None"] = relationship(
        "src.social_media.tasks.models.SocialTask",
        foreign_keys=[social_task_id],
        lazy="selectin",
    )
    news_monitor: Mapped["NewsMonitor | None"] = relationship(
        "src.news_media.models.NewsMonitor",
        foreign_keys=[news_monitor_id],
        lazy="selectin",
    )
    news_task: Mapped["NewsTask | None"] = relationship(
        "src.news_media.models.NewsTask",
        foreign_keys=[news_task_id],
        lazy="selectin",
    )
    user: Mapped["User"] = relationship(
        "src.auth.models.User", foreign_keys=[user_id], lazy="selectin"
    )

    # ===== 索引 =====
    __table_args__ = (
        Index("idx_analysis_job_social_monitor", "social_monitor_id"),
        Index("idx_analysis_job_social_task", "social_task_id"),
        Index("idx_analysis_job_news_monitor", "news_monitor_id"),
        Index("idx_analysis_job_news_task", "news_task_id"),
        Index("idx_analysis_job_type_status", "analysis_type", "status"),
        Index("idx_analysis_job_created_at", "created_at"),
        Index("idx_analysis_job_user", "user_id"),
    )

    def __repr__(self):
        return f"<AnalysisJob(id={self.id}, type='{self.analysis_type}', status='{self.status}')>"

    @property
    def is_task_level(self) -> bool:
        """是否为任务级分析"""
        return self.social_task_id is not None or self.news_task_id is not None

    @property
    def is_monitor_level(self) -> bool:
        """是否为项目级分析"""
        return self.social_task_id is None and self.news_task_id is None


class AnalysisSlice(Base):
    """项目级手动合并分析切片

    设计意图：
    - 与 AnalysisJob（LLM/Celery 任务流水）分离
    - 专门用于保存”勾选多个任务 -> 生成一份合并报告”的历史切片
    """

    __tablename__ = "analysis_slices"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="切片名称（可选）",
    )

    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("social_monitors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联的项目ID",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        comment="创建切片的用户ID",
    )

    included_task_ids: Mapped[list[int]] = mapped_column(
        JSON,
        nullable=False,
        comment="参与合并的任务ID列表",
    )

    # 注意：result_data 会在 Celery 流水线中被逐步“原地更新”（stage2/stage3/reports 等）。
    # 使用 MutableDict 以确保 SQLAlchemy 能追踪变更并正确落库。
    result_data: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        comment="切片结果数据",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    monitor: Mapped["SocialMonitor"] = relationship(
        "src.social_media.monitors.models.SocialMonitor",
        foreign_keys=[monitor_id],
        lazy="selectin",
    )
    user: Mapped["User"] = relationship(
        "src.auth.models.User",
        foreign_keys=[user_id],
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_monitor_slices_project", "monitor_id"),
        Index("idx_monitor_slices_created_at", "created_at"),
    )
