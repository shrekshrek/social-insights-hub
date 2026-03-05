"""策略定义数据模型"""

from typing import TYPE_CHECKING
from datetime import datetime
from sqlalchemy import (
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
    from src.social_media.analysis.models import ProjectAnalysisSlice


class Strategy(Base):
    """策略定义

    基于切片数据的 AI 策略草案生成器。
    3 阶段分步生成: 洞察层 → 策略层 → 创意层。
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
        comment="状态: draft / phase1_done / phase2_done / completed",
    )
    brand_brief: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="可选 Brand Brief"
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
    slices: Mapped[list["StrategySlice"]] = relationship(
        back_populates="strategy",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'phase1_done', 'phase2_done', 'completed')",
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
        ForeignKey("project_analysis_slices.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # 关系
    strategy: Mapped["Strategy"] = relationship(
        back_populates="slices",
    )
    slice: Mapped["ProjectAnalysisSlice"] = relationship(
        "src.social_media.analysis.models.ProjectAnalysisSlice",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_strategy_slices_slice_id", "slice_id"),
    )
