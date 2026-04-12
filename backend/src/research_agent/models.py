"""ResearchTask 数据模型"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, DateTime, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.database import Base

if TYPE_CHECKING:
    from src.auth.models import User
    from src.strategies.models import Strategy
    from src.jobs.models import AnalysisJob


class ResearchTask(Base):
    """研究任务

    独立研究或策略关联研究，由 LangGraph 状态图执行。
    每个任务关联一个 AnalysisJob 追踪 token/cost。
    """

    __tablename__ = "research_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)

    # ===== 输入 =====
    query: Mapped[str] = mapped_column(Text, nullable=False, comment="研究主题")
    research_questions: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="研究问题列表"
    )
    search_config: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="research_angles, focus_domains 等搜索配置"
    )

    # ===== 关联 =====
    strategy_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="关联策略（策略模式下非空）",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        comment="创建者",
    )
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="关联 AnalysisJob（token/cost 追踪）",
    )

    # ===== 状态 =====
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
        comment="pending / running / completed / failed",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="失败原因"
    )

    # ===== 结果 =====
    result_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="synthesis + findings + sources"
    )
    stats: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="rounds, documents_analyzed, candidates_total 等统计",
    )

    # ===== 时间戳 =====
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ===== 关系 =====
    strategy: Mapped["Strategy | None"] = relationship(
        "src.strategies.models.Strategy",
        foreign_keys=[strategy_id],
        back_populates="research_tasks",
        lazy="selectin",
    )
    user: Mapped["User"] = relationship(
        "src.auth.models.User",
        foreign_keys=[user_id],
        lazy="selectin",
    )
    job: Mapped["AnalysisJob | None"] = relationship(
        "src.jobs.models.AnalysisJob",
        foreign_keys=[job_id],
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_research_task_strategy", "strategy_id"),
        Index("idx_research_task_status", "status"),
        Index("idx_research_task_user", "user_id"),
        Index("idx_research_task_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<ResearchTask(id={self.id}, status='{self.status}')>"
