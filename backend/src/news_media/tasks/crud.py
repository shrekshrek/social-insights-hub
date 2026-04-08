"""新闻任务与文章 CRUD 操作"""

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.news_media.tasks.models import NewsArticle, NewsTask


def _escape_like(value: str) -> str:
    """转义 LIKE 通配符"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ==================== NewsTask CRUD ====================


async def get_task_by_id(
    db: AsyncSession, task_id: int, load_relations: bool = True
) -> NewsTask | None:
    stmt = select(NewsTask).where(NewsTask.id == task_id)
    if load_relations:
        stmt = stmt.options(
            selectinload(NewsTask.monitor),
            selectinload(NewsTask.creator),
        )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_tasks(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    monitor_id: int | None = None,
    status: str | None = None,
    phase: str | None = None,
    strategy_id: int | None = None,
    search: str | None = None,
) -> tuple[list[NewsTask], int]:
    conditions: list = []
    if monitor_id is not None:
        conditions.append(NewsTask.monitor_id == monitor_id)
    if status is not None:
        conditions.append(NewsTask.status == status)
    if phase is not None:
        conditions.append(NewsTask.phase == phase)
    if strategy_id is not None:
        conditions.append(NewsTask.strategy_id == strategy_id)
    if search:
        escaped = _escape_like(search)
        conditions.append(
            NewsTask.name.ilike(f"%{escaped}%", escape="\\")
            | NewsTask.keywords.ilike(f"%{escaped}%", escape="\\")
        )

    base_stmt = select(NewsTask)
    if conditions:
        base_stmt = base_stmt.where(and_(*conditions))

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    query_stmt = (
        base_stmt
        .options(
            selectinload(NewsTask.monitor),
            selectinload(NewsTask.creator),
        )
        .offset(skip)
        .limit(limit)
        .order_by(NewsTask.created_at.desc())
    )
    result = await db.execute(query_stmt)
    tasks = list(result.scalars().all())
    return tasks, total


async def get_tasks_by_strategy(
    db: AsyncSession, strategy_id: int, phase: str | None = None
) -> list[NewsTask]:
    stmt = select(NewsTask).where(NewsTask.strategy_id == strategy_id)
    if phase:
        stmt = stmt.where(NewsTask.phase == phase)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_task(db: AsyncSession, task_data: dict) -> NewsTask:
    task = NewsTask(**task_data)
    db.add(task)
    await db.flush()
    return task


async def update_task_status(
    db: AsyncSession,
    task: NewsTask,
    status: str,
    error_message: str | None = None,
) -> NewsTask:
    task.status = status
    if error_message is not None:
        task.error_message = error_message
    await db.flush()
    await db.refresh(task)
    return task


async def delete_task(db: AsyncSession, task: NewsTask) -> None:
    await db.delete(task)
    await db.flush()


# ==================== NewsArticle CRUD ====================


async def get_article_by_id(
    db: AsyncSession, article_id: int, load_relations: bool = True
) -> NewsArticle | None:
    stmt = select(NewsArticle).where(NewsArticle.id == article_id)
    if load_relations:
        stmt = stmt.options(selectinload(NewsArticle.task))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_article_by_url(db: AsyncSession, url: str) -> NewsArticle | None:
    stmt = select(NewsArticle).where(NewsArticle.url == url)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_articles_by_task(
    db: AsyncSession,
    task_id: int,
    skip: int = 0,
    limit: int = 50,
    relevance: str | None = None,
    source_tier: str | None = None,
) -> tuple[list[NewsArticle], int]:
    conditions: list = [NewsArticle.task_id == task_id]
    if relevance:
        conditions.append(NewsArticle.relevance == relevance)
    if source_tier:
        conditions.append(NewsArticle.source_tier == source_tier)

    base_stmt = select(NewsArticle).where(and_(*conditions))

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    query_stmt = (
        base_stmt
        .offset(skip)
        .limit(limit)
        .order_by(NewsArticle.published_at.desc().nulls_last())
    )
    result = await db.execute(query_stmt)
    articles = list(result.scalars().all())
    return articles, total


async def create_article(db: AsyncSession, article_data: dict) -> NewsArticle:
    article = NewsArticle(**article_data)
    db.add(article)
    await db.flush()
    return article


async def bulk_create_articles(
    db: AsyncSession, articles_data: list[dict]
) -> list[NewsArticle]:
    """批量创建文章，返回创建的文章列表。每篇文章绑定 task_id，URL 在同一任务内不重复即可。"""
    if not articles_data:
        return []
    articles = []
    for data in articles_data:
        article = NewsArticle(**data)
        db.add(article)
        articles.append(article)
    await db.flush()
    return articles


async def update_article(
    db: AsyncSession, article: NewsArticle, update_data: dict
) -> NewsArticle:
    for key, value in update_data.items():
        setattr(article, key, value)
    await db.flush()
    return article


async def get_articles_by_urls(
    db: AsyncSession, urls: list[str]
) -> list[NewsArticle]:
    """按 URL 列表批量查询已存在的文章（用于去重）"""
    if not urls:
        return []
    stmt = select(NewsArticle).where(NewsArticle.url.in_(urls))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_articles_by_monitor(
    db: AsyncSession,
    monitor_id: int,
    phase: str = "collect",
) -> list[NewsArticle]:
    """查询 monitor 下所有指定阶段任务关联的文章（用于跨任务聚合）"""
    stmt = (
        select(NewsArticle)
        .join(NewsTask, NewsArticle.task_id == NewsTask.id)
        .where(
            NewsTask.monitor_id == monitor_id,
            NewsTask.phase == phase,
            NewsTask.status == "completed",
        )
        .order_by(NewsArticle.published_at.desc().nulls_last())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
