"""新闻任务与文章 Schemas"""

from datetime import datetime

from pydantic import Field

from src.schemas import CustomBaseModel


# ==================== NewsTask Schemas ====================


class NewsTaskCreate(CustomBaseModel):
    """创建新闻任务"""

    name: str = Field(..., min_length=1, max_length=255)
    keywords: str = Field(..., min_length=1)
    phase: str | None = Field(None, pattern=r"^(probe|collect)$")
    search_params: dict | None = None
    auto_analyze: bool = Field(
        True, description="collect 阶段采集完成后是否自动触发分析链（NEWS_TAGGING + NEWS_INSIGHT）"
    )


class NewsTaskRefine(CustomBaseModel):
    """refine 一个 probe 任务：替换关键词并创建下一轮 probe"""

    keywords: str = Field(..., min_length=1, description="替换后的搜索关键词")


class NewsTaskRead(CustomBaseModel):
    """新闻任务详情"""

    id: int
    name: str
    monitor_id: int
    strategy_id: int | None
    keywords: str
    phase: str | None
    probe_round: int
    parent_probe_id: int | None
    status: str
    search_params: dict | None
    articles_count: int
    auto_analyze: bool
    analysis_result: dict | None
    error_message: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime


class NewsTaskReadWithRelations(NewsTaskRead):
    """新闻任务详情（含关联信息）"""

    monitor_name: str | None = None
    creator_username: str | None = None

    @classmethod
    def from_orm_full(cls, task) -> "NewsTaskReadWithRelations":
        return cls(
            id=task.id,
            name=task.name,
            monitor_id=task.monitor_id,
            strategy_id=task.strategy_id,
            keywords=task.keywords,
            phase=task.phase,
            probe_round=task.probe_round,
            parent_probe_id=task.parent_probe_id,
            status=task.status,
            search_params=task.search_params,
            articles_count=task.articles_count,
            auto_analyze=task.auto_analyze,
            analysis_result=task.analysis_result,
            error_message=task.error_message,
            created_by=task.created_by,
            created_at=task.created_at,
            updated_at=task.updated_at,
            monitor_name=task.monitor.name if task.monitor else None,
            creator_username=task.creator.username if task.creator else None,
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
