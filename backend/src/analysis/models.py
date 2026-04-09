"""分析模块数据模型（社媒专属残留）

本文件残留的是社媒专属的数据模型：
- PostAnalysis: 社媒原文级分析结果（初筛 + 原文深度 + 评论深度）
- AnalysisSlice: 社媒项目级手动合并分析切片

跨渠道的 AnalysisJob / AnalysisType / AnalysisStatus 已迁至 `src/jobs/`。
见 docs/adr-001-channel-local-analysis.md P1。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.database import Base

# 跨渠道 AnalysisJob/AnalysisType/AnalysisStatus 已迁至 src/jobs/models.py（P1, ADR-001）。
# 这里 re-export 以便旧调用方过渡；新代码请直接 `from src.jobs.models import ...`。
from src.jobs.models import (  # noqa: F401
    AnalysisJob,
    AnalysisStatus,
    AnalysisType,
)

if TYPE_CHECKING:
    from src.auth.models import User
    from src.social_media.monitors.models import SocialMonitor as SocialMonitor
    from src.social_media.tasks.models import SocialPost
    from src.social_media.tasks.models import SocialTask as SocialTask


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


class AnalysisSlice(Base):
    """项目级手动合并分析切片

    设计意图：
    - 与 AnalysisJob（LLM/Celery 任务流水）分离
    - 专门用于保存"勾选多个任务 -> 生成一份合并报告"的历史切片
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

    # 注意：result_data 会在 Celery 流水线中被逐步"原地更新"（stage2/stage3/reports 等）。
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
