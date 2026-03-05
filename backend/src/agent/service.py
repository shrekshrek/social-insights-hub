"""Agent API 业务逻辑"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, and_, update
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
    # 原子抢占：仅当任务仍为 pending 时才能成功更新为 accepted
    accepted_at = datetime.now(timezone.utc)
    upd = (
        update(DataTask)
        .where(
            and_(
                DataTask.id == task_id,
                DataTask.is_deleted.is_(False),
                DataTask.status == "pending",
            )
        )
        .values(
            status="accepted",
            accepted_at=accepted_at,
            accepted_by=request.client_id,
        )
    )
    result = await db.execute(upd)
    if result.rowcount and result.rowcount > 0:
        await db.commit()
        logger.info(
            f"Task {task_id} accepted by client: {request.client_id or 'unknown'}"
        )
        return

    # 未抢占成功：查询当前状态给出幂等/冲突响应
    stmt = select(DataTask.status).where(
        and_(DataTask.id == task_id, DataTask.is_deleted.is_(False))
    )
    status_result = await db.execute(stmt)
    current_status = status_result.scalar_one_or_none()

    if current_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )

    # 幂等：已被接收则直接返回成功
    if current_status == "accepted":
        return

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "ok": False,
            "error_code": "TASK_ALREADY_ACCEPTED",
            "message": f"Task status is {current_status}, expected pending",
        },
    )


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
    if task.status not in ("accepted", "running", "completed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "ok": False,
                "error_code": "INVALID_TASK_STATUS",
                "message": f"Task status is {task.status}, expected accepted, running or completed",
            },
        )

    # 如果是已完成的任务，先清空现有数据（覆盖模式）
    is_reupload = task.status == "completed"
    if is_reupload:
        logger.info(f"Task {task_id}: Re-uploading data, clearing existing data...")
        # 清理自动分析幂等锁（避免锁残留阻断后续自动分析）
        try:
            import redis.asyncio as redis
            from src.redis_client import redis_pool

            async with redis.Redis(connection_pool=redis_pool) as redis_client:
                await redis_client.delete(f"analysis:auto:{task_id}:triggered")
                await redis_client.delete(f"analysis:auto:{task_id}:running")
        except Exception as e:
            logger.warning(
                f"Task {task_id}: Failed to clear auto analysis lock: {e}",
                exc_info=True,
            )

        # 先撤销/终止旧的分析 Celery 任务，避免重传过程中旧任务继续写入
        try:
            from celery import current_app as celery_app  # type: ignore[import-not-found]
            from src.social_media.analysis.models import AnalysisJob

            jobs_stmt = select(AnalysisJob.celery_task_id).where(
                and_(
                    AnalysisJob.task_id == task_id,
                    AnalysisJob.status.in_(("pending", "processing")),
                )
            )
            jobs_result = await db.execute(jobs_stmt)
            celery_task_ids = [row[0] for row in jobs_result.all() if row and row[0]]
            for celery_task_id in celery_task_ids:
                celery_app.control.revoke(celery_task_id, terminate=True)
            if celery_task_ids:
                logger.info(
                    f"Task {task_id}: Revoked {len(celery_task_ids)} analysis celery tasks"
                )
        except Exception as e:
            # 撤销失败不应阻断重传；记录日志用于排查
            logger.warning(
                f"Task {task_id}: Failed to revoke previous analysis celery tasks: {e}",
                exc_info=True,
            )

        await task_crud.delete_task_posts_and_comments(db, task_id)
        # 重置任务统计与时间字段，避免沿用旧的 started_at / completed_at / counts
        task.posts_count = 0
        task.comments_count = 0
        task.crawled_count = 0
        task.started_at = None
        task.completed_at = None
        task.error_message = None
        # 清空聚合分析报告
        task.analysis_result = None
        task.analysis_result_at = None
        # 清空分析任务记录
        from sqlalchemy import delete
        from src.social_media.analysis.models import AnalysisJob

        await db.execute(delete(AnalysisJob).where(AnalysisJob.task_id == task_id))
        await db.flush()
        logger.info(f"Task {task_id}: Existing data cleared")

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
            monitor_keywords = task.keywords or ""

            # 幂等锁（触发侧）：避免同一 task 并发 upload_result 时重复触发
            # 注意：触发侧与执行侧使用不同 key，避免“已触发”阻断真正执行
            lock_key = f"analysis:auto:{task.id}:triggered"
            try:
                import redis.asyncio as redis
                from src.redis_client import redis_pool

                async with redis.Redis(connection_pool=redis_pool) as redis_client:
                    acquired = await redis_client.set(
                        lock_key, "triggered", nx=True, ex=7200
                    )
                if acquired:
                    run_auto_analysis.delay(
                        task_id=task.id,
                        user_id=user_id,
                        monitor_keywords=monitor_keywords,
                    )
                    logger.info(f"Task {task_id}: Auto analysis triggered")
                else:
                    logger.info(
                        f"Task {task_id}: Auto analysis already triggered (lock exists), skip"
                    )
            except Exception as e:
                # 锁失败不应阻断主流程：降级为直接触发（由 Celery 执行侧幂等锁兜底）
                logger.warning(
                    f"Task {task_id}: Failed to acquire auto analysis lock, fallback trigger: {e}",
                    exc_info=True,
                )
                run_auto_analysis.delay(
                    task_id=task.id,
                    user_id=user_id,
                    monitor_keywords=monitor_keywords,
                )

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
