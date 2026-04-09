"""跨渠道 AI 分析任务模型

AnalysisJob 是唯一真正跨渠道的共享组件，记录所有渠道（社媒/新闻/策略/知识库）
的 LLM 调用，用于成本追踪、进度查询、状态管理。

通过 FK 关联到各渠道 task（nullable，至多一个非空）：
- social_monitor_id / social_task_id
- news_monitor_id / news_task_id
- 策略分析通过 social_monitor_id 或 news_monitor_id 关联（analysis_config 中存 strategy_id）

依赖方向：`src/jobs/` 不得 import 任何渠道模块（TYPE_CHECKING 下的 relationship hint 除外）。
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, ForeignKey, Text, DateTime, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.database import Base

if TYPE_CHECKING:
    from src.social_media.tasks.models import SocialTask as SocialTask
    from src.social_media.monitors.models import SocialMonitor as SocialMonitor
    from src.news_media.monitors.models import NewsMonitor
    from src.news_media.tasks.models import NewsTask
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
        "src.news_media.monitors.models.NewsMonitor",
        foreign_keys=[news_monitor_id],
        lazy="selectin",
    )
    news_task: Mapped["NewsTask | None"] = relationship(
        "src.news_media.tasks.models.NewsTask",
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
