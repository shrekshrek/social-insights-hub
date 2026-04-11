"""社交媒体数据任务业务逻辑层"""

from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from . import crud
from .models import SocialTask, SocialPost, SocialComment
from .schemas import SocialTaskCreate, SocialTaskUpdate, JSONUploadData
from .adapters import get_adapter

# Backward-compat aliases for local use
SocialTaskUpdate = SocialTaskUpdate


# ==================== SocialTask Service ====================


async def create_social_task(
    db: AsyncSession,
    monitor_id: int,
    task_in: SocialTaskCreate,
    current_user_id: int,
) -> SocialTask:
    """创建任务（monitor_id 由调用方从 URL 路径提取，不在 body 中）"""
    from src.social_media.monitors import crud as social_crud

    monitor = await social_crud.get_monitor_by_id(
        db, monitor_id, load_relations=False
    )
    if not monitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SocialMonitor with id {monitor_id} not found",
        )

    platform = await social_crud.get_platform_by_id(db, task_in.platform_id)
    if not platform:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Platform with id {task_in.platform_id} not found",
        )

    await social_crud.assert_monitor_access(db, monitor_id, current_user_id)

    task_data = task_in.model_dump()
    task_data["monitor_id"] = monitor_id

    task = await crud.create_task(db, task_data=task_data, user_id=current_user_id)
    await db.commit()
    await db.refresh(task)

    return task


async def get_social_task(
    db: AsyncSession, task_id: int, current_user_id: int
) -> Optional[SocialTask]:
    """获取任务详情"""
    task = await crud.get_task_by_id(db, task_id, load_relations=True)
    if not task:
        return None

    # 验证用户是否有项目访问权限
    from src.social_media.monitors import crud as social_crud

    await social_crud.assert_monitor_access(db, task.monitor_id, current_user_id, detail="You don't have access to this task")

    return task


async def get_social_tasks_list(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    monitor_id: Optional[int] = None,
    platform_id: Optional[int] = None,
    task_type: Optional[str] = None,
    status: Optional[str] = None,
    data_source: Optional[str] = None,
    user_id: Optional[int] = None,
    search: Optional[str] = None,
    current_user_id: Optional[int] = None,
    phase: Optional[str] = None,
) -> tuple[List[SocialTask], int]:
    """获取任务列表（带过滤和分页）"""
    # 如果指定了monitor_id，验证访问权限
    if monitor_id is not None and current_user_id is not None:
        from src.social_media.monitors import crud as social_crud

        await social_crud.assert_monitor_access(db, monitor_id, current_user_id)

    skip = (page - 1) * page_size
    return await crud.get_tasks(
        db,
        skip=skip,
        limit=page_size,
        monitor_id=monitor_id,
        platform_id=platform_id,
        task_type=task_type,
        status=status,
        data_source=data_source,
        user_id=user_id,
        search=search,
        phase=phase,
    )


async def update_social_task(
    db: AsyncSession, task: SocialTask, task_update: SocialTaskUpdate
) -> SocialTask:
    """更新任务"""
    update_data = task_update.model_dump(exclude_unset=True)
    updated_task = await crud.update_task(db, task, update_data)
    await db.commit()
    await db.refresh(updated_task)
    return updated_task


async def delete_social_task(db: AsyncSession, task: SocialTask) -> None:
    """删除任务（软删除）"""
    await crud.delete_task(db, task)
    await db.commit()


# ==================== JSON Upload Service ====================


async def process_json_upload(
    db: AsyncSession, task_id: int, upload_data: JSONUploadData, current_user_id: int
) -> dict:
    """处理JSON上传数据

    使用平台适配器将原始数据转换为统一格式后存储。

    Args:
        task_id: 任务ID
        upload_data: 上传的数据（原始格式或已转换格式）
        current_user_id: 当前用户ID

    Returns:
        导入统计信息
    """
    # 1. 验证任务存在且有权限
    task = await get_task(db, task_id, current_user_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with id {task_id} not found",
        )

    # 2. 验证任务状态（允许 pending 和 completed 状态上传，completed 会覆盖现有数据）
    if task.status not in ("pending", "completed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task status is '{task.status}', cannot upload data. Task must be in 'pending' or 'completed' status.",
        )

    # 如果是 completed 状态，先清除现有数据
    is_reupload = task.status == "completed"
    if is_reupload:
        await crud.delete_task_posts_and_comments(db, task_id)
        # 同时清除分析结果
        task.analysis_result = None
        task.analysis_result_at = None
        await db.flush()

    # 3. 验证数据源
    if task.data_source != "local_upload":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task data_source is '{task.data_source}', expected 'local_upload'",
        )

    # 4. 获取平台适配器
    platform_code = task.platform.code if task.platform else None
    adapter = None
    if platform_code:
        try:
            adapter = get_adapter(platform_code)
        except ValueError:
            # 平台暂不支持适配器，使用原始数据
            pass

    try:
        # 5. 更新任务状态为running
        await crud.update_task_status(db, task, "running")
        task.started_at = datetime.now(timezone.utc)
        await db.flush()

        # 6. 转换并导入原文数据（按 post_id_on_platform 去重）
        posts_data_dict: dict[str, dict] = {}  # 用字典去重，key 是 post_id_on_platform
        for post in upload_data.contents:
            raw_data = post.model_dump()
            if adapter:
                # 使用适配器转换并验证
                transformed = adapter.transform_post(raw_data)
                adapter.validate_post(transformed)
                # 规范化内容字段
                transformed = adapter.normalize_content(transformed)
            else:
                # 直接使用原始数据（假设已是统一格式）
                transformed = raw_data
                # 基础验证：必须有 post_id_on_platform
                if not transformed.get("post_id_on_platform"):
                    raise ValueError(
                        f"Missing required field 'post_id_on_platform'. "
                        f"Platform '{platform_code}' has no adapter. "
                        f"Data keys: {list(raw_data.keys())[:10]}"
                    )
            # 只有当 title 和 content 都为空时才跳过
            if not transformed.get("content") and not transformed.get("title"):
                continue
            # 按 post_id_on_platform 去重（保留第一条）
            platform_id = transformed.get("post_id_on_platform")
            if platform_id and platform_id not in posts_data_dict:
                posts_data_dict[platform_id] = transformed

        posts_data = list(posts_data_dict.values())

        created_posts = await crud.create_posts_bulk(
            db, task_id=task.id, platform_id=task.platform_id, posts_data=posts_data
        )

        # 7. 创建post_id映射（平台ID -> 数据库ID）
        post_id_mapping = {post.post_id_on_platform: post.id for post in created_posts}

        # 8. 转换并导入评论数据（按 comment_id_on_platform 去重）
        comments_dict: dict[
            str, tuple[int, dict]
        ] = {}  # 用字典去重，key 是 comment_id_on_platform
        for comment in upload_data.comments:
            raw_data = comment.model_dump()
            if adapter:
                # 使用适配器转换并验证
                transformed = adapter.transform_comment(raw_data)
                adapter.validate_comment(transformed)
                # 从适配器获取原文ID
                post_id_on_platform = adapter.get_post_id_from_comment(transformed)
            else:
                # 直接使用原始数据（假设已是统一格式）
                transformed = raw_data
                # 基础验证：必须有 comment_id_on_platform
                if not transformed.get("comment_id_on_platform"):
                    raise ValueError(
                        f"Missing required field 'comment_id_on_platform'. "
                        f"Platform '{platform_code}' has no adapter. "
                        f"Data keys: {list(raw_data.keys())[:10]}"
                    )
                post_id_on_platform = transformed.get("raw_data", {}).get(
                    "post_id_on_platform"
                )

            # 查找对应的 post
            if not post_id_on_platform:
                # 如果没有原文ID，尝试从第一个原文推断（简化处理）
                if created_posts:
                    post_id = created_posts[0].id
                else:
                    continue
            else:
                post_id = post_id_mapping.get(post_id_on_platform)
                if not post_id:
                    # 找不到对应的原文，跳过该评论
                    continue

            # 按 comment_id_on_platform 去重（保留第一条）
            comment_platform_id = transformed.get("comment_id_on_platform")
            if comment_platform_id and comment_platform_id not in comments_dict:
                comments_dict[comment_platform_id] = (post_id, transformed)

        comments_to_create = list(comments_dict.values())

        created_comments = await crud.create_comments_bulk(
            db,
            task_id=task.id,
            platform_id=task.platform_id,
            comments_data=comments_to_create,
        )

        # 9. 更新任务统计和状态
        await crud.update_task_counts(
            db,
            task,
            posts_count=len(created_posts),
            comments_count=len(created_comments),
        )
        await crud.update_task_status(db, task, "completed")

        # 10. 提交事务
        await db.commit()

        return {
            "task_id": task.id,
            "posts_imported": len(created_posts),
            "comments_imported": len(created_comments),
            "message": "Data imported successfully",
        }

    except Exception as e:
        # 回滚事务
        await db.rollback()

        # 更新任务状态为failed
        await crud.update_task_status(db, task, "failed", error_message=str(e))
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import data: {str(e)}",
        )


# ==================== Data Query Service ====================


async def get_task_posts(
    db: AsyncSession,
    task_id: int,
    page: int = 1,
    page_size: int = 20,
    current_user_id: int = None,
    post_id: int = None,
) -> tuple[List[dict], int]:
    """获取任务的原文列表（包含已爬取评论数）

    Args:
        db: 数据库会话
        task_id: 任务ID
        page: 页码
        page_size: 每页数量
        current_user_id: 当前用户ID（用于权限验证）
        post_id: 可选，按原文ID精确筛选
    """
    # 验证任务访问权限
    task = await get_task(db, task_id, current_user_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with id {task_id} not found",
        )

    skip = (page - 1) * page_size
    return await crud.get_posts_by_task(
        db, task_id, skip=skip, limit=page_size, post_id=post_id
    )


async def get_task_comments(
    db: AsyncSession,
    task_id: int,
    page: int = 1,
    page_size: int = 50,
    current_user_id: int = None,
    post_id: int = None,
) -> tuple[List[SocialComment], int]:
    """获取任务的评论列表，可选按原文ID筛选"""
    # 验证任务访问权限
    task = await get_task(db, task_id, current_user_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with id {task_id} not found",
        )

    skip = (page - 1) * page_size
    return await crud.get_comments_by_task(
        db, task_id, skip=skip, limit=page_size, post_id=post_id
    )


async def get_post_with_comments(
    db: AsyncSession,
    post_id: int,
    page: int = 1,
    page_size: int = 50,
    current_user_id: int = None,
) -> tuple[SocialPost, List[SocialComment], int]:
    """获取原文及其评论"""
    # 获取原文
    post = await crud.get_post_by_id(db, post_id, load_comments=False)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id {post_id} not found",
        )

    # 验证任务访问权限
    task = await get_task(db, post.task_id, current_user_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this post",
        )

    # 获取评论列表
    skip = (page - 1) * page_size
    comments, total = await crud.get_comments_by_post(
        db, post_id, skip=skip, limit=page_size
    )

    return post, comments, total


async def query_cross_task_posts(
    db: AsyncSession,
    platform_id: int,
    post_id_on_platform: str,
    monitor_id: Optional[int] = None,
    current_user_id: int = None,
) -> List[SocialPost]:
    """跨任务查询同一原文的历史数据"""
    # 如果指定了monitor_id，验证访问权限
    if monitor_id is not None and current_user_id is not None:
        from src.social_media.monitors import crud as social_crud

        await social_crud.assert_monitor_access(db, monitor_id, current_user_id)

    posts = await crud.get_posts_by_platform_post_id(
        db,
        platform_id=platform_id,
        post_id_on_platform=post_id_on_platform,
        monitor_id=monitor_id,
    )

    return posts


async def clear_task_data(db: AsyncSession, task: SocialTask) -> SocialTask:
    """
    清空任务的所有数据（软删除原文和评论），重置任务状态

    用于重新上传或重新采集数据
    """
    from sqlalchemy import delete
    from src.social_media.analysis.models import PostAnalysis

    # 先删除分析结果（因为原文是软删除，CASCADE 不会触发）
    await db.execute(delete(PostAnalysis).where(PostAnalysis.task_id == task.id))

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
    # 清空聚合分析报告
    task.analysis_result = None
    task.analysis_result_at = None

    await db.commit()
    await db.refresh(task)

    return task


# ==================== Backward-compatible aliases ====================

create_task = create_social_task
get_task = get_social_task
get_tasks_list = get_social_tasks_list
update_task = update_social_task
delete_task = delete_social_task
