"""新闻监测项目依赖注入"""

from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.database import get_async_db
from src.news_media.monitors import crud
from src.news_media.monitors.models import NewsMonitor
from src.rbac.utils import is_admin_or_super_admin


async def validate_news_monitor_exists(
    monitor_id: Annotated[int, Path()],
    db: AsyncSession = Depends(get_async_db),
) -> NewsMonitor:
    """验证新闻监测项目是否存在"""
    monitor = await crud.get_monitor_by_id(db, monitor_id, load_relations=True)
    if not monitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"NewsMonitor with id {monitor_id} not found",
        )
    return monitor


async def validate_news_monitor_access(
    monitor: NewsMonitor = Depends(validate_news_monitor_exists),
    current_user: User = Depends(get_current_user),
) -> NewsMonitor:
    """验证用户是否有新闻监测项目访问权限（admin / owner / participant）"""
    if is_admin_or_super_admin(current_user):
        return monitor
    if monitor.user_id == current_user.id:
        return monitor
    if current_user.id in {p.id for p in monitor.participants}:
        return monitor
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You don't have access to this monitor. Only the monitor owner, participants, or administrators can access this monitor.",
    )


async def validate_news_monitor_owner(
    monitor: NewsMonitor = Depends(validate_news_monitor_exists),
    current_user: User = Depends(get_current_user),
) -> NewsMonitor:
    """验证用户是否是新闻监测项目的所有者（或管理员）"""
    if is_admin_or_super_admin(current_user):
        return monitor
    if monitor.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the monitor owner or administrators can perform this action",
        )
    return monitor
