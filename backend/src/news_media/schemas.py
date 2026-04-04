"""新闻媒体模块 Schemas"""

from datetime import datetime

from pydantic import Field

from src.schemas import CustomBaseModel


# ==================== NewsMonitor Schemas ====================


class NewsMonitorCreate(CustomBaseModel):
    """创建新闻监测项目"""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    search_provider: str = Field(default="serpapi_baidu")


class NewsMonitorUpdate(CustomBaseModel):
    """更新新闻监测项目"""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None


class NewsMonitorRead(CustomBaseModel):
    """新闻监测项目详情"""

    id: int
    name: str
    description: str | None
    owner_id: int
    search_provider: str
    created_at: datetime
    updated_at: datetime


class NewsMonitorReadWithOwner(NewsMonitorRead):
    """新闻监测项目详情（含创建者用户名）"""

    owner_username: str

    @classmethod
    def from_orm_full(cls, monitor) -> "NewsMonitorReadWithOwner":
        return cls(
            id=monitor.id,
            name=monitor.name,
            description=monitor.description,
            owner_id=monitor.owner_id,
            search_provider=monitor.search_provider,
            created_at=monitor.created_at,
            updated_at=monitor.updated_at,
            owner_username=monitor.owner.username if monitor.owner else "",
        )


# ==================== NewsTask Schemas ====================


class NewsTaskCreate(CustomBaseModel):
    """创建新闻任务"""

    name: str = Field(..., min_length=1, max_length=255)
    keywords: str = Field(..., min_length=1)
    phase: str | None = Field(None, pattern=r"^(probe|collect)$")
    search_params: dict | None = None


class NewsTaskRead(CustomBaseModel):
    """新闻任务详情"""

    id: int
    name: str
    monitor_id: int
    strategy_id: int | None
    keywords: str
    phase: str | None
    status: str
    search_provider: str
    search_params: dict | None
    articles_count: int
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
            status=task.status,
            search_provider=task.search_provider,
            search_params=task.search_params,
            articles_count=task.articles_count,
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
        task = article.task
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
            relevance=article.relevance,
            sentiment=article.sentiment,
            article_type=article.article_type,
            mentioned_entities=article.mentioned_entities,
            key_quotes=article.key_quotes,
            summary=article.summary,
            created_at=article.created_at,
            updated_at=article.updated_at,
            task_name=task.name if task else None,
            monitor_name=task.monitor.name if task and task.monitor else None,
        )
