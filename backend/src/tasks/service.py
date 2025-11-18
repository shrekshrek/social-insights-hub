"""社交媒体数据任务业务逻辑层"""

from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from . import crud
from .models import DataTask, SocialPost, SocialComment
from .schemas import (
    DataTaskCreate,
    DataTaskUpdate,
    JSONUploadData,
    SocialPostCreate,
    SocialCommentCreate
)


# ==================== DataTask Service ====================

async def create_task(
    db: AsyncSession,
    task_in: DataTaskCreate,
    current_user_id: int
) -> DataTask:
    """创建任务"""
    # 验证项目是否存在
    from src.projects import crud as social_crud
    project = await social_crud.get_project_by_id(db, task_in.project_id, load_relations=False)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with id {task_in.project_id} not found"
        )

    # 验证平台是否存在
    platform = await social_crud.get_platform_by_id(db, task_in.platform_id)
    if not platform:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Platform with id {task_in.platform_id} not found"
        )

    # 验证用户是否有项目访问权限
    has_access = await social_crud.check_project_access(db, task_in.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this project"
        )

    # 准备任务数据
    task_data = task_in.model_dump()

    # 创建任务
    task = await crud.create_task(db, task_data=task_data, creator_id=current_user_id)
    await db.commit()
    await db.refresh(task)

    return task


async def get_task(
    db: AsyncSession,
    task_id: int,
    current_user_id: int
) -> Optional[DataTask]:
    """获取任务详情"""
    task = await crud.get_task_by_id(db, task_id, load_relations=True)
    if not task:
        return None

    # 验证用户是否有项目访问权限
    from src.projects import crud as social_crud
    has_access = await social_crud.check_project_access(db, task.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task"
        )

    return task


async def get_tasks_list(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    project_id: Optional[int] = None,
    platform_id: Optional[int] = None,
    task_type: Optional[str] = None,
    status: Optional[str] = None,
    data_source: Optional[str] = None,
    creator_id: Optional[int] = None,
    search: Optional[str] = None,
    current_user_id: Optional[int] = None
) -> tuple[List[DataTask], int]:
    """获取任务列表（带过滤和分页）"""
    # 如果指定了project_id，验证访问权限
    if project_id is not None and current_user_id is not None:
        from src.projects import crud as social_crud
        has_access = await social_crud.check_project_access(db, project_id, current_user_id)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this project"
            )

    skip = (page - 1) * page_size
    return await crud.get_tasks(
        db,
        skip=skip,
        limit=page_size,
        project_id=project_id,
        platform_id=platform_id,
        task_type=task_type,
        status=status,
        data_source=data_source,
        creator_id=creator_id,
        search=search
    )


async def update_task(
    db: AsyncSession,
    task: DataTask,
    task_update: DataTaskUpdate
) -> DataTask:
    """更新任务"""
    update_data = task_update.model_dump(exclude_unset=True)
    updated_task = await crud.update_task(db, task, update_data)
    await db.commit()
    await db.refresh(updated_task)
    return updated_task


async def delete_task(
    db: AsyncSession,
    task: DataTask
) -> None:
    """删除任务（软删除）"""
    await crud.delete_task(db, task)
    await db.commit()


# ==================== JSON Upload Service ====================

async def process_json_upload(
    db: AsyncSession,
    task_id: int,
    upload_data: JSONUploadData,
    current_user_id: int
) -> dict:
    """处理JSON上传数据

    Args:
        task_id: 任务ID
        upload_data: 上传的数据
        current_user_id: 当前用户ID

    Returns:
        导入统计信息
    """
    # 1. 验证任务存在且有权限
    task = await get_task(db, task_id, current_user_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with id {task_id} not found"
        )

    # 2. 验证任务状态
    if task.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task status is '{task.status}', cannot upload data. Task must be in 'pending' status."
        )

    # 3. 验证数据源
    if task.data_source != "local_upload":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task data_source is '{task.data_source}', expected 'local_upload'"
        )

    try:
        # 4. 更新任务状态为running
        await crud.update_task_status(db, task, "running")
        task.started_at = datetime.now(timezone.utc)
        await db.flush()

        # 5. 导入原文数据
        posts_data = [post.model_dump() for post in upload_data.contents]
        created_posts = await crud.create_posts_bulk(
            db,
            task_id=task.id,
            platform_id=task.platform_id,
            posts_data=posts_data
        )

        # 6. 创建post_id映射（平台ID -> 数据库ID）
        post_id_mapping = {
            post.post_id_on_platform: post.id
            for post in created_posts
        }

        # 7. 导入评论数据
        comments_to_create = []
        for comment in upload_data.comments:
            comment_dict = comment.model_dump()

            # 查找对应的post（评论的raw_data中应包含post_id_on_platform）
            post_id_on_platform = comment_dict.get('raw_data', {}).get('post_id_on_platform')
            if not post_id_on_platform:
                # 如果raw_data中没有，尝试从第一个原文推断（简化处理）
                if created_posts:
                    post_id = created_posts[0].id
                else:
                    continue
            else:
                post_id = post_id_mapping.get(post_id_on_platform)
                if not post_id:
                    # 找不到对应的原文，跳过该评论
                    continue

            comments_to_create.append((post_id, comment_dict))

        created_comments = await crud.create_comments_bulk(
            db,
            task_id=task.id,
            platform_id=task.platform_id,
            comments_data=comments_to_create
        )

        # 8. 更新任务统计和状态
        await crud.update_task_counts(
            db,
            task,
            posts_count=len(created_posts),
            comments_count=len(created_comments)
        )
        await crud.update_task_status(db, task, "completed")

        # 9. 提交事务
        await db.commit()

        return {
            "task_id": task.id,
            "posts_imported": len(created_posts),
            "comments_imported": len(created_comments),
            "message": "Data imported successfully"
        }

    except Exception as e:
        # 回滚事务
        await db.rollback()

        # 更新任务状态为failed
        await crud.update_task_status(db, task, "failed", error_message=str(e))
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import data: {str(e)}"
        )


# ==================== Data Query Service ====================

async def get_task_posts(
    db: AsyncSession,
    task_id: int,
    page: int = 1,
    page_size: int = 20,
    current_user_id: int = None
) -> tuple[List[SocialPost], int]:
    """获取任务的原文列表"""
    # 验证任务访问权限
    task = await get_task(db, task_id, current_user_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with id {task_id} not found"
        )

    skip = (page - 1) * page_size
    return await crud.get_posts_by_task(db, task_id, skip=skip, limit=page_size)


async def get_task_comments(
    db: AsyncSession,
    task_id: int,
    page: int = 1,
    page_size: int = 50,
    current_user_id: int = None,
    post_id: int = None
) -> tuple[List[SocialComment], int]:
    """获取任务的评论列表，可选按原文ID筛选"""
    # 验证任务访问权限
    task = await get_task(db, task_id, current_user_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with id {task_id} not found"
        )

    skip = (page - 1) * page_size
    return await crud.get_comments_by_task(db, task_id, skip=skip, limit=page_size, post_id=post_id)


async def get_post_with_comments(
    db: AsyncSession,
    post_id: int,
    page: int = 1,
    page_size: int = 50,
    current_user_id: int = None
) -> tuple[SocialPost, List[SocialComment], int]:
    """获取原文及其评论"""
    # 获取原文
    post = await crud.get_post_by_id(db, post_id, load_comments=False)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id {post_id} not found"
        )

    # 验证任务访问权限
    task = await get_task(db, post.task_id, current_user_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this post"
        )

    # 获取评论列表
    skip = (page - 1) * page_size
    comments, total = await crud.get_comments_by_post(
        db,
        post_id,
        skip=skip,
        limit=page_size
    )

    return post, comments, total


async def query_cross_task_posts(
    db: AsyncSession,
    platform_id: int,
    post_id_on_platform: str,
    project_id: Optional[int] = None,
    current_user_id: int = None
) -> List[SocialPost]:
    """跨任务查询同一帖子的历史数据"""
    # 如果指定了project_id，验证访问权限
    if project_id is not None and current_user_id is not None:
        from src.projects import crud as social_crud
        has_access = await social_crud.check_project_access(db, project_id, current_user_id)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this project"
            )

    posts = await crud.get_posts_by_platform_post_id(
        db,
        platform_id=platform_id,
        post_id_on_platform=post_id_on_platform,
        project_id=project_id
    )

    return posts


async def clear_task_data(
    db: AsyncSession,
    task: DataTask
) -> DataTask:
    """
    清空任务的所有数据（软删除原文和评论），重置任务状态

    用于重新上传或重新采集数据
    """
    # 软删除该任务的所有原文
    await crud.soft_delete_task_posts(db, task.id)

    # 软删除该任务的所有评论
    await crud.soft_delete_task_comments(db, task.id)

    # 重置任务状态和计数
    task.status = "pending"
    task.posts_count = 0
    task.comments_count = 0
    task.started_at = None
    task.completed_at = None
    task.error_message = None

    await db.commit()
    await db.refresh(task)

    return task
