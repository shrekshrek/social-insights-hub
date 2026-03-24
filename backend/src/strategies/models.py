"""策略定义数据模型"""

from typing import TYPE_CHECKING
from datetime import datetime
from sqlalchemy import (
    Integer,
    String,
    DateTime,
    ForeignKey,
    JSON,
    CheckConstraint,
    Index,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.auth.models import User
    from src.social_media.analysis.models import AnalysisSlice
    from src.social_media.monitors.models import Monitor


class Strategy(Base):
    """策略研究引擎

    智能研究编排者：研究设计 → 探测验证 → 全量采集 → 自动建切片 → 产出生成。
    用户全程留在策略页面，系统自动完成 Monitor 创建、任务管理、切片创建。
    """

    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="策略名称"
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True, comment="创建者用户ID"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="draft",
        comment="状态: draft / planned / probing / collecting / ready / phase1_done / phase2_done / completed",
    )
    brand_brief: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="结构化 Brand Brief"
    )

    # ① 研究设计
    research_design: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="研究设计（research_design_chain 输出）"
    )

    # ② 探测验证
    probe_review_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="探测审查结果（probe_review_chain 输出）"
    )
    probe_round: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
        comment="当前探测轮次（最多 3）",
    )

    # ③ 数据就绪
    coverage_check_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="覆盖度验证结果（coverage_check_chain 输出）"
    )

    # ④ 产出生成
    output_type: Mapped[str | None] = mapped_column(
        String(30), nullable=True,
        comment="产出类型: brand_strategy / insight_report",
    )
    phase1_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Phase 1: Tension + Opportunity"
    )
    phase2_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Phase 2: Role + Strategy"
    )
    phase3_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Phase 3: Big Idea + Content Strategy"
    )

    # 关联
    monitor_id: Mapped[int | None] = mapped_column(
        ForeignKey("monitors.id"), nullable=True,
        comment="策略创建的 Monitor ID",
    )
    task_ids: Mapped[list] = mapped_column(
        JSON, nullable=False, server_default="[]",
        comment="策略创建的所有 DataTask ID",
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    creator: Mapped["User"] = relationship(
        "src.auth.models.User",
        foreign_keys=[created_by],
        lazy="selectin",
    )
    monitor: Mapped["Monitor | None"] = relationship(
        "src.social_media.monitors.models.Monitor",
        foreign_keys=[monitor_id],
        lazy="selectin",
    )
    slices: Mapped[list["StrategySlice"]] = relationship(
        back_populates="strategy",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'planned', 'probing', 'collecting', 'ready', "
            "'phase1_done', 'phase2_done', 'completed')",
            name="valid_status",
        ),
    )


class StrategySlice(Base):
    """策略-切片关联表

    记录策略引用了哪些项目级分析切片，可跨项目引用。
    """

    __tablename__ = "strategy_slices"

    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"),
        primary_key=True,
    )
    slice_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_slices.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # 关系
    strategy: Mapped["Strategy"] = relationship(
        back_populates="slices",
    )
    slice: Mapped["AnalysisSlice"] = relationship(
        "src.social_media.analysis.models.AnalysisSlice",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_strategy_slices_slice_id", "slice_id"),
    )
