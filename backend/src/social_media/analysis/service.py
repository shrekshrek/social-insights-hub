"""分析模块业务逻辑层

使用统一的 AnalysisJob 模型，通过 task_id 是否为空区分任务级/项目级分析。
"""

from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from .models import PostAnalysis, AnalysisJob, ProjectAnalysisSnapshot
from .jobs import create_analysis_job_async
from .schemas import (
    RunScreeningRequest,
    RunDeepAnalysisRequest,
    RunAnalysisResponse,
    AnalysisStatsResponse,
)

from .project_snapshot import build_project_snapshot_result


# ==================== Task-Level Analysis ====================


async def run_post_screening(
    db: AsyncSession, request: RunScreeningRequest, current_user_id: int
) -> RunAnalysisResponse:
    """运行帖子AI初筛分析"""
    from src.social_media.tasks import crud as task_crud
    from src.social_media.projects import crud as project_crud
    from .celery_tasks.screening_tasks import run_screening_task

    # 验证任务是否存在
    task = await task_crud.get_task_by_id(db, request.task_id, load_relations=False)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {request.task_id} not found",
        )

    # 验证用户权限
    has_access = await project_crud.check_project_access(
        db, task.project_id, current_user_id
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task",
        )

    # 获取要分析的帖子ID列表
    post_ids = request.post_ids or []

    if request.analyze_all or not post_ids:
        # 获取任务下所有帖子ID（排除已有初筛结果的）
        from src.social_media.tasks.models import SocialPost

        stmt = (
            select(SocialPost.id)
            .outerjoin(PostAnalysis, PostAnalysis.post_id == SocialPost.id)
            .where(SocialPost.task_id == request.task_id)
            .where(SocialPost.is_deleted.is_(False))
            .where(PostAnalysis.spam_score.is_(None))  # 只选择尚未初筛的
        )
        result = await db.execute(stmt)
        post_ids = [row[0] for row in result.fetchall()]

    if not post_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有需要初筛的帖子（所有帖子已完成初筛）",
        )

    # 创建分析任务记录
    analysis_job = await create_analysis_job_async(
        db=db,
        project_id=task.project_id,
        task_id=request.task_id,
        user_id=current_user_id,
        analysis_type="screening_posts",
        source_count=len(post_ids),
    )

    # 获取项目关键词
    project_keywords = task.keywords or ""

    # 启动Celery任务
    celery_result = run_screening_task.delay(
        result_id=analysis_job.id,
        task_id=request.task_id,
        post_ids=post_ids,
        project_keywords=project_keywords,
    )

    # 更新celery_task_id
    analysis_job.celery_task_id = celery_result.id
    await db.commit()

    return RunAnalysisResponse(
        celery_task_id=celery_result.id,
        job_id=analysis_job.id,
        status="pending",
        message=f"帖子初筛任务已启动，共{len(post_ids)}条数据",
    )


async def run_post_deep_analysis(
    db: AsyncSession,
    request: RunDeepAnalysisRequest,
    current_user_id: int,
    spam_max: float | None = None,
    value_min: float | None = None,
    relevance_min: float | None = None,
) -> RunAnalysisResponse:
    """运行帖子深度分析"""
    from src.social_media.tasks import crud as task_crud
    from src.social_media.projects import crud as project_crud
    from .celery_tasks.deep_analysis_tasks import run_post_deep_task

    # 验证任务和权限
    task = await task_crud.get_task_by_id(db, request.task_id, load_relations=False)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {request.task_id} not found",
        )

    has_access = await project_crud.check_project_access(
        db, task.project_id, current_user_id
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task",
        )

    # 获取要分析的帖子ID列表
    post_ids = request.post_ids or []

    if not post_ids:
        # 基于阈值筛选候选帖子
        preview = await preview_deep_analysis_candidates(
            db,
            request.task_id,
            current_user_id,
            spam_max=spam_max,
            value_min=value_min,
            relevance_min=relevance_min,
        )
        post_ids = preview["deep_candidate_ids"]

    if not post_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有符合条件的帖子需要原文深度分析（请先完成初筛或调整阈值）",
        )

    # 创建分析任务记录
    analysis_job = await create_analysis_job_async(
        db=db,
        project_id=task.project_id,
        task_id=request.task_id,
        user_id=current_user_id,
        analysis_type="deep_posts",
        source_count=len(post_ids),
        analysis_config={
            "spam_max": spam_max,
            "value_min": value_min,
            "relevance_min": relevance_min,
        }
        if any([spam_max, value_min, relevance_min])
        else None,
    )

    # 启动Celery任务
    celery_result = run_post_deep_task.delay(
        result_id=analysis_job.id,
        task_id=request.task_id,
        post_ids=post_ids,
        analysis_focus=request.analysis_focus,
    )

    # 更新celery_task_id
    analysis_job.celery_task_id = celery_result.id
    await db.commit()

    return RunAnalysisResponse(
        celery_task_id=celery_result.id,
        job_id=analysis_job.id,
        status="pending",
        message=f"帖子深度分析任务已启动，共{len(post_ids)}条数据",
    )


# ==================== Project Snapshot (Manual) ====================


async def create_project_snapshot(
    db: AsyncSession,
    project_id: int,
    task_ids: list[int],
    current_user_id: int,
    name: str | None = None,
    subject: str | None = None,
    competitors: list[str] | None = None,
    platform_weights: dict[str, float] | None = None,
) -> ProjectAnalysisSnapshot:
    """手动生成项目级合并分析快照（同步完成，写入 project_analysis_snapshots 表）。"""
    from src.social_media.projects import crud as project_crud
    from src.social_media.tasks.models import DataTask

    # 权限校验
    has_access = await project_crud.check_project_access(
        db, project_id, current_user_id
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this project",
        )

    # 任务校验：必须属于该项目且未删除
    if not task_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="task_ids is required"
        )

    stmt = (
        select(DataTask)
        .options(selectinload(DataTask.platform))
        .where(DataTask.id.in_(task_ids))
        .where(DataTask.project_id == project_id)
        .where(DataTask.is_deleted.is_(False))
    )
    result = await db.execute(stmt)
    tasks = list(result.scalars().all())

    found_ids = {t.id for t in tasks}
    missing = [tid for tid in task_ids if tid not in found_ids]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Some tasks not found in this project: {missing}",
        )

    # 必须已有任务级聚合结果
    rich_task_data: list[dict[str, Any]] = []
    missing_agg_opinions: list[int] = []
    missing_agg_entities: list[int] = []
    for t in tasks:
        if not t.analysis_result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Task {t.id} has no analysis_result. Please run task aggregation first.",
            )

        # 规范口径：项目快照只认 canonical 字段 aggregated_*（不使用 insights 兜底）
        ar = t.analysis_result or {}
        if not isinstance(ar.get("aggregated_opinions"), list):
            missing_agg_opinions.append(t.id)
        if not isinstance(ar.get("aggregated_entities"), list):
            missing_agg_entities.append(t.id)

        # 关键词展示优先使用聚合结果里记录的 keywords（通常是 list[str]）
        keywords_val = ((t.analysis_result or {}).get("meta") or {}).get("keywords")
        if isinstance(keywords_val, list) and keywords_val:
            keyword_label = " / ".join([str(x) for x in keywords_val if x])
        else:
            keyword_label = t.keywords or ""
        rich_task_data.append(
            {
                "task_id": t.id,
                "platform": t.platform.code if t.platform else "unknown",
                "keyword": keyword_label,
                "posts_count": int(getattr(t, "posts_count", 0) or 0),
                "analysis_result": t.analysis_result,
            }
        )

    if missing_agg_opinions or missing_agg_entities:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Some tasks have incompatible analysis_result schema (missing canonical aggregated_* fields). "
                "Please re-run task aggregation for these tasks, then re-generate the project snapshot.",
                "missing_aggregated_opinions_task_ids": missing_agg_opinions,
                "missing_aggregated_entities_task_ids": missing_agg_entities,
            },
        )

    # Step0 辅助：为项目级去重/权重/新鲜度准备帖子映射（platform+post_id_on_platform）
    # 说明：项目级聚合的“去重口径”基于 SocialPost 的平台帖ID，而不是任务内自增ID
    from src.social_media.tasks.models import SocialPost
    from src.social_media.projects.models import Platform
    from src.social_media.analysis.celery_tasks.aggregation.metrics import calculate_cii

    posts_stmt = (
        select(
            SocialPost.id,
            SocialPost.post_id_on_platform,
            SocialPost.published_at,
            SocialPost.likes_count,
            SocialPost.comments_count,
            SocialPost.shares_count,
            SocialPost.collected_count,
            Platform.code,
        )
        .join(Platform, Platform.id == SocialPost.platform_id)
        .where(SocialPost.task_id.in_(task_ids))
        .where(SocialPost.is_deleted.is_(False))
    )
    posts_rows = (await db.execute(posts_stmt)).all()

    post_key_by_id: dict[int, str] = {}
    post_info_by_key: dict[str, dict[str, Any]] = {}
    # 为 keyword 分布提供一个稳定“主归属”（首见原则）
    primary_keyword_by_key: dict[str, str] = {}
    primary_task_by_key: dict[str, int] = {}

    # 先构造 task_id -> keyword_label 的映射（用于首见原则）
    task_keyword_label: dict[int, str] = {}
    for t in rich_task_data:
        try:
            tid = int(t.get("task_id"))
        except Exception:
            continue
        task_keyword_label[tid] = str(t.get("keyword") or "")

    for row in posts_rows:
        try:
            pid = int(row[0])
        except Exception:
            continue
        post_id_on_platform = str(row[1] or "")
        platform_code = str(row[7] or "unknown")
        if not post_id_on_platform:
            # 极端兜底：没有平台帖ID时，退化为内部ID
            post_id_on_platform = str(pid)

        post_key = f"{platform_code}:{post_id_on_platform}"
        post_key_by_id[pid] = post_key

        # 只保留第一条（跨任务重复贴：platform+post_id_on_platform 会相同）
        if post_key not in post_info_by_key:
            likes = int(row[3] or 0)
            comments = int(row[4] or 0)
            shares = int(row[5] or 0)
            collected = int(row[6] or 0)
            raw_cii = float(
                calculate_cii(
                    likes=likes, comments=comments, shares=shares, collected=collected
                )
            )
            post_info_by_key[post_key] = {
                "platform": platform_code,
                "post_id_on_platform": post_id_on_platform,
                "published_at": row[2],
                "raw_cii": raw_cii,
            }

        # 主归属（首见原则）——用于 keyword 分布在去重后仍能“总和=总量”
        if post_key not in primary_keyword_by_key:
            # row 没有 task_id，因此无法直接判定；这里先留空，后续由 build_project_snapshot_result 按任务维度补齐
            primary_keyword_by_key[post_key] = ""
        if post_key not in primary_task_by_key:
            primary_task_by_key[post_key] = 0

    snapshot_result = build_project_snapshot_result(
        project_id=project_id,
        included_task_ids=task_ids,
        task_data_list=rich_task_data,
        subject=subject,
        competitors=competitors,
        platform_weights=platform_weights,
        post_key_by_id=post_key_by_id,
        post_info_by_key=post_info_by_key,
        primary_keyword_by_key=primary_keyword_by_key,
        primary_task_by_key=primary_task_by_key,
    )

    snapshot = ProjectAnalysisSnapshot(
        name=name,
        project_id=project_id,
        user_id=current_user_id,
        included_task_ids=task_ids,
        result_data=snapshot_result,
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    return snapshot


async def run_comment_deep_analysis(
    db: AsyncSession,
    request: RunDeepAnalysisRequest,
    current_user_id: int,
    spam_max: float | None = None,
    value_min: float | None = None,
    relevance_min: float | None = None,
) -> RunAnalysisResponse:
    """运行评论深度分析"""
    from src.social_media.tasks import crud as task_crud
    from src.social_media.projects import crud as project_crud
    from .celery_tasks.deep_analysis_tasks import run_comment_deep_task

    # 验证任务和权限
    task = await task_crud.get_task_by_id(db, request.task_id, load_relations=False)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {request.task_id} not found",
        )

    has_access = await project_crud.check_project_access(
        db, task.project_id, current_user_id
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task",
        )

    # 获取要分析的帖子ID列表（因为评论分析是基于帖子的）
    post_ids = request.post_ids or []

    if not post_ids:
        # 基于阈值筛选候选帖子
        preview = await preview_deep_analysis_candidates(
            db,
            request.task_id,
            current_user_id,
            spam_max=spam_max,
            value_min=value_min,
            relevance_min=relevance_min,
        )
        post_ids = preview["comment_candidate_ids"]

    if not post_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有符合条件的帖子需要评论深度分析（需先完成原文深度分析且有评论）",
        )

    # 创建分析任务记录
    analysis_job = await create_analysis_job_async(
        db=db,
        project_id=task.project_id,
        task_id=request.task_id,
        user_id=current_user_id,
        analysis_type="deep_comments",
        source_count=len(post_ids),
        analysis_config={
            "spam_max": spam_max,
            "value_min": value_min,
            "relevance_min": relevance_min,
        }
        if any([spam_max, value_min, relevance_min])
        else None,
    )

    # 启动Celery任务
    celery_result = run_comment_deep_task.delay(
        result_id=analysis_job.id,
        task_id=request.task_id,
        post_ids=post_ids,
        analysis_focus=request.analysis_focus,
    )

    # 更新celery_task_id
    analysis_job.celery_task_id = celery_result.id
    await db.commit()

    return RunAnalysisResponse(
        celery_task_id=celery_result.id,
        job_id=analysis_job.id,
        status="pending",
        message=f"评论深度分析任务已启动，将分析{len(post_ids)}个帖子的评论",
    )


# ==================== Post Analysis Query ====================


async def get_task_post_analyses(
    db: AsyncSession,
    task_id: int,
    current_user_id: int,
    page: int = 1,
    page_size: int = 20,
    filter_analyzed: bool = True,
    search_query: str | None = None,
    search_id: int | None = None,
    post_ids: list[int] | None = None,
) -> tuple[List[Dict[str, Any]], int]:
    """获取任务下所有帖子的分析结果（带分页和搜索）

    Args:
        task_id: 任务ID
        current_user_id: 当前用户ID
        page: 页码
        page_size: 每页数量
        filter_analyzed: 是否只返回已分析的帖子（默认True）
        search_query: 关键词搜索（搜索标题和内容）
        search_id: 按帖子分析ID精确搜索
        post_ids: 按帖子ID列表筛选

    Returns:
        (帖子分析列表, 总数)，每个帖子包含：
        - 帖子基本信息（id, title, content, author_name, published_at等）
        - 分析结果（spam_score, value_score, relevance_score, sentiment）
        - 深度分析结果（post_deep_result, comment_deep_result）
    """
    from src.social_media.tasks import crud as task_crud
    from src.social_media.projects import crud as project_crud
    from src.social_media.tasks.models import SocialPost

    # 验证任务是否存在
    task = await task_crud.get_task_by_id(db, task_id, load_relations=False)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found"
        )

    # 验证用户权限
    has_access = await project_crud.check_project_access(
        db, task.project_id, current_user_id
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task",
        )

    # 构建查询
    stmt = (
        select(
            SocialPost.id,
            SocialPost.post_id_on_platform,
            SocialPost.title,
            SocialPost.content,
            SocialPost.author_name,
            SocialPost.likes_count,
            SocialPost.comments_count,
            SocialPost.shares_count,
            SocialPost.collected_count,
            SocialPost.views_count,
            SocialPost.danmaku_count,
            SocialPost.published_at,
            SocialPost.url,
            PostAnalysis.spam_score,
            PostAnalysis.value_score,
            PostAnalysis.relevance_score,
            PostAnalysis.sentiment,
            PostAnalysis.cii,
            PostAnalysis.post_deep_result,
            PostAnalysis.comment_deep_result,
            PostAnalysis.analyzed_at,
            PostAnalysis.analysis_model,
        )
        .join(
            PostAnalysis,
            PostAnalysis.post_id == SocialPost.id,
            isouter=not filter_analyzed,
        )
        .where(SocialPost.task_id == task_id)
        .where(SocialPost.is_deleted.is_(False))
    )

    if filter_analyzed:
        stmt = stmt.where(PostAnalysis.spam_score.isnot(None))

    # 搜索条件
    if post_ids:
        # 按帖子ID列表筛选（优先级最高）
        stmt = stmt.where(SocialPost.id.in_(post_ids))
    elif search_id is not None:
        stmt = stmt.where(PostAnalysis.id == search_id)
    elif search_query:
        search_pattern = f"%{search_query}%"
        stmt = stmt.where(
            or_(
                SocialPost.title.ilike(search_pattern),
                SocialPost.content.ilike(search_pattern),
            )
        )

    # 计算总数
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # 分页查询
    stmt = stmt.order_by(SocialPost.published_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(stmt)
    rows = result.all()

    # 转换为字典列表
    items = []
    for row in rows:
        items.append(
            {
                "post_id": row.id,
                "post_id_on_platform": row.post_id_on_platform,
                "title": row.title,
                "content": row.content,
                "author_name": row.author_name,
                "likes_count": row.likes_count,
                "comments_count": row.comments_count,
                "shares_count": row.shares_count,
                "collected_count": row.collected_count,
                "views_count": row.views_count,
                "danmaku_count": row.danmaku_count,
                "published_at": row.published_at,
                "url": row.url,
                "spam_score": row.spam_score,
                "value_score": row.value_score,
                "relevance_score": row.relevance_score,
                "sentiment": row.sentiment,
                "cii": row.cii,
                "post_deep_result": row.post_deep_result,
                "comment_deep_result": row.comment_deep_result,
                "analyzed_at": row.analyzed_at,
                "analysis_model": row.analysis_model,
            }
        )

    return items, total


async def preview_deep_analysis_candidates(
    db: AsyncSession,
    task_id: int,
    current_user_id: int,
    spam_max: float | None = None,
    value_min: float | None = None,
    relevance_min: float | None = None,
) -> dict[str, Any]:
    """
    基于初筛分阈值计算可进行原文/评论深度分析的帖子列表

    Returns:
        dict 包含总帖数、已初筛数、符合阈值数、已完成深度/评论分析数、候选ID列表
    """
    from src.social_media.tasks import crud as task_crud
    from src.social_media.projects import crud as project_crud
    from src.social_media.tasks.models import SocialPost

    # 验证任务与权限
    task = await task_crud.get_task_by_id(db, task_id, load_relations=False)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found"
        )
    has_access = await project_crud.check_project_access(
        db, task.project_id, current_user_id
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task",
        )

    # 查询所有帖子与分析结果
    stmt = (
        select(
            SocialPost.id,
            SocialPost.comments_count,
            PostAnalysis.spam_score,
            PostAnalysis.value_score,
            PostAnalysis.relevance_score,
            PostAnalysis.post_deep_result,
            PostAnalysis.comment_deep_result,
        )
        .join(PostAnalysis, PostAnalysis.post_id == SocialPost.id, isouter=True)
        .where(SocialPost.task_id == task_id)
        .where(SocialPost.is_deleted.is_(False))
    )
    result = await db.execute(stmt)
    rows = result.all()

    total_posts = len(rows)
    screened_count = 0
    qualified_count = 0  # 符合阈值条件的已初筛帖子总数（不管是否已深度分析）
    matched_ids: list[int] = []  # 符合条件且待深度分析的帖子
    deep_done = 0
    comment_done = 0
    comment_candidate_ids: list[int] = []

    # 阈值默认值：广告≤7 价值≥4 相关≥4（中等宽松）
    spam_threshold = spam_max if spam_max is not None else 7
    value_threshold = value_min if value_min is not None else 4
    relevance_threshold = relevance_min if relevance_min is not None else 4

    for row in rows:
        post_id = row.id
        spam = row.spam_score
        val = row.value_score
        rel = row.relevance_score
        post_deep = row.post_deep_result
        comment_deep = row.comment_deep_result

        # 统计初筛
        if spam is not None and val is not None and rel is not None:
            screened_count += 1
            # 符合阈值条件
            if (
                spam <= spam_threshold
                and val >= value_threshold
                and rel >= relevance_threshold
            ):
                qualified_count += 1
                # 尚未深度分析的才加入候选列表
                if post_deep is None:
                    matched_ids.append(post_id)

        # 统计已完成
        if post_deep is not None:
            deep_done += 1
        if comment_deep is not None:
            comment_done += 1

        # 评论深度候选：已有原文深度、有评论、尚未评论深度
        if (
            post_deep is not None
            and comment_deep is None
            and (row.comments_count or 0) > 0
        ):
            comment_candidate_ids.append(post_id)

    return {
        "total_posts": total_posts,
        "screened_count": screened_count,
        "qualified_count": qualified_count,  # 符合条件的总数
        "matched_count": len(matched_ids),  # 待深度分析数
        "deep_done": deep_done,
        "comment_done": comment_done,
        "deep_candidate_ids": matched_ids,
        "comment_candidate_ids": comment_candidate_ids,
    }


# ==================== Delete Analysis Results ====================


async def delete_task_analyses(
    db: AsyncSession,
    task_id: int,
    current_user_id: int,
) -> dict[str, Any]:
    """删除任务下所有帖子的分析结果，方便重新分析

    Args:
        task_id: 任务ID
        current_user_id: 当前用户ID

    Returns:
        删除结果，包含删除的记录数
    """
    from src.social_media.tasks import crud as task_crud
    from src.social_media.projects import crud as project_crud
    from sqlalchemy import delete

    # 验证任务是否存在
    task = await task_crud.get_task_by_id(db, task_id, load_relations=False)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found"
        )

    # 验证用户权限
    has_access = await project_crud.check_project_access(
        db, task.project_id, current_user_id
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task",
        )

    # 查询要删除的记录数
    count_stmt = select(func.count()).where(PostAnalysis.task_id == task_id)
    count_result = await db.execute(count_stmt)
    deleted_count = count_result.scalar() or 0

    if deleted_count == 0:
        return {
            "success": True,
            "deleted_count": 0,
            "message": "没有需要删除的分析结果",
        }

    # 删除所有分析结果
    delete_stmt = delete(PostAnalysis).where(PostAnalysis.task_id == task_id)
    await db.execute(delete_stmt)
    await db.commit()

    return {
        "success": True,
        "deleted_count": deleted_count,
        "message": f"已删除 {deleted_count} 条分析结果",
    }


# ==================== Statistics Service ====================


async def get_global_stats(
    db: AsyncSession, current_user_id: int
) -> AnalysisStatsResponse:
    """获取全局分析统计"""
    # 查询所有分析任务
    stmt = select(AnalysisJob)
    result = await db.execute(stmt)
    all_jobs = result.scalars().all()

    total_jobs = len(all_jobs)
    completed_jobs = sum(1 for j in all_jobs if j.status == "completed")
    failed_jobs = sum(1 for j in all_jobs if j.status == "failed")
    pending_jobs = sum(1 for j in all_jobs if j.status == "pending")
    processing_jobs = sum(1 for j in all_jobs if j.status == "processing")

    total_cost = 0.0
    total_tokens = 0
    total_time = 0

    for j in all_jobs:
        if j.token_usage:
            total_cost += j.token_usage.get("summary", {}).get("total_cost_cny", 0.0)
            total_tokens += j.token_usage.get("summary", {}).get("total_tokens", 0)
        if j.processing_time:
            total_time += j.processing_time

    avg_processing_time = total_time / total_jobs if total_jobs > 0 else 0

    return AnalysisStatsResponse(
        total_jobs=total_jobs,
        completed_jobs=completed_jobs,
        failed_jobs=failed_jobs,
        pending_jobs=pending_jobs,
        processing_jobs=processing_jobs,
        total_cost_cny=total_cost,
        total_tokens=total_tokens,
        avg_processing_time=avg_processing_time,
    )


# ==================== Task Analysis Result ====================


async def run_task_aggregation(
    db: AsyncSession, task_id: int, current_user_id: int
) -> RunAnalysisResponse:
    """运行聚合分析，生成任务级分析报告（异步 Celery 任务）

    调用 Aggregator 计算聚合数据（NSR、SERP、实体、观点等），
    结果存储在 DataTask.analysis_result 中。

    与初筛/深度分析一致，采用 Celery 异步执行，避免阻塞 API。

    注意：聚合分析本身不涉及 LLM API 调用，因此不创建 AnalysisJob 记录。
    但会预先创建实体归一化和观点归一化的 AnalysisJob（状态为 pending），
    以便前端可以立即检测到任务在运行。

    Args:
        task_id: 任务ID
        current_user_id: 当前用户ID

    Returns:
        RunAnalysisResponse: 包含 celery_task_id
    """
    from src.social_media.tasks import crud as task_crud
    from src.social_media.projects import crud as project_crud
    from .celery_tasks.aggregation_tasks import run_aggregation_task

    # 验证任务是否存在
    task = await task_crud.get_task_by_id(db, task_id, load_relations=False)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found"
        )

    # 验证用户权限
    has_access = await project_crud.check_project_access(
        db, task.project_id, current_user_id
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task",
        )

    # 检查是否有已分析的帖子
    stmt = (
        select(func.count())
        .where(PostAnalysis.task_id == task_id)
        .where(PostAnalysis.spam_score.isnot(None))
    )
    result = await db.execute(stmt)
    analyzed_count = result.scalar() or 0

    if analyzed_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有已分析的帖子，请先运行初筛或深度分析",
        )

    # 预先创建实体归一化和观点归一化的 AnalysisJob（状态为 pending）
    # 这样前端可以立即检测到任务在运行，不需要等待 Celery 任务内部创建
    entity_job = await create_analysis_job_async(
        db=db,
        project_id=task.project_id,
        task_id=task_id,
        user_id=current_user_id,
        analysis_type="entity_normalization",
        source_count=analyzed_count,
    )
    opinion_job = await create_analysis_job_async(
        db=db,
        project_id=task.project_id,
        task_id=task_id,
        user_id=current_user_id,
        analysis_type="opinion_normalization",
        source_count=analyzed_count,
    )

    # 启动 Celery 任务，传递预创建的 job_id
    celery_result = run_aggregation_task.delay(
        task_id=task_id,
        project_id=task.project_id,
        user_id=current_user_id,
        entity_job_id=entity_job.id,
        opinion_job_id=opinion_job.id,
    )

    return RunAnalysisResponse(
        celery_task_id=celery_result.id,
        job_id=entity_job.id,  # 返回实体归一化的 job_id 用于跟踪
        status="pending",
        message=f"聚合分析任务已启动，将分析 {analyzed_count} 条数据",
    )


async def get_task_aggregation(
    db: AsyncSession, task_id: int, current_user_id: int
) -> dict[str, Any] | None:
    """获取任务级聚合分析结果

    从 DataTask.analysis_result 中获取聚合数据。

    Args:
        task_id: 任务ID
        current_user_id: 当前用户ID

    Returns:
        聚合分析结果，如果没有则返回 None
    """
    from src.social_media.tasks import crud as task_crud
    from src.social_media.tasks.models import DataTask
    from src.social_media.projects import crud as project_crud

    # 验证任务是否存在
    task = await task_crud.get_task_by_id(db, task_id, load_relations=False)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found"
        )

    # 验证用户权限
    has_access = await project_crud.check_project_access(
        db, task.project_id, current_user_id
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task",
        )

    # 从 DataTask 获取 analysis_result
    stmt = select(DataTask).where(DataTask.id == task_id)
    result = await db.execute(stmt)
    data_task = result.scalar_one_or_none()

    if not data_task or not data_task.analysis_result:
        return None

    return {
        "task_id": task_id,
        "analyzed_at": data_task.analysis_result_at.isoformat()
        if data_task.analysis_result_at
        else None,
        "result": data_task.analysis_result,
    }
