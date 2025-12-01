"""分析模块业务逻辑层

使用统一的 AnalysisJob 模型，通过 task_id 是否为空区分任务级/项目级分析。
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from .models import PostAnalysis, AnalysisJob
from .schemas import (
    RunScreeningRequest,
    RunDeepAnalysisRequest,
    RunAnalysisResponse,
    AnalysisProgressResponse,
    AnalysisStatsResponse,
)


# ==================== Analysis Job CRUD ====================

async def get_analysis_jobs(
    db: AsyncSession,
    current_user_id: int,
    page: int = 1,
    page_size: int = 20,
    project_id: int | None = None,
    task_id: int | None = None,
    analysis_type: str | None = None,
    status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[List[Dict[str, Any]], int]:
    """获取全局分析任务列表（带筛选和关联信息）"""
    from src.social_media.projects.models import SocialProject
    from src.social_media.tasks.models import DataTask
    from src.auth.models import User

    # 构建基础查询
    stmt = (
        select(
            AnalysisJob,
            SocialProject.name.label('project_name'),
            DataTask.name.label('task_name'),
            User.username.label('user_name'),
        )
        .join(SocialProject, AnalysisJob.project_id == SocialProject.id)
        .join(DataTask, AnalysisJob.task_id == DataTask.id, isouter=True)
        .join(User, AnalysisJob.user_id == User.id)
    )

    # 筛选条件
    conditions = []

    if project_id is not None:
        conditions.append(AnalysisJob.project_id == project_id)

    if task_id is not None:
        conditions.append(AnalysisJob.task_id == task_id)

    if analysis_type:
        conditions.append(AnalysisJob.analysis_type == analysis_type)

    if status:
        conditions.append(AnalysisJob.status == status)

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            conditions.append(AnalysisJob.created_at >= start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            # 结束日期包含当天
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            conditions.append(AnalysisJob.created_at <= end_dt)
        except ValueError:
            pass

    if conditions:
        stmt = stmt.where(and_(*conditions))

    # 计算总数
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0

    # 分页查询
    stmt = stmt.order_by(AnalysisJob.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(stmt)
    rows = result.all()

    # 转换为字典列表（包含关联名称）
    items = []
    for row in rows:
        job = row.AnalysisJob
        item = {
            "id": job.id,
            "project_id": job.project_id,
            "task_id": job.task_id,
            "user_id": job.user_id,
            "analysis_type": job.analysis_type,
            "celery_task_id": job.celery_task_id,
            "status": job.status,
            "analysis_config": job.analysis_config,
            "source_task_ids": job.source_task_ids,
            "source_count": job.source_count,
            "analyzed_count": job.analyzed_count,
            "failed_count": job.failed_count,
            "result_data": job.result_data,
            "analysis_summary": job.analysis_summary,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "processing_time": job.processing_time,
            "token_usage": job.token_usage,
            "error_message": job.error_message,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            # 关联名称
            "project_name": row.project_name,
            "task_name": row.task_name,
            "user_name": row.user_name,
        }
        items.append(item)

    return items, total


async def get_analysis_job(
    db: AsyncSession,
    job_id: int,
    current_user_id: int
) -> Optional[Dict[str, Any]]:
    """获取单个分析任务详情（带关联信息）"""
    from src.social_media.projects.models import SocialProject
    from src.social_media.tasks.models import DataTask
    from src.auth.models import User
    from src.social_media.projects import crud as project_crud

    # 查询分析任务及关联信息
    stmt = (
        select(
            AnalysisJob,
            SocialProject.name.label('project_name'),
            DataTask.name.label('task_name'),
            User.username.label('user_name'),
        )
        .join(SocialProject, AnalysisJob.project_id == SocialProject.id)
        .join(DataTask, AnalysisJob.task_id == DataTask.id, isouter=True)
        .join(User, AnalysisJob.user_id == User.id)
        .where(AnalysisJob.id == job_id)
    )

    result = await db.execute(stmt)
    row = result.first()

    if not row:
        return None

    job = row.AnalysisJob

    # 验证用户权限
    has_access = await project_crud.check_project_access(db, job.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this analysis job"
        )

    return {
        "id": job.id,
        "project_id": job.project_id,
        "task_id": job.task_id,
        "user_id": job.user_id,
        "analysis_type": job.analysis_type,
        "celery_task_id": job.celery_task_id,
        "status": job.status,
        "analysis_config": job.analysis_config,
        "source_task_ids": job.source_task_ids,
        "source_count": job.source_count,
        "analyzed_count": job.analyzed_count,
        "failed_count": job.failed_count,
        "result_data": job.result_data,
        "analysis_summary": job.analysis_summary,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "processing_time": job.processing_time,
        "token_usage": job.token_usage,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "project_name": row.project_name,
        "task_name": row.task_name,
        "user_name": row.user_name,
    }


async def get_analysis_progress(
    db: AsyncSession,
    job_id: int,
    current_user_id: int
) -> AnalysisProgressResponse:
    """获取分析任务进度"""
    from src.social_media.projects import crud as project_crud

    # 查询分析任务
    stmt = select(AnalysisJob).where(AnalysisJob.id == job_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis job {job_id} not found"
        )

    # 验证权限
    has_access = await project_crud.check_project_access(db, job.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this analysis job"
        )

    # 计算进度
    progress = 0.0
    if job.source_count > 0:
        progress = (job.analyzed_count / job.source_count) * 100

    # 估算剩余时间
    estimated_time_remaining = None
    if job.processing_time and job.analyzed_count > 0:
        avg_time_per_item = job.processing_time / job.analyzed_count
        remaining_items = job.source_count - job.analyzed_count
        estimated_time_remaining = int(avg_time_per_item * remaining_items)

    # 获取当前Token和成本
    current_tokens = 0
    current_cost = 0.0
    if job.token_usage:
        current_tokens = job.token_usage.get("summary", {}).get("total_tokens", 0)
        current_cost = job.token_usage.get("summary", {}).get("total_cost_cny", 0.0)

    return AnalysisProgressResponse(
        job_id=job_id,
        status=job.status,
        progress=progress,
        analyzed_count=job.analyzed_count,
        total_count=job.source_count,
        estimated_time_remaining=estimated_time_remaining,
        current_cost=current_cost,
        current_tokens=current_tokens,
    )


async def cancel_analysis_job(
    db: AsyncSession,
    job_id: int,
    current_user_id: int
) -> bool:
    """取消分析任务"""
    from celery import current_app as celery_app
    from src.social_media.projects import crud as project_crud

    # 查询分析任务
    stmt = select(AnalysisJob).where(AnalysisJob.id == job_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis job {job_id} not found"
        )

    # 验证权限
    has_access = await project_crud.check_project_access(db, job.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this analysis job"
        )

    if job.status not in ("pending", "processing"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel analysis in status: {job.status}"
        )

    # 取消Celery任务
    celery_app.control.revoke(job.celery_task_id, terminate=True)

    # 更新状态
    job.status = "failed"
    job.error_message = "Cancelled by user"
    job.completed_at = datetime.now(timezone.utc)
    await db.commit()

    return True


async def delete_analysis_job(
    db: AsyncSession,
    job_id: int,
    current_user_id: int
) -> bool:
    """删除分析任务"""
    from src.social_media.projects import crud as project_crud

    # 查询分析任务
    stmt = select(AnalysisJob).where(AnalysisJob.id == job_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis job {job_id} not found"
        )

    # 验证权限
    has_access = await project_crud.check_project_access(db, job.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this analysis job"
        )

    await db.delete(job)
    await db.commit()

    return True


# ==================== Task-Level Analysis ====================

async def run_post_screening(
    db: AsyncSession,
    request: RunScreeningRequest,
    current_user_id: int
) -> RunAnalysisResponse:
    """运行帖子AI初筛分析"""
    from src.social_media.tasks import crud as task_crud
    from src.social_media.projects import crud as project_crud
    from .celery_tasks.screening_tasks import screening_coordinator

    # 验证任务是否存在
    task = await task_crud.get_task_by_id(db, request.task_id, load_relations=False)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {request.task_id} not found"
        )

    # 验证用户权限
    has_access = await project_crud.check_project_access(db, task.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task"
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
            .where(SocialPost.is_deleted == False)
            .where(PostAnalysis.spam_score.is_(None))  # 只选择尚未初筛的
        )
        result = await db.execute(stmt)
        post_ids = [row[0] for row in result.fetchall()]

    if not post_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有需要初筛的帖子（所有帖子已完成初筛）"
        )

    # 创建分析任务记录（使用新的 AnalysisJob 模型）
    analysis_job = AnalysisJob(
        project_id=task.project_id,
        task_id=request.task_id,
        user_id=current_user_id,
        analysis_type="screening_posts",
        celery_task_id="",  # 将在Celery任务启动后更新
        status="pending",
        source_count=len(post_ids),
    )
    db.add(analysis_job)
    await db.commit()
    await db.refresh(analysis_job)

    # 获取项目关键词
    project_keywords = task.keywords or ""

    # 启动Celery任务
    celery_result = screening_coordinator.delay(
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
        message=f"帖子初筛任务已启动，共{len(post_ids)}条数据"
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
    from .celery_tasks.deep_analysis_tasks import post_deep_coordinator

    # 验证任务和权限
    task = await task_crud.get_task_by_id(db, request.task_id, load_relations=False)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {request.task_id} not found"
        )

    has_access = await project_crud.check_project_access(db, task.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task"
        )

    # 获取要分析的帖子ID列表
    post_ids = request.post_ids or []

    if not post_ids:
        # 基于阈值筛选候选帖子
        preview = await preview_deep_analysis_candidates(
            db, request.task_id, current_user_id,
            spam_max=spam_max, value_min=value_min, relevance_min=relevance_min
        )
        post_ids = preview["deep_candidate_ids"]

    if not post_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有符合条件的帖子需要原文深度分析（请先完成初筛或调整阈值）"
        )

    # 创建分析任务记录
    analysis_job = AnalysisJob(
        project_id=task.project_id,
        task_id=request.task_id,
        user_id=current_user_id,
        analysis_type="deep_posts",
        celery_task_id="",
        status="pending",
        source_count=len(post_ids),
        analysis_config={
            "spam_max": spam_max,
            "value_min": value_min,
            "relevance_min": relevance_min,
        } if any([spam_max, value_min, relevance_min]) else None,
    )
    db.add(analysis_job)
    await db.commit()
    await db.refresh(analysis_job)

    # 启动Celery任务
    celery_result = post_deep_coordinator.delay(
        result_id=analysis_job.id,
        task_id=request.task_id,
        post_ids=post_ids,
        analysis_focus=request.analysis_focus
    )

    # 更新celery_task_id
    analysis_job.celery_task_id = celery_result.id
    await db.commit()

    return RunAnalysisResponse(
        celery_task_id=celery_result.id,
        job_id=analysis_job.id,
        status="pending",
        message=f"帖子深度分析任务已启动，共{len(post_ids)}条数据"
    )


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
    from .celery_tasks.deep_analysis_tasks import comment_deep_coordinator

    # 验证任务和权限
    task = await task_crud.get_task_by_id(db, request.task_id, load_relations=False)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {request.task_id} not found"
        )

    has_access = await project_crud.check_project_access(db, task.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task"
        )

    # 获取要分析的帖子ID列表（因为评论分析是基于帖子的）
    post_ids = request.post_ids or []

    if not post_ids:
        # 基于阈值筛选候选帖子
        preview = await preview_deep_analysis_candidates(
            db, request.task_id, current_user_id,
            spam_max=spam_max, value_min=value_min, relevance_min=relevance_min
        )
        post_ids = preview["comment_candidate_ids"]

    if not post_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有符合条件的帖子需要评论深度分析（需先完成原文深度分析且有评论）"
        )

    # 创建分析任务记录
    analysis_job = AnalysisJob(
        project_id=task.project_id,
        task_id=request.task_id,
        user_id=current_user_id,
        analysis_type="deep_comments",
        celery_task_id="",
        status="pending",
        source_count=len(post_ids),
        analysis_config={
            "spam_max": spam_max,
            "value_min": value_min,
            "relevance_min": relevance_min,
        } if any([spam_max, value_min, relevance_min]) else None,
    )
    db.add(analysis_job)
    await db.commit()
    await db.refresh(analysis_job)

    # 启动Celery任务
    celery_result = comment_deep_coordinator.delay(
        result_id=analysis_job.id,
        task_id=request.task_id,
        post_ids=post_ids,
        analysis_focus=request.analysis_focus
    )

    # 更新celery_task_id
    analysis_job.celery_task_id = celery_result.id
    await db.commit()

    return RunAnalysisResponse(
        celery_task_id=celery_result.id,
        job_id=analysis_job.id,
        status="pending",
        message=f"评论深度分析任务已启动，将分析{len(post_ids)}个帖子的评论"
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )

    # 验证用户权限
    has_access = await project_crud.check_project_access(db, task.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task"
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
        .join(PostAnalysis, PostAnalysis.post_id == SocialPost.id, isouter=not filter_analyzed)
        .where(SocialPost.task_id == task_id)
        .where(SocialPost.is_deleted == False)
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
                SocialPost.content.ilike(search_pattern)
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
        items.append({
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
        })

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
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    has_access = await project_crud.check_project_access(db, task.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task"
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
        .where(SocialPost.is_deleted == False)
    )
    result = await db.execute(stmt)
    rows = result.all()

    total_posts = len(rows)
    screened_count = 0
    matched_ids: list[int] = []
    deep_done = 0
    comment_done = 0
    comment_candidate_ids: list[int] = []

    # 阈值默认
    spam_threshold = spam_max if spam_max is not None else 5
    value_threshold = value_min if value_min is not None else 6
    relevance_threshold = relevance_min if relevance_min is not None else 6

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
            if (
                spam <= spam_threshold
                and val >= value_threshold
                and rel >= relevance_threshold
                and post_deep is None
            ):
                matched_ids.append(post_id)

        # 统计已完成
        if post_deep is not None:
            deep_done += 1
        if comment_deep is not None:
            comment_done += 1

        # 评论深度候选：已有原文深度、有评论、尚未评论深度
        if post_deep is not None and comment_deep is None and (row.comments_count or 0) > 0:
            comment_candidate_ids.append(post_id)

    return {
        "total_posts": total_posts,
        "screened_count": screened_count,
        "matched_count": len(matched_ids),
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )

    # 验证用户权限
    has_access = await project_crud.check_project_access(db, task.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task"
        )

    # 查询要删除的记录数
    count_stmt = select(func.count()).where(PostAnalysis.task_id == task_id)
    count_result = await db.execute(count_stmt)
    deleted_count = count_result.scalar() or 0

    if deleted_count == 0:
        return {
            "success": True,
            "deleted_count": 0,
            "message": "没有需要删除的分析结果"
        }

    # 删除所有分析结果
    delete_stmt = delete(PostAnalysis).where(PostAnalysis.task_id == task_id)
    await db.execute(delete_stmt)
    await db.commit()

    return {
        "success": True,
        "deleted_count": deleted_count,
        "message": f"已删除 {deleted_count} 条分析结果"
    }


# ==================== Statistics Service ====================

async def get_global_stats(
    db: AsyncSession,
    current_user_id: int
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
    db: AsyncSession,
    task_id: int,
    current_user_id: int
) -> dict[str, Any]:
    """运行聚合分析，生成任务级分析报告

    调用 Aggregator 计算聚合数据（NSR、SERP、实体、KANO等），
    结果存储在 DataTask.analysis_result 中。

    Args:
        task_id: 任务ID
        current_user_id: 当前用户ID

    Returns:
        聚合分析结果
    """
    from src.social_media.tasks import crud as task_crud
    from src.social_media.tasks.models import DataTask
    from src.social_media.projects import crud as project_crud
    from .celery_tasks.aggregator import aggregate_task_analysis
    from src.database import SyncSessionLocal

    # 验证任务是否存在
    task = await task_crud.get_task_by_id(db, task_id, load_relations=False)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )

    # 验证用户权限
    has_access = await project_crud.check_project_access(db, task.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task"
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
            detail="没有已分析的帖子，请先运行初筛或深度分析"
        )

    # 使用同步 session 调用 Aggregator（因为 Aggregator 是同步的）
    sync_db = SyncSessionLocal()
    try:
        # 运行聚合（函数内部会读取关键词）
        aggregation_result = aggregate_task_analysis(
            db=sync_db,
            task_id=task_id,
        )

        # 更新 DataTask 的 analysis_result
        now = datetime.now(timezone.utc)
        update_stmt = (
            select(DataTask)
            .where(DataTask.id == task_id)
        )
        task_result = sync_db.execute(update_stmt)
        data_task = task_result.scalar_one()
        data_task.analysis_result = aggregation_result
        data_task.analysis_result_at = now
        sync_db.commit()

        return {
            "success": True,
            "task_id": task_id,
            "analyzed_at": now.isoformat(),
            "result": aggregation_result,
        }
    except Exception as e:
        sync_db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"聚合分析失败: {str(e)}"
        )
    finally:
        sync_db.close()


async def get_task_aggregation(
    db: AsyncSession,
    task_id: int,
    current_user_id: int
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )

    # 验证用户权限
    has_access = await project_crud.check_project_access(db, task.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task"
        )

    # 从 DataTask 获取 analysis_result
    stmt = select(DataTask).where(DataTask.id == task_id)
    result = await db.execute(stmt)
    data_task = result.scalar_one_or_none()

    if not data_task or not data_task.analysis_result:
        return None

    return {
        "task_id": task_id,
        "analyzed_at": data_task.analysis_result_at.isoformat() if data_task.analysis_result_at else None,
        "result": data_task.analysis_result,
    }
