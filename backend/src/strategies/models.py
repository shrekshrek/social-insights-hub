"""策略定义数据模型"""

from typing import TYPE_CHECKING
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    String,
    DateTime,
    JSON,
    CheckConstraint,
    Index,
    Table,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.auth.models import User
    from src.social_media.analysis.models import SocialSlice
    from src.social_media.monitors.models import SocialMonitor
    from src.social_media.tasks.models import SocialTask
    from src.news_media.monitors.models import NewsMonitor
    from src.news_media.tasks.models import NewsTask


# 策略-参与者关联表（多对多）
strategy_participants = Table(
    "strategy_participants",
    Base.metadata,
    Column(
        "strategy_id",
        Integer,
        ForeignKey("strategies.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "user_id",
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Strategy(Base):
    """策略研究引擎

    智能研究编排者：研究设计 → 探测验证 → 全量采集 → 自动建切片 → 产出生成。
    用户全程留在策略页面，系统自动完成 SocialMonitor 创建、任务管理、切片创建。
    """

    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="策略名称"
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True, comment="创建者用户ID"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="draft",
        comment=(
            "状态: draft / planned / probing / collecting / ready / "
            "insight_done / brand_role_done / "
            "agenda_map_done / landscape_done / completed"
        ),
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
    # output_type 决定走哪条产出路径（两条路径都是 3 层递进）：
    #   - brand_strategy: 填充 insight_result → brand_role_result → big_idea_result
    #   - market_report:  填充 agenda_map_result → landscape_result → strategic_brief_result
    output_type: Mapped[str | None] = mapped_column(
        String(30), nullable=True,
        comment="产出类型: brand_strategy / market_report",
    )
    insight_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="brand_strategy 第 1 层 Insight: Tension + Opportunity",
    )
    brand_role_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="brand_strategy 第 2 层 Brand Role: Role + Strategy",
    )
    big_idea_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="brand_strategy 第 3 层 Big Idea: Big Idea + Content Strategy",
    )
    agenda_map_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="market_report 第 1 层 Agenda Map: 媒体议程图",
    )
    landscape_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="market_report 第 2 层 Landscape: 竞争格局 + 话语权",
    )
    strategic_brief_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="market_report 第 3 层 Strategic Brief: 战略简报",
    )

    # 关联
    social_monitor_id: Mapped[int | None] = mapped_column(
        ForeignKey("social_monitors.id"), nullable=True,
        comment="策略创建的社媒 SocialMonitor ID",
    )
    news_monitor_id: Mapped[int | None] = mapped_column(
        ForeignKey("news_monitors.id"), nullable=True,
        comment="策略创建的新闻 NewsMonitor ID",
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    user: Mapped["User"] = relationship(
        "src.auth.models.User",
        foreign_keys=[user_id],
        lazy="selectin",
    )
    participants: Mapped[list["User"]] = relationship(
        "src.auth.models.User",
        secondary=strategy_participants,
        lazy="selectin",
    )
    social_monitor: Mapped["SocialMonitor | None"] = relationship(
        "src.social_media.monitors.models.SocialMonitor",
        foreign_keys=[social_monitor_id],
        lazy="selectin",
    )
    news_monitor: Mapped["NewsMonitor | None"] = relationship(
        "src.news_media.monitors.models.NewsMonitor",
        foreign_keys=[news_monitor_id],
        lazy="selectin",
    )
    social_tasks: Mapped[list["SocialTask"]] = relationship(
        "src.social_media.tasks.models.SocialTask",
        foreign_keys="SocialTask.strategy_id",
        back_populates="strategy",
        lazy="select",
    )
    news_tasks: Mapped[list["NewsTask"]] = relationship(
        "src.news_media.tasks.models.NewsTask",
        foreign_keys="NewsTask.strategy_id",
        back_populates="strategy",
        lazy="select",
    )
    slices: Mapped[list["StrategySlice"]] = relationship(
        back_populates="strategy",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'planned', 'probing', 'collecting', 'ready', "
            "'insight_done', 'brand_role_done', "
            "'agenda_map_done', 'landscape_done', 'completed')",
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
        ForeignKey("social_slices.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # 关系
    strategy: Mapped["Strategy"] = relationship(
        back_populates="slices",
    )
    slice: Mapped["SocialSlice"] = relationship(
        "src.social_media.analysis.models.SocialSlice",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_strategy_slices_slice_id", "slice_id"),
    )
