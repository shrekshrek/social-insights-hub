"""新闻媒体模块的依赖注入"""

from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.database import get_async_db
from src.news_media import crud
from src.news_media.models import NewsMonitor, NewsTask
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


async def validate_news_monitor_owner(
    monitor: NewsMonitor = Depends(validate_news_monitor_exists),
    current_user: User = Depends(get_current_user),
) -> NewsMonitor:
    """验证用户是否是新闻监测项目的所有者（或管理员）"""
    if is_admin_or_super_admin(current_user):
        return monitor
    if monitor.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the monitor owner or administrators can perform this action",
        )
    return monitor


async def validate_news_task_exists(
    task_id: Annotated[int, Path()],
    db: AsyncSession = Depends(get_async_db),
) -> NewsTask:
    """验证新闻任务是否存在"""
    task = await crud.get_task_by_id(db, task_id, load_relations=True)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"NewsTask with id {task_id} not found",
        )
    return task


async def validate_news_task_access(
    task: NewsTask = Depends(validate_news_task_exists),
    current_user: User = Depends(get_current_user),
) -> NewsTask:
    """验证用户是否有权限访问新闻任务（通过监测项目的 owner 判断）"""
    if is_admin_or_super_admin(current_user):
        return task
    if not task.monitor or task.monitor.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task",
        )
    return task
