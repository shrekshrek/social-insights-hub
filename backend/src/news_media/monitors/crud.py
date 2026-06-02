"""新闻监测项目 CRUD 操作"""

from sqlalchemy import and_, func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.news_media.monitors.models import NewsMonitor

_UPDATABLE_MONITOR_FIELDS = {"name", "description"}


def _escape_like(value: str) -> str:
    """转义 LIKE 通配符"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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
    user_id: int | None = None,
    participant_id: int | None = None,
    search: str | None = None,
) -> tuple[list[NewsMonitor], int]:
    from src.auth.models import User

    conditions: list = []
    if user_id is not None:
        conditions.append(NewsMonitor.user_id == user_id)
    if participant_id is not None:
        conditions.append(
            or_(
                NewsMonitor.user_id == participant_id,
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
        base_stmt.options(
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
    db: AsyncSession,
    monitor_data: dict,
    user_id: int,
    participant_ids: list[int] | None = None,
) -> NewsMonitor:
    monitor = NewsMonitor(**monitor_data, user_id=user_id)
    db.add(monitor)
    await db.flush()

    if participant_ids:
        from src.news_media.monitors.models import news_monitor_participants

        for pid in participant_ids:
            if pid != user_id:
                await db.execute(
                    news_monitor_participants.insert().values(
                        monitor_id=monitor.id, user_id=pid
                    )
                )

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


async def add_participants_to_news_monitor(
    db: AsyncSession, monitor: NewsMonitor, user_ids: list[int]
) -> NewsMonitor:
    """为新闻监测项目添加参与者"""
    from src.auth.models import User

    users = await db.execute(select(User).where(User.id.in_(user_ids)))
    new_participants = users.scalars().all()
    existing_ids = {u.id for u in monitor.participants}
    for user in new_participants:
        if user.id not in existing_ids and user.id != monitor.user_id:
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
    new_participants = [u for u in users.scalars().all() if u.id != monitor.user_id]
    monitor.participants = new_participants
    await db.flush()
    return monitor


async def check_news_monitor_access(
    db: AsyncSession, monitor_id: int, user_id: int
) -> bool:
    """检查用户是否有新闻监测项目访问权限（admin / owner / participant）"""
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
    if monitor.user_id == user_id:
        return True
    return user_id in {p.id for p in monitor.participants}
