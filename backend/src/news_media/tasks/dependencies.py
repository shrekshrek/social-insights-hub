"""新闻任务依赖注入"""

from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.database import get_async_db
from src.news_media.tasks import crud
from src.news_media.tasks.models import NewsTask
from src.rbac.utils import is_admin_or_super_admin


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
    """验证用户是否有权限访问新闻任务（通过监测项目的 owner/participant 判断）"""
    if is_admin_or_super_admin(current_user):
        return task
    if not task.monitor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task",
        )
    if task.monitor.owner_id == current_user.id:
        return task
    if current_user.id in {p.id for p in task.monitor.participants}:
        return task
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You don't have access to this task",
    )
