"""Agent API 业务逻辑"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from src.social_media.tasks.models import DataTask
from src.social_media.tasks.adapters import get_adapter
from src.social_media.tasks import crud as task_crud
from .schemas import (
    AgentTaskInfo,
    AcceptTaskRequest,
    ProgressUpdateRequest,
    UploadResultRequest,
    StoredCounts,
)

logger = logging.getLogger(__name__)


async def get_pending_tasks(
    db: AsyncSession,
    limit: int = 5,
) -> list[AgentTaskInfo]:
    """获取待执行任务列表

    Args:
        db: 数据库会话
        limit: 最大返回数量

    Returns:
        list[AgentTaskInfo]: 任务列表
    """
    stmt = (
        select(DataTask)
        .where(
            and_(
                DataTask.data_source == "remote_crawler",
                DataTask.status == "pending",
                DataTask.is_deleted.is_(False),
            )
        )
        .order_by(DataTask.priority.desc(), DataTask.created_at.asc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    tasks = result.scalars().all()

    return [
        AgentTaskInfo(
            task_id=task.id,
            task_name=task.name,
            platform=task.platform.code if task.platform else "unknown",
            task_type=task.task_type,
            priority=task.priority,
            keywords=task.keywords,
            task_params=task.task_params,
            created_at=task.created_at,
        )
        for task in tasks
    ]


async def accept_task(
    db: AsyncSession,
    task_id: int,
    request: AcceptTaskRequest,
) -> None:
    """接收任务

    Args:
        db: 数据库会话
        task_id: 任务ID
        request: 接收请求

    Raises:
        HTTPException: 任务不存在或状态不正确
    """
    stmt = select(DataTask).where(
        and_(
            DataTask.id == task_id,
            DataTask.is_deleted.is_(False),
        )
    )
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    # 幂等：已被接收的任务再次调用返回成功
    if task.status == "accepted":
        return

    if task.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "ok": False,
                "error_code": "TASK_ALREADY_ACCEPTED",
                "message": f"Task status is {task.status}, expected pending",
            },
        )

    # 更新任务状态
    task.status = "accepted"
    task.accepted_at = datetime.now(timezone.utc)
    if request.client_id:
        task.accepted_by = request.client_id

    await db.commit()
    logger.info(f"Task {task_id} accepted by client: {request.client_id or 'unknown'}")


async def update_progress(
    db: AsyncSession,
    task_id: int,
    request: ProgressUpdateRequest,
) -> None:
    """更新任务进度

    Args:
        db: 数据库会话
        task_id: 任务ID
        request: 进度更新请求

    Raises:
        HTTPException: 任务不存在
    """
    stmt = select(DataTask).where(
        and_(
            DataTask.id == task_id,
            DataTask.is_deleted.is_(False),
        )
    )
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    # 更新状态
    if request.status:
        task.status = request.status
        if request.status == "running" and not task.started_at:
            task.started_at = datetime.now(timezone.utc)
        elif request.status == "completed":
            task.completed_at = datetime.now(timezone.utc)
        elif request.status == "failed" and request.message:
            task.error_message = request.message

    # 更新进度
    if request.crawled_count is not None:
        task.crawled_count = request.crawled_count

    await db.commit()
    logger.info(
        f"Task {task_id} progress updated: status={request.status}, "
        f"crawled_count={request.crawled_count}"
    )


async def upload_result(
    db: AsyncSession,
    task_id: int,
    request: UploadResultRequest,
) -> StoredCounts:
    """上传任务结果

    Args:
        db: 数据库会话
        task_id: 任务ID
        request: 上传请求

    Returns:
        StoredCounts: 已存储数量

    Raises:
        HTTPException: 任务不存在或状态不正确
    """
    stmt = select(DataTask).where(
        and_(
            DataTask.id == task_id,
            DataTask.is_deleted.is_(False),
        )
    )
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    # 验证状态
    if task.status not in ("accepted", "running"):
        # 幂等：已完成的任务返回成功
        if task.status == "completed":
            return StoredCounts(posts=task.posts_count, comments=task.comments_count)

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "ok": False,
                "error_code": "INVALID_TASK_STATUS",
                "message": f"Task status is {task.status}, expected accepted or running",
            },
        )

    # 验证平台
    platform_code = task.platform.code if task.platform else None
    if platform_code and request.platform != platform_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "ok": False,
                "error_code": "PLATFORM_MISMATCH",
                "message": f"Platform mismatch: expected {platform_code}, got {request.platform}",
            },
        )

    # 获取适配器
    try:
        adapter = get_adapter(request.platform)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported platform: {request.platform}",
        )

    try:
        # 更新任务状态为 running
        task.status = "running"
        if not task.started_at:
            task.started_at = datetime.now(timezone.utc)
        await db.flush()

        # 转换并导入原文数据（按 post_id_on_platform 去重）
        contents = request.data.get("contents", [])
        posts_data_dict: dict[str, dict] = {}

        for item in contents:
            transformed = adapter.transform_post(item)
            adapter.validate_post(transformed)
            transformed = adapter.normalize_content(transformed)

            # 只有当 title 和 content 都为空时才跳过
            if not transformed.get("content") and not transformed.get("title"):
                continue

            platform_id = transformed.get("post_id_on_platform")
            if platform_id and platform_id not in posts_data_dict:
                posts_data_dict[platform_id] = transformed

        posts_data = list(posts_data_dict.values())

        created_posts = await task_crud.create_posts_bulk(
            db, task_id=task.id, platform_id=task.platform_id, posts_data=posts_data
        )

        # 创建 post_id 映射（平台ID -> 数据库ID）
        post_id_mapping = {post.post_id_on_platform: post.id for post in created_posts}

        # 转换并导入评论数据（按 comment_id_on_platform 去重）
        comments_raw = request.data.get("comments", [])
        comments_dict: dict[str, tuple[int, dict]] = {}

        for item in comments_raw:
            transformed = adapter.transform_comment(item)
            adapter.validate_comment(transformed)

            # 从适配器获取帖子ID
            post_id_on_platform = adapter.get_post_id_from_comment(transformed)

            if not post_id_on_platform:
                if created_posts:
                    post_id = created_posts[0].id
                else:
                    continue
            else:
                post_id = post_id_mapping.get(post_id_on_platform)
                if not post_id:
                    continue

            comment_platform_id = transformed.get("comment_id_on_platform")
            if comment_platform_id and comment_platform_id not in comments_dict:
                comments_dict[comment_platform_id] = (post_id, transformed)

        comments_to_create = list(comments_dict.values())

        created_comments = await task_crud.create_comments_bulk(
            db,
            task_id=task.id,
            platform_id=task.platform_id,
            comments_data=comments_to_create,
        )

        # 更新任务统计和状态
        posts_count = len(created_posts)
        comments_count = len(created_comments)

        await task_crud.update_task_counts(
            db, task, posts_count=posts_count, comments_count=comments_count
        )
        await task_crud.update_task_status(db, task, "completed")

        await db.commit()

        logger.info(
            f"Task {task_id} result uploaded: posts={posts_count}, comments={comments_count}"
        )

        # 如果启用了自动分析，触发分析任务链
        if task.auto_analyze and posts_count > 0:
            from src.social_media.analysis.celery_tasks.auto_analysis_tasks import (
                run_auto_analysis,
            )
            
            # 获取任务创建者ID作为分析任务的用户ID
            user_id = task.creator_id
            project_keywords = task.keywords or ""
            
            # 异步启动分析任务链
            run_auto_analysis.delay(
                task_id=task.id,
                user_id=user_id,
                project_keywords=project_keywords,
            )
            logger.info(f"Task {task_id}: Auto analysis triggered")

        return StoredCounts(posts=posts_count, comments=comments_count)

    except Exception as e:
        await db.rollback()
        await task_crud.update_task_status(db, task, "failed", error_message=str(e))
        await db.commit()

        logger.error(f"Task {task_id} upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import data: {str(e)}",
        )
