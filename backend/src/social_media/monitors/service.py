"""社交媒体模块的业务逻辑层"""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from . import crud
from .models import SocialMonitor, Platform
from .schemas import (
    SocialMonitorCreate,
    SocialMonitorUpdate,
    DeepAnalysisSettings,
    SocialQuickTaskCreate,
)

# Aliases for local use


# ==================== Platform Service ====================


async def get_all_platforms(db: AsyncSession) -> List[Platform]:
    """获取所有平台（不分页，用于下拉选择）"""
    platforms, _ = await crud.get_platforms(db, skip=0, limit=100)
    return platforms


async def get_platforms_paginated(
    db: AsyncSession, page: int = 1, page_size: int = 20
) -> tuple[List[Platform], int]:
    """获取平台列表（分页）"""
    skip = (page - 1) * page_size
    return await crud.get_platforms(db, skip=skip, limit=page_size)


# ==================== SocialMonitor Service ====================


async def create_social_monitor(
    db: AsyncSession, monitor_in: SocialMonitorCreate, current_user_id: int
) -> dict:
    """创建新项目（可选同时批量创建任务）"""
    # 检查项目名称是否已存在
    existing = await crud.get_monitor_by_name(db, monitor_in.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"SocialMonitor with name '{monitor_in.name}' already exists",
        )

    # 准备项目数据
    monitor_data = monitor_in.model_dump(exclude={"participant_ids", "quick_tasks"})

    # 创建项目
    monitor = await crud.create_monitor(
        db,
        monitor_data=monitor_data,
        owner_id=current_user_id,
        participant_ids=monitor_in.participant_ids,
    )

    # 如果提供了快速创建任务配置，批量创建任务
    created_tasks = []
    if monitor_in.quick_tasks:
        from src.social_media.tasks.crud import bulk_create_tasks

        # 验证平台ID是否存在
        for platform_id in monitor_in.quick_tasks.platform_ids:
            platform = await crud.get_platform_by_id(db, platform_id)
            if not platform:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Platform with id {platform_id} not found",
                )

        # 构建 task_params（爬虫高级选项）
        task_params = None
        if monitor_in.quick_tasks.data_source == "remote_crawler":
            task_params = {
                "max_notes_count": monitor_in.quick_tasks.max_notes_count,
                "enable_comments": 1 if monitor_in.quick_tasks.enable_comments else 0,
                "per_note_max_comments_count": monitor_in.quick_tasks.per_note_max_comments_count,
                "publish_time_type": monitor_in.quick_tasks.publish_time_type,
                "sort_type": monitor_in.quick_tasks.sort_type,
            }

        # 批量创建任务
        created_tasks = await bulk_create_tasks(
            db=db,
            monitor_id=monitor.id,
            platform_ids=monitor_in.quick_tasks.platform_ids,
            task_type=monitor_in.quick_tasks.task_type,
            data_source=monitor_in.quick_tasks.data_source,
            creator_id=current_user_id,
            keywords=monitor_in.quick_tasks.keywords,
            task_params=task_params,
            auto_analyze=(
                monitor_in.quick_tasks.auto_analyze
                if monitor_in.quick_tasks.data_source == "remote_crawler"
                else False
            ),
        )

        await db.commit()

    return {"monitor": monitor, "created_tasks": created_tasks}


async def create_social_monitor_batch_tasks(
    db: AsyncSession,
    monitor_id: int,
    quick_tasks: SocialQuickTaskCreate,
    current_user_id: int,
) -> List:
    """为已有项目批量创建任务"""
    from src.social_media.tasks.crud import bulk_create_tasks

    # 验证平台ID是否存在
    for platform_id in quick_tasks.platform_ids:
        platform = await crud.get_platform_by_id(db, platform_id)
        if not platform:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Platform with id {platform_id} not found",
            )

    # 构建 task_params（爬虫高级选项）
    task_params = None
    if quick_tasks.data_source == "remote_crawler":
        task_params = {
            "max_notes_count": quick_tasks.max_notes_count,
            "enable_comments": 1 if quick_tasks.enable_comments else 0,
            "per_note_max_comments_count": quick_tasks.per_note_max_comments_count,
            "publish_time_type": quick_tasks.publish_time_type,
            "sort_type": quick_tasks.sort_type,
        }

    created_tasks = await bulk_create_tasks(
        db=db,
        monitor_id=monitor_id,
        platform_ids=quick_tasks.platform_ids,
        task_type=quick_tasks.task_type,
        data_source=quick_tasks.data_source,
        creator_id=current_user_id,
        keywords=quick_tasks.keywords,
        task_params=task_params,
        auto_analyze=(
            quick_tasks.auto_analyze
            if quick_tasks.data_source == "remote_crawler"
            else False
        ),
    )

    await db.commit()
    return created_tasks


async def get_social_monitor(db: AsyncSession, monitor_id: int) -> Optional[SocialMonitor]:
    """获取项目详情"""
    return await crud.get_monitor_by_id(db, monitor_id, load_relations=True)


async def get_social_monitors_list(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    owner_id: Optional[int] = None,
    participant_id: Optional[int] = None,
    search: Optional[str] = None,
) -> tuple[List[SocialMonitor], int]:
    """获取项目列表（带过滤和分页）"""
    skip = (page - 1) * page_size
    return await crud.get_monitors(
        db,
        skip=skip,
        limit=page_size,
        owner_id=owner_id,
        participant_id=participant_id,
        search=search,
    )


async def update_social_monitor(
    db: AsyncSession, monitor: SocialMonitor, monitor_update: SocialMonitorUpdate
) -> SocialMonitor:
    """更新项目"""
    # 如果更新名称，检查新名称是否已被占用
    if monitor_update.name and monitor_update.name != monitor.name:
        existing = await crud.get_monitor_by_name(db, monitor_update.name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"SocialMonitor with name '{monitor_update.name}' already exists",
            )

    # 只更新提供的字段
    update_data = monitor_update.model_dump(exclude_unset=True)
    return await crud.update_monitor(db, monitor, update_data)


async def delete_social_monitor(db: AsyncSession, monitor: SocialMonitor) -> None:
    """删除项目，并清理策略中的关联引用"""
    monitor_id = monitor.id

    # 先清理策略表中 social_monitor_id 外键引用，再删除 SocialMonitor
    from src.strategies.models import Strategy

    stmt = select(Strategy).where(Strategy.social_monitor_id == monitor_id)
    result = await db.execute(stmt)
    for strat in result.scalars().all():
        strat.social_monitor_id = None
    await db.flush()

    await crud.delete_monitor(db, monitor)


# ==================== SocialMonitor-Participant Relations ====================


async def add_participants(
    db: AsyncSession, monitor: SocialMonitor, user_ids: List[int]
) -> SocialMonitor:
    """为项目添加参与者"""
    # TODO: 验证用户ID是否存在（需要导入User相关模块）
    return await crud.add_participants_to_monitor(db, monitor, user_ids)


async def remove_participant(
    db: AsyncSession, monitor: SocialMonitor, user_id: int
) -> SocialMonitor:
    """从项目移除参与者"""
    # 不能移除owner
    if user_id == monitor.owner_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove monitor owner from participants",
        )

    # 检查用户是否是参与者
    participant_ids = [p.id for p in monitor.participants]
    if user_id not in participant_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} is not a participant of this monitor",
        )

    return await crud.remove_participant_from_monitor(db, monitor, user_id)


# ==================== Deep Analysis Settings ====================


async def update_deep_analysis_settings(
    db: AsyncSession, monitor: SocialMonitor, settings: DeepAnalysisSettings
) -> SocialMonitor:
    """更新项目的深度分析阈值配置"""
    monitor.deep_analysis_settings = settings.model_dump(exclude_unset=True)
    await db.commit()
    await db.refresh(monitor)
    return monitor


async def get_deep_analysis_settings(monitor: SocialMonitor) -> Optional[dict]:
    """获取项目的深度分析阈值配置"""
    return monitor.deep_analysis_settings


# ==================== Task Comparison ====================


async def compare_tasks(
    db: AsyncSession,
    monitor_id: int,
    task_ids: List[int],
    current_user_id: int,
    compare_type: str = "posts",
) -> dict:
    """对比项目内多个任务的数据重合度"""
    from sqlalchemy.orm import selectinload
    from src.social_media.tasks.models import SocialTask, SocialPost, SocialComment
    from src.social_media.monitors import crud as monitor_crud

    # 1. 权限校验
    await monitor_crud.assert_monitor_access(db, monitor_id, current_user_id)

    # 2. 任务校验
    stmt = (
        select(SocialTask)
        .options(selectinload(SocialTask.platform))
        .where(SocialTask.id.in_(task_ids))
        .where(SocialTask.monitor_id == monitor_id)
        .where(SocialTask.is_deleted.is_(False))
    )
    result = await db.execute(stmt)
    tasks = list(result.scalars().all())

    if len(tasks) != len(task_ids):
        found_ids = {t.id for t in tasks}
        missing = set(task_ids) - found_ids
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tasks not found or not in monitor: {missing}",
        )

    # 校验是否同一平台（不同平台对比 post_id 无意义）
    platform_ids = {t.platform_id for t in tasks}
    if len(platform_ids) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot compare tasks from different platforms. Please select tasks from the same platform.",
        )

    # 3. 获取所有任务的原文ID (task_id, post_id_on_platform)
    posts_stmt = (
        select(SocialPost.task_id, SocialPost.post_id_on_platform)
        .where(SocialPost.task_id.in_(task_ids))
        .where(SocialPost.is_deleted.is_(False))
    )
    posts_result = await db.execute(posts_stmt)
    # 内存结构：task_id -> set(post_ids)
    task_posts: dict[int, set[str]] = {tid: set() for tid in task_ids}
    all_posts: set[str] = set()
    # 记录每个原文出现在哪些任务中，用于评论分析
    post_in_tasks: dict[str, set[int]] = {}

    for tid, pid in posts_result.all():
        task_posts[tid].add(pid)
        all_posts.add(pid)
        if pid not in post_in_tasks:
            post_in_tasks[pid] = set()
        post_in_tasks[pid].add(tid)

    # 4. 计算矩阵
    matrix = []
    task_map = {t.id: t for t in tasks}

    for tid_main in task_ids:
        main_set = task_posts[tid_main]
        overlaps = []
        # 计算该任务的独有原文（不与其他任何选定任务重合）
        # unique = main - union(others)
        others_union = set()
        for tid_other in task_ids:
            if tid_other != tid_main:
                others_union.update(task_posts[tid_other])
        unique_count = len(main_set - others_union)

        # 计算两两重合
        for tid_target in task_ids:
            if tid_main == tid_target:
                continue
            target_set = task_posts[tid_target]
            overlap_count = len(main_set & target_set)
            overlaps.append(
                {"target_task_id": tid_target, "overlap_count": overlap_count}
            )

        matrix.append(
            {
                "task_id": tid_main,
                "task_name": task_map[tid_main].name,
                "total_posts": len(main_set),
                "unique_posts": unique_count,
                "overlaps": overlaps,
            }
        )

    # 5. 概览统计
    total_posts_raw = sum(len(s) for s in task_posts.values())
    unique_posts_count = len(all_posts)
    # 重合原文：出现在 >= 2 个任务中的原文
    overlap_posts_set = {pid for pid, tids in post_in_tasks.items() if len(tids) >= 2}
    overlap_count = len(overlap_posts_set)
    overlap_rate = overlap_count / unique_posts_count if unique_posts_count > 0 else 0.0

    # 6. 评论互补分析（仅针对重合原文）
    comment_analysis = {
        "posts_involved": overlap_count,
        "total_comments_raw": 0,
        "unique_comments": 0,
        "overlap_rate": 0.0,
        "complementary_rate": 0.0,
    }

    if overlap_count > 0:
        # 查出这些重合原文在各任务中的评论 ID
        # 仅查询涉及重合原文的评论
        comments_stmt = (
            select(
                SocialComment.task_id,
                SocialComment.post_id,
                SocialComment.comment_id_on_platform,
                SocialPost.post_id_on_platform,
            )
            .join(SocialPost, SocialPost.id == SocialComment.post_id)
            .where(SocialComment.task_id.in_(task_ids))
            .where(SocialPost.post_id_on_platform.in_(overlap_posts_set))
            .where(SocialComment.is_deleted.is_(False))
        )
        comments_result = await db.execute(comments_stmt)

        # 统计
        # task_id -> set(comment_id) (仅限重合原文)
        task_comments: dict[int, set[str]] = {tid: set() for tid in task_ids}
        all_comments: set[str] = set()

        for tid, _, cid, pid in comments_result.all():
            # 组合键：为了更严谨，评论去重最好带上 post_id (虽然平台 cid 全局唯一，但带上更安全)
            # 这里简化为 cid，假设平台 cid 足够唯一
            task_comments[tid].add(cid)
            all_comments.add(cid)

        total_comments_raw = sum(len(s) for s in task_comments.values())
        unique_comments_count = len(all_comments)

        # 评论重合率：(Raw - Unique) / Raw (衡量冗余度)
        # 或者：(Raw - Unique) / Unique ?
        # 这里定义 Overlap Rate = 1 - (Unique / Raw)，即冗余比例
        comments_overlap_rate = (
            1.0 - (unique_comments_count / total_comments_raw)
            if total_comments_raw > 0
            else 0.0
        )

        # 互补率：(Unique - Max_Single_Task) / Unique
        # 衡量多任务合并后比单任务增加了多少信息量
        max_single = max(len(s) for s in task_comments.values()) if task_comments else 0
        complementary_rate = (
            (unique_comments_count - max_single) / unique_comments_count
            if unique_comments_count > 0
            else 0.0
        )

        comment_analysis.update(
            {
                "total_comments_raw": total_comments_raw,
                "unique_comments": unique_comments_count,
                "overlap_rate": round(comments_overlap_rate, 4),
                "complementary_rate": round(complementary_rate, 4),
            }
        )

    return {
        "overview": {
            "total_posts_raw": total_posts_raw,
            "unique_posts": unique_posts_count,
            "overlap_count": overlap_count,
            "overlap_rate": round(overlap_rate, 4),
        },
        "matrix": matrix,
        "comment_analysis": comment_analysis,
    }


# ==================== Backward-compatible aliases ====================

create_monitor = create_social_monitor
get_monitor = get_social_monitor
get_monitors_list = get_social_monitors_list
update_monitor = update_social_monitor
delete_monitor = delete_social_monitor
batch_create_tasks_for_monitor = create_social_monitor_batch_tasks
