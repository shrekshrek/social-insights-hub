"""新闻任务与文章 Schemas"""

from datetime import datetime

from pydantic import Field

from src.schemas import CustomBaseModel


# ==================== NewsTask Schemas ====================


class NewsTaskCreate(CustomBaseModel):
    """创建新闻任务

    phase 默认 collect。独立 monitor 创建一律走 collect；probe 仅由
    strategies 模块编排时显式传入（service 层签名上的 phase 参数会覆盖）。
    """

    name: str = Field(..., min_length=1, max_length=255)
    keywords: str = Field(..., min_length=1)
    phase: str = Field("collect", pattern=r"^(probe|collect)$")
    search_params: dict | None = None
    auto_analyze: bool = Field(
        True, description="collect 阶段采集完成后是否自动触发逐篇标注（NEWS_TAGGING）"
    )


class NewsTaskRead(CustomBaseModel):
    """新闻任务详情"""

    id: int
    name: str
    monitor_id: int
    strategy_id: int | None
    keywords: str
    phase: str
    status: str
    search_params: dict | None
    articles_count: int
    auto_analyze: bool
    analysis_result: dict | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    user_id: int
    created_at: datetime
    updated_at: datetime


class ChannelCount(CustomBaseModel):
    """单渠道的采集量（原始 vs 入库）

    - raw: 去重前原始召回量（从 task.analysis_result.meta.channel_raw_counts 读取）
    - deduped: 去重后入库量（SQL group by search_source 实时统计）
    raw 更能反映渠道健康度；deduped 反映最终可用数据。
    """

    raw: int = 0
    deduped: int = 0


class NewsTaskChannelStats(CustomBaseModel):
    """新闻任务的渠道采集量分布

    按 NewsArticle.search_source 分组统计，用于在任务详情页直观展示
    各搜索渠道的实际贡献，评估渠道健康度与 yield。
    raw_total 反映所有渠道去重前的总召回量，deduped_total 是最终入库总数。
    """

    baidu: ChannelCount = ChannelCount()
    sogou: ChannelCount = ChannelCount()
    wechat_mp: ChannelCount = ChannelCount()
    raw_total: int = 0
    deduped_total: int = 0


class NewsTaskReadWithRelations(NewsTaskRead):
    """新闻任务详情（含关联信息）"""

    monitor_name: str | None = None
    user_username: str | None = None

    @classmethod
    def from_orm_full(cls, task) -> "NewsTaskReadWithRelations":
        return cls(
            id=task.id,
            name=task.name,
            monitor_id=task.monitor_id,
            strategy_id=task.strategy_id,
            keywords=task.keywords,
            phase=task.phase,
            status=task.status,
            search_params=task.search_params,
            articles_count=task.articles_count,
            auto_analyze=task.auto_analyze,
            analysis_result=task.analysis_result,
            started_at=task.started_at,
            completed_at=task.completed_at,
            error_message=task.error_message,
            user_id=task.user_id,
            created_at=task.created_at,
            updated_at=task.updated_at,
            monitor_name=task.monitor.name if task.monitor else None,
            user_username=task.user.username if task.user else None,
        )


# ==================== NewsArticle Schemas ====================


class NewsArticleRead(CustomBaseModel):
    """新闻文章详情"""

    id: int
    task_id: int
    url: str
    title: str
    snippet: str | None
    source_name: str
    source_tier: str
    author: str | None
    published_at: datetime | None
    image_url: str | None
    search_source: str = "baidu"
    # 逐篇分析字段
    relevance: str | None
    sentiment: float | None
    article_type: str | None
    mentioned_entities: list | None
    key_quotes: list | None
    summary: str | None
    created_at: datetime
    updated_at: datetime


class NewsArticleReadWithTask(NewsArticleRead):
    """新闻文章详情（含任务信息）"""

    task_name: str | None = None
    monitor_name: str | None = None

    @classmethod
    def from_orm_full(cls, article) -> "NewsArticleReadWithTask":
        return cls(
            id=article.id,
            task_id=article.task_id,
            url=article.url,
            title=article.title,
            snippet=article.snippet,
            source_name=article.source_name,
            source_tier=article.source_tier,
            author=article.author,
            published_at=article.published_at,
            image_url=article.image_url,
            search_source=article.search_source,
            relevance=article.relevance,
            sentiment=article.sentiment,
            article_type=article.article_type,
            mentioned_entities=article.mentioned_entities,
            key_quotes=article.key_quotes,
            summary=article.summary,
            created_at=article.created_at,
            updated_at=article.updated_at,
            task_name=article.task.name if article.task else None,
            monitor_name=article.task.monitor.name if article.task and article.task.monitor else None,
        )
