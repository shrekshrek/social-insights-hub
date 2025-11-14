"""社交媒体数据任务依赖注入"""

from fastapi import Depends, HTTPException, status, Path
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from src.auth.models import User
from src.auth.dependencies import get_current_user
from src.database import get_async_db
from src.social_media import crud as social_crud
from . import crud
from .models import DataTask, SocialPost


async def validate_task_exists(
    task_id: Annotated[int, Path()],
    db: AsyncSession = Depends(get_async_db)
) -> DataTask:
    """验证任务是否存在"""
    task = await crud.get_task_by_id(db, task_id, load_relations=True)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with id {task_id} not found"
        )
    return task


async def validate_task_access(
    task: DataTask = Depends(validate_task_exists),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
) -> DataTask:
    """验证用户是否有任务访问权限（通过项目权限）"""
    # 检查用户是否有项目访问权限
    has_access = await social_crud.check_project_access(
        db,
        task.project_id,
        current_user.id
    )

    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task"
        )

    return task


async def validate_task_owner(
    task: DataTask = Depends(validate_task_exists),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
) -> DataTask:
    """验证用户是否是任务创建者或项目owner"""
    # 检查是否是任务创建者
    if task.creator_id == current_user.id:
        return task

    # 检查是否是项目owner
    project = await social_crud.get_project_by_id(db, task.project_id, load_relations=False)
    if project and project.owner_id == current_user.id:
        return task

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only task creator or project owner can perform this action"
    )


async def validate_post_exists(
    post_id: Annotated[int, Path()],
    db: AsyncSession = Depends(get_async_db)
) -> SocialPost:
    """验证原文是否存在"""
    post = await crud.get_post_by_id(db, post_id, load_comments=False)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id {post_id} not found"
        )
    return post


async def validate_post_access(
    post: SocialPost = Depends(validate_post_exists),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
) -> SocialPost:
    """验证用户是否有原文访问权限（通过任务的项目权限）"""
    # 获取任务
    task = await crud.get_task_by_id(db, post.task_id, load_relations=False)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    # 检查用户是否有项目访问权限
    has_access = await social_crud.check_project_access(
        db,
        task.project_id,
        current_user.id
    )

    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this post"
        )

    return post
