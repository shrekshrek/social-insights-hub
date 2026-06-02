"""新闻分析切片模型

用户从监测项目中选择若干任务组合成切片，系统合并文章后运行 insight 分析。
与社媒 SocialSlice 对齐：任务负责采集+打标，切片负责聚合分析。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, UniqueConstraint, text
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.database import Base

if TYPE_CHECKING:
    from src.auth.models import User
    from src.news_media.monitors.models import NewsMonitor


class NewsSlice(Base):
    """新闻分析切片

    用户勾选若干 NewsTask → 合并文章 → URL 去重 → 低相关过滤 → 描述层 SQL
    → Pass 1 LLM（归一/抽取/聚类） → 派生层 SQL → Pass 2 LLM（briefing/event_titles）。
    详见 docs/adr/003-news-analysis-redesign.md。

    切片级配置（subject / competitors）作为独立列，与分析产物 result_data 解耦：
    LLM 重跑覆写 result_data 不会清掉切片配置；前端列表/详情可在 analyzing
    中间态读到配置而无需等分析完成。
    """

    __tablename__ = "news_slices"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="切片名称")

    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("news_monitors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属新闻监测项目",
    )

    included_task_ids: Mapped[list[int]] = mapped_column(
        JSON, nullable=False, comment="参与合并的 NewsTask ID 列表"
    )

    subject: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment=(
            "聚焦切片的主体品牌名（None=大盘视角，无 target/competitor 区分）。"
            "驱动 _enforce_entity_roles 的归类模式，并在前端列表显示 Focus/大盘 徽章。"
        ),
    )

    competitors: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'::json"),
        comment="聚焦切片的竞品品牌名列表（subject 为 None 时应为空）",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        comment="pending | analyzing | completed | failed",
    )

    result_data: Mapped[dict | None] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=True,
        comment="insight 分析结果",
    )

    stats: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="统计摘要（文章数/来源分布/情感分布/实体 Top N）",
    )

    error_message: Mapped[str | None] = mapped_column(
        String(1000), nullable=True, comment="失败原因"
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        comment="创建者",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    monitor: Mapped["NewsMonitor"] = relationship(
        "src.news_media.monitors.models.NewsMonitor",
        foreign_keys=[monitor_id],
        lazy="selectin",
    )
    user: Mapped["User"] = relationship(
        "src.auth.models.User",
        foreign_keys=[user_id],
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_news_slices_monitor", "monitor_id"),
        Index("idx_news_slices_created_at", "created_at"),
        UniqueConstraint("monitor_id", "name", name="uq_news_slices_monitor_name"),
    )
