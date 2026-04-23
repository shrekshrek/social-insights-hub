"""Agent API 业务逻辑"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from src.social_media.tasks.models import SocialTask
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
    # 返回 pending 任务（探测任务和全量采集任务均通过 pending 状态下发）
    stmt = (
        select(SocialTask)
        .where(
            and_(
                SocialTask.data_source == "remote_crawler",
                SocialTask.status == "pending",
                SocialTask.is_deleted.is_(False),
            )
        )
        .order_by(SocialTask.priority.desc(), SocialTask.created_at.asc())
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
            status=task.status,
        )
        for task in tasks
    ]


async def get_task_detail(
    db: AsyncSession,
    task_id: int,
) -> AgentTaskInfo:
    """查询任务详情（供爬虫轮询状态和获取续采参数）"""
    stmt = select(SocialTask).where(
        and_(SocialTask.id == task_id, SocialTask.is_deleted.is_(False))
    )
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    return AgentTaskInfo(
        task_id=task.id,
        task_name=task.name,
        platform=task.platform.code if task.platform else "unknown",
        task_type=task.task_type,
        priority=task.priority,
        keywords=task.keywords,
        task_params=task.task_params,
        created_at=task.created_at,
        status=task.status,
    )


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
        update(SocialTask)
        .where(
            and_(
                SocialTask.id == task_id,
                SocialTask.is_deleted.is_(False),
                SocialTask.status == "pending",
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
            "Task %s accepted by client: %s",
            task_id,
            request.client_id or "unknown",
        )
        return

    # 未抢占成功：查询当前状态给出幂等/冲突响应
    stmt = select(SocialTask.status).where(
        and_(SocialTask.id == task_id, SocialTask.is_deleted.is_(False))
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
    stmt = select(SocialTask).where(
        and_(
            SocialTask.id == task_id,
            SocialTask.is_deleted.is_(False),
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
        "Task %s progress updated: status=%s, crawled_count=%s",
        task_id,
        request.status,
        request.crawled_count,
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
    stmt = select(SocialTask).where(
        and_(
            SocialTask.id == task_id,
            SocialTask.is_deleted.is_(False),
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
                "message": (
                    f"Task status is {task.status}, "
                    "expected accepted, running or completed"
                ),
            },
        )

    # 单任务多阶段 + 聚合上传模型下：
    # - 每次 upload 都是 cloud_task_id 的"完整数据快照"（agent 已聚合多个本地 task 的 JSON）
    # - 已存在的 posts / comments 通过下面的 mapping 去重跳过，不会创建重复
    # - 真正有新数据时才会触发 INSERT 和 auto-analysis；无变化时整个流程是 no-op
    # 因此不再需要 "is_reupload 清空再插入" 的覆盖模式 —— 自然幂等。
    is_reupload = task.status == "completed"
    if is_reupload:
        logger.info(
            "Task %s: re-upload detected (status=completed); using upsert/dedup mode (no clear)",
            task_id,
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
        # 单任务多阶段模型：同一 task_id 在 probe / collect / comment 多个阶段被多次 upload。
        # 必须从 DB 加载已有原文映射，否则 collect 阶段重复 upload 同一笔记会创建重复记录。
        from src.social_media.tasks.models import SocialPost as _ExistingPost
        existing_posts_stmt = select(_ExistingPost.id, _ExistingPost.post_id_on_platform).where(
            _ExistingPost.task_id == task.id,
            _ExistingPost.is_deleted.is_(False),
        )
        existing_posts_result = await db.execute(existing_posts_stmt)
        existing_post_mapping: dict[str, int] = {
            row.post_id_on_platform: row.id for row in existing_posts_result.all()
        }
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
            if not platform_id:
                continue
            # 跳过已存在的原文（追加模式去重）
            if platform_id in existing_post_mapping:
                continue
            if platform_id not in posts_data_dict:
                posts_data_dict[platform_id] = transformed

        posts_data = list(posts_data_dict.values())

        created_posts = await task_crud.create_posts_bulk(
            db, task_id=task.id, platform_id=task.platform_id, posts_data=posts_data
        )

        # 创建 post_id 映射（平台ID -> 数据库ID），合并已有映射
        post_id_mapping = {**existing_post_mapping}
        for post in created_posts:
            post_id_mapping[post.post_id_on_platform] = post.id

        # 转换并导入评论数据（按 comment_id_on_platform 去重）
        # 与 posts 同理：从 DB 加载已有评论映射，重复 upload 同一评论时跳过创建。
        from src.social_media.tasks.models import SocialComment as _ExistingComment
        existing_comments_stmt = select(
            _ExistingComment.id,
            _ExistingComment.comment_id_on_platform,
        ).where(
            _ExistingComment.task_id == task.id,
            _ExistingComment.is_deleted.is_(False),
        )
        existing_comments_result = await db.execute(existing_comments_stmt)
        existing_comment_mapping: dict[str, int] = {
            row.comment_id_on_platform: row.id
            for row in existing_comments_result.all()
            if row.comment_id_on_platform
        }

        comments_raw = request.data.get("comments", [])
        comments_dict: dict[str, tuple[int, dict]] = {}

        for item in comments_raw:
            transformed = adapter.transform_comment(item)
            adapter.validate_comment(transformed)

            # 从适配器获取原文ID
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
            if not comment_platform_id:
                continue
            # 跳过已存在的评论（DB 历史 + 本次 batch 内部）
            if comment_platform_id in existing_comment_mapping:
                continue
            if comment_platform_id not in comments_dict:
                comments_dict[comment_platform_id] = (post_id, transformed)

        comments_to_create = list(comments_dict.values())

        created_comments = await task_crud.create_comments_bulk(
            db,
            task_id=task.id,
            platform_id=task.platform_id,
            comments_data=comments_to_create,
        )

        # 本次上传新增的数量（用于日志和返回值）
        posts_count = len(created_posts)
        comments_count = len(created_comments)

        # 更新任务统计：从 DB 实际查询累计总数（自愈，不会因覆写丢数）
        # 单任务多阶段模型下，同一 task_id 会经历 probe → collect 多次 upload，
        # 每次 upload 仅是增量；用 SQL count 得到的是历史累计真实总数。
        from sqlalchemy import select as _select, func as _func
        from src.social_media.tasks.models import (
            SocialPost as _SocialPost,
            SocialComment as _SocialComment,
        )
        total_posts_result = await db.execute(
            _select(_func.count(_SocialPost.id)).where(
                _SocialPost.task_id == task.id,
                _SocialPost.is_deleted.is_(False),
            )
        )
        total_comments_result = await db.execute(
            _select(_func.count(_SocialComment.id)).where(
                _SocialComment.task_id == task.id,
                _SocialComment.is_deleted.is_(False),
            )
        )
        total_posts = int(total_posts_result.scalar() or 0)
        total_comments = int(total_comments_result.scalar() or 0)

        await task_crud.update_task_counts(
            db, task, posts_count=total_posts, comments_count=total_comments
        )

        # 决定最终状态
        if request.error_message:
            # 任务执行失败：保留已采集数据，但标记为 failed
            final_status = "failed"
        elif task.phase == "probe" and not is_reupload:
            # 探测任务：上传完成后进入 probe_ready，等待策略审查
            final_status = "probe_ready"
        else:
            final_status = "completed"

        await task_crud.update_task_status(
            db, task, final_status,
            error_message=request.error_message if request.error_message else None,
        )

        await db.commit()

        logger.info(
            "Task %s result uploaded: posts=%s, comments=%s, status=%s",
            task_id,
            posts_count,
            comments_count,
            final_status,
        )

        # 如果启用了自动分析，触发分析任务链（probe_ready 也需要分析以供审查）
        # 触发条件：本次新插入了 posts 或 comments 任意一种
        # —— 单任务多阶段 + 上传幂等化模型下，可能出现 "只补评论无新 post" 的场景
        # （例如 collect 阶段补抓 probe 漏掉的笔记评论），此时也应让分析重新跑
        new_posts_count = len(created_posts)
        new_comments_count = len(created_comments)
        if task.auto_analyze and (new_posts_count > 0 or new_comments_count > 0):
            from src.social_media.analysis.celery_tasks.auto_analysis_tasks import (
                run_auto_analysis,
            )

            # 获取任务创建者ID作为分析任务的用户ID
            user_id = task.user_id
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
                    logger.info(
                        "Task %s: Auto analysis triggered (new_posts=%s, new_comments=%s)",
                        task_id, new_posts_count, new_comments_count,
                    )
                else:
                    logger.info(
                        "Task %s: Auto analysis already triggered (lock exists), skip",
                        task_id,
                    )
            except Exception as e:
                # 锁失败不应阻断主流程：降级为直接触发（由 Celery 执行侧幂等锁兜底）
                logger.warning(
                    "Task %s: Failed to acquire auto analysis lock, fallback trigger: %s",
                    task_id,
                    e,
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

        logger.error("Task %s upload failed: %s", task_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import data: {str(e)}",
        )
