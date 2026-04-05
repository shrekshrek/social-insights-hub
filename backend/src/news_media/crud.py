"""新闻媒体 CRUD 操作"""

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.news_media.models import NewsArticle, NewsMonitor, NewsTask

_UPDATABLE_MONITOR_FIELDS = {"name", "description"}


def _escape_like(value: str) -> str:
    """转义 LIKE 通配符"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ==================== NewsMonitor CRUD ====================


async def get_monitor_by_id(
    db: AsyncSession, monitor_id: int, load_relations: bool = True
) -> NewsMonitor | None:
    stmt = select(NewsMonitor).where(NewsMonitor.id == monitor_id)
    if load_relations:
        stmt = stmt.options(
            selectinload(NewsMonitor.owner),
            selectinload(NewsMonitor.participants),
        )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_monitor_by_name(db: AsyncSession, name: str) -> NewsMonitor | None:
    stmt = select(NewsMonitor).where(NewsMonitor.name == name)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_monitors(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    owner_id: int | None = None,
    participant_id: int | None = None,
    search: str | None = None,
) -> tuple[list[NewsMonitor], int]:
    from src.auth.models import User

    conditions: list = []
    if owner_id is not None:
        conditions.append(NewsMonitor.owner_id == owner_id)
    if participant_id is not None:
        conditions.append(
            or_(
                NewsMonitor.owner_id == participant_id,
                NewsMonitor.participants.any(User.id == participant_id),
            )
        )
    if search:
        conditions.append(
            NewsMonitor.name.ilike(f"%{_escape_like(search)}%", escape="\\")
        )

    base_stmt = select(NewsMonitor)
    if conditions:
        base_stmt = base_stmt.where(and_(*conditions))

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    query_stmt = (
        base_stmt
        .options(
            selectinload(NewsMonitor.owner),
            selectinload(NewsMonitor.participants),
        )
        .offset(skip)
        .limit(limit)
        .order_by(NewsMonitor.created_at.desc())
    )
    result = await db.execute(query_stmt)
    monitors = list(result.scalars().all())
    return monitors, total


async def create_monitor(
    db: AsyncSession, monitor_data: dict, owner_id: int, participant_ids: list[int] | None = None
) -> NewsMonitor:
    monitor = NewsMonitor(**monitor_data, owner_id=owner_id)
    db.add(monitor)
    await db.flush()

    if participant_ids:
        from src.auth.models import User
        users = await db.execute(select(User).where(User.id.in_(participant_ids)))
        new_participants = users.scalars().all()
        existing_ids = {u.id for u in monitor.participants}
        for user in new_participants:
            if user.id not in existing_ids and user.id != owner_id:
                monitor.participants.append(user)

    return monitor


async def update_monitor(
    db: AsyncSession, monitor: NewsMonitor, update_data: dict
) -> NewsMonitor:
    for key, value in update_data.items():
        if key not in _UPDATABLE_MONITOR_FIELDS:
            continue
        setattr(monitor, key, value)
    await db.flush()
    await db.refresh(monitor)
    return monitor


async def delete_monitor(db: AsyncSession, monitor: NewsMonitor) -> None:
    await db.delete(monitor)
    await db.flush()


# ==================== NewsMonitor-Participant Relations ====================


async def add_participants_to_news_monitor(
    db: AsyncSession, monitor: NewsMonitor, user_ids: list[int]
) -> NewsMonitor:
    """为新闻监测项目添加参与者"""
    from src.auth.models import User

    users = await db.execute(select(User).where(User.id.in_(user_ids)))
    new_participants = users.scalars().all()
    existing_ids = {u.id for u in monitor.participants}
    for user in new_participants:
        if user.id not in existing_ids and user.id != monitor.owner_id:
            monitor.participants.append(user)
    await db.commit()
    await db.refresh(monitor, ["participants"])
    return monitor


async def remove_participant_from_news_monitor(
    db: AsyncSession, monitor: NewsMonitor, user_id: int
) -> NewsMonitor:
    """从新闻监测项目移除参与者"""
    monitor.participants = [u for u in monitor.participants if u.id != user_id]
    await db.commit()
    await db.refresh(monitor, ["participants"])
    return monitor


async def set_news_monitor_participants(
    db: AsyncSession, monitor: NewsMonitor, user_ids: list[int]
) -> NewsMonitor:
    """覆盖式设置新闻监测参与者（用于策略同步）"""
    from src.auth.models import User

    users = await db.execute(select(User).where(User.id.in_(user_ids)))
    new_participants = [u for u in users.scalars().all() if u.id != monitor.owner_id]
    monitor.participants = new_participants
    await db.flush()
    return monitor


async def check_news_monitor_access(
    db: AsyncSession, monitor_id: int, user_id: int
) -> bool:
    """检查用户是否有新闻监测项目访问权限（admin / owner / participant）"""
    from sqlalchemy.orm import selectinload
    from src.auth.models import User
    from src.rbac.models import UserRole
    from src.rbac.utils import is_admin_or_super_admin

    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.user_roles).selectinload(UserRole.role))
    )
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        return False
    if is_admin_or_super_admin(user):
        return True

    monitor = await get_monitor_by_id(db, monitor_id, load_relations=True)
    if not monitor:
        return False
    if monitor.owner_id == user_id:
        return True
    return user_id in {p.id for p in monitor.participants}


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
    conditions = [NewsArticle.task_id == task_id]
    if relevance:
        conditions.append(NewsArticle.relevance == relevance)
    if source_tier:
        conditions.append(NewsArticle.source_tier == source_tier)

    where_clause = and_(*conditions)

    count_stmt = select(func.count()).select_from(NewsArticle).where(where_clause)
    total = (await db.execute(count_stmt)).scalar() or 0

    query_stmt = (
        select(NewsArticle)
        .where(where_clause)
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
    articles = [NewsArticle(**data) for data in articles_data]
    db.add_all(articles)
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
    """查询 monitor 下所有指定阶段任务的文章（用于跨任务聚合）"""
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
