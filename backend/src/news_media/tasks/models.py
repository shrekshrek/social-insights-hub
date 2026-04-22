"""新闻采集任务与文章数据模型"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.database import Base

if TYPE_CHECKING:
    from src.auth.models import User
    from src.news_media.monitors.models import NewsMonitor
    from src.strategies.models import Strategy


class NewsTask(Base):
    """新闻采集任务"""

    __tablename__ = "news_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="任务名称")
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("news_monitors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属监测项目ID",
    )
    strategy_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="所属策略ID（策略流程专用）",
    )
    keywords: Mapped[str] = mapped_column(Text, nullable=False, comment="搜索关键词")
    phase: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True, comment="采集阶段: probe / collect"
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="pending",
        index=True,
        comment="任务状态: pending / running / completed / failed",
    )
    search_params: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="搜索参数（时间范围、地区、最大结果数等）"
    )
    articles_count: Mapped[int] = mapped_column(
        Integer, server_default="0", comment="采集到的文章数量"
    )
    auto_analyze: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False,
        comment="采集完成后是否自动触发分析链（对标 SocialTask.auto_analyze）",
    )
    analysis_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="任务级聚合分析结果"
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="任务开始时间"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="任务完成时间"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True, comment="创建者用户ID"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    monitor: Mapped["NewsMonitor"] = relationship(
        "src.news_media.monitors.models.NewsMonitor",
        back_populates="tasks",
        lazy="selectin",
    )
    user: Mapped["User"] = relationship(
        "src.auth.models.User", foreign_keys=[user_id], lazy="selectin"
    )
    strategy: Mapped["Strategy | None"] = relationship(
        "Strategy", foreign_keys=[strategy_id], lazy="select", back_populates="news_tasks"
    )
    articles: Mapped[list["NewsArticle"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", lazy="select"
    )


class NewsArticle(Base):
    """新闻文章 — 对标社媒的 SocialPost

    存储 SerpAPI 搜索到的文章元数据 + Crawl4AI 抓取的全文 + 逐篇轻量分析结果。
    probe 阶段仅有元数据和 snippet；collect 阶段补充 full_text 和分析字段。
    每篇文章属于一个采集任务，同一 URL 在不同任务下各自独立存储，标注结果互不干扰。
    """

    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("news_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属采集任务ID",
    )
    url: Mapped[str] = mapped_column(
        String(2048), nullable=False, index=True, comment="文章链接"
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False, comment="文章标题")
    snippet: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="SerpAPI 返回的摘要片段"
    )
    source_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="来源媒体名称"
    )
    source_tier: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="tier3",
        comment="来源等级: tier1(权威央媒) / tier2(行业门户) / tier3(其他) / wechat_mp(微信公众号)",
    )
    author: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="作者"
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="发布时间"
    )
    image_url: Mapped[str | None] = mapped_column(
        String(2048), nullable=True, comment="配图链接"
    )

    # Crawl4AI 抓取的全文（probe 阶段为 NULL）
    full_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Crawl4AI 抓取的全文（仅内部分析用，不对外展示）"
    )

    # 逐篇轻量分析结果（news_tagging_chain 产出）
    relevance: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="与研究目标的相关程度: high / medium / low"
    )
    sentiment: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="情感分 -2 ~ 2: -2强烈负面 / -1轻度负面 / 0中性 / 1轻度正面 / 2强烈正面"
    )
    article_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="文章类型: report / opinion / pr / analysis"
    )
    mentioned_entities: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment='提及的实体名单: [{"name": "...", "role": "target/competitor/context"}]'
    )
    key_quotes: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment='关键引述: [{"speaker": "...", "quote": "..."}]'
    )
    summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="一句话摘要"
    )

    # 搜索渠道
    search_source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="baidu",
        comment="搜索渠道: baidu / sogou / bing / wechat_mp"
    )

    # 原始数据
    raw_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="SerpAPI 原始响应（保留以支持未来重解析）"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    task: Mapped["NewsTask"] = relationship(
        back_populates="articles", lazy="select"
    )
