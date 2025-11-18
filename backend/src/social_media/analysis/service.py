"""分析模块业务逻辑层"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from fastapi import HTTPException, status

from .models import (
    PostAnalysis,
    CommentAnalysis,
    TaskAnalysisResult,
    ProjectAnalysisResult
)
from .schemas import (
    RunScreeningRequest,
    RunDeepAnalysisRequest,
    RunClusteringRequest,
    RunCompetitiveRequest,
    RunAnalysisResponse,
    AnalysisProgressResponse,
    AnalysisStatsResponse,
    TaskAnalysisStatsResponse,
    ProjectAnalysisStatsResponse,
)


# ==================== Task Analysis Service ====================

async def run_post_screening(
    db: AsyncSession,
    request: RunScreeningRequest,
    current_user_id: int
) -> RunAnalysisResponse:
    """运行帖子AI初筛分析"""
    from src.social_media.tasks import crud as task_crud
    from src.social_media.projects import crud as project_crud
    from .tasks.screening_tasks import run_post_screening as celery_task

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
        # 获取任务下所有帖子ID
        from src.social_media.tasks.models import SocialPost
        stmt = select(SocialPost.id).where(SocialPost.task_id == request.task_id)
        result = await db.execute(stmt)
        post_ids = [row[0] for row in result.fetchall()]

    if not post_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No posts to analyze"
        )

    # 创建分析结果记录
    analysis_result = TaskAnalysisResult(
        task_id=request.task_id,
        analysis_type="screening_posts",
        celery_task_id="",  # 将在Celery任务启动后更新
        status="pending",
        source_count=len(post_ids),
    )
    db.add(analysis_result)
    await db.commit()
    await db.refresh(analysis_result)

    # 获取项目关键词
    project = await project_crud.get_project_by_id(db, task.project_id, load_relations=False)
    project_keywords = task.keywords or ""

    # 启动Celery任务
    celery_result = celery_task.delay(
        result_id=analysis_result.id,
        task_id=request.task_id,
        post_ids=post_ids,
        project_keywords=project_keywords,
    )

    # 更新celery_task_id
    analysis_result.celery_task_id = celery_result.id
    await db.commit()

    return RunAnalysisResponse(
        celery_task_id=celery_result.id,
        result_id=analysis_result.id,
        status="pending",
        message=f"帖子初筛任务已启动，共{len(post_ids)}条数据"
    )


async def run_comment_screening(
    db: AsyncSession,
    request: RunScreeningRequest,
    current_user_id: int
) -> RunAnalysisResponse:
    """运行评论AI初筛分析"""
    from src.social_media.tasks import crud as task_crud
    from src.social_media.projects import crud as project_crud
    from .tasks.screening_tasks import run_comment_screening as celery_task

    # 验证任务和权限（与帖子初筛类似）
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

    # 获取要分析的评论ID列表
    comment_ids = request.comment_ids or []

    if request.analyze_all or not comment_ids:
        from src.social_media.tasks.models import SocialComment
        stmt = select(SocialComment.id).where(SocialComment.task_id == request.task_id)
        result = await db.execute(stmt)
        comment_ids = [row[0] for row in result.fetchall()]

    if not comment_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No comments to analyze"
        )

    # 创建分析结果记录
    analysis_result = TaskAnalysisResult(
        task_id=request.task_id,
        analysis_type="screening_comments",
        celery_task_id="",
        status="pending",
        source_count=len(comment_ids),
    )
    db.add(analysis_result)
    await db.commit()
    await db.refresh(analysis_result)

    # 获取项目关键词
    project = await project_crud.get_project_by_id(db, task.project_id, load_relations=False)
    project_keywords = task.keywords or ""

    # 启动Celery任务
    celery_result = celery_task.delay(
        result_id=analysis_result.id,
        task_id=request.task_id,
        comment_ids=comment_ids,
        project_keywords=project_keywords,
    )

    analysis_result.celery_task_id = celery_result.id
    await db.commit()

    return RunAnalysisResponse(
        celery_task_id=celery_result.id,
        result_id=analysis_result.id,
        status="pending",
        message=f"评论初筛任务已启动，共{len(comment_ids)}条数据"
    )


async def get_task_analysis_results(
    db: AsyncSession,
    task_id: int,
    current_user_id: int,
    page: int = 1,
    page_size: int = 20
) -> tuple[List[TaskAnalysisResult], int]:
    """获取任务的分析结果列表"""
    from src.social_media.tasks import crud as task_crud
    from src.social_media.projects import crud as project_crud

    # 验证任务和权限
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

    # 查询分析结果
    offset = (page - 1) * page_size

    stmt = (
        select(TaskAnalysisResult)
        .where(TaskAnalysisResult.task_id == task_id)
        .order_by(TaskAnalysisResult.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    # 查询总数
    count_stmt = select(func.count()).select_from(TaskAnalysisResult).where(
        TaskAnalysisResult.task_id == task_id
    )
    total = await db.scalar(count_stmt)

    return list(items), total or 0


async def get_task_analysis_result(
    db: AsyncSession,
    result_id: int,
    current_user_id: int
) -> Optional[TaskAnalysisResult]:
    """获取单个任务分析结果"""
    from src.social_media.tasks import crud as task_crud
    from src.social_media.projects import crud as project_crud

    # 查询分析结果
    stmt = select(TaskAnalysisResult).where(TaskAnalysisResult.id == result_id)
    result = await db.execute(stmt)
    analysis_result = result.scalar_one_or_none()

    if not analysis_result:
        return None

    # 验证权限
    task = await task_crud.get_task_by_id(db, analysis_result.task_id, load_relations=False)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Related task not found"
        )

    has_access = await project_crud.check_project_access(db, task.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this analysis result"
        )

    return analysis_result


async def get_analysis_progress(
    db: AsyncSession,
    result_id: int,
    current_user_id: int
) -> AnalysisProgressResponse:
    """获取分析任务进度"""
    analysis_result = await get_task_analysis_result(db, result_id, current_user_id)

    if not analysis_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis result {result_id} not found"
        )

    # 计算进度
    progress = 0.0
    if analysis_result.source_count > 0:
        progress = (analysis_result.analyzed_count / analysis_result.source_count) * 100

    # 估算剩余时间
    estimated_time_remaining = None
    if analysis_result.processing_time and analysis_result.analyzed_count > 0:
        avg_time_per_item = analysis_result.processing_time / analysis_result.analyzed_count
        remaining_items = analysis_result.source_count - analysis_result.analyzed_count
        estimated_time_remaining = int(avg_time_per_item * remaining_items)

    # 获取当前Token和成本
    current_tokens = 0
    current_cost = 0.0
    if analysis_result.token_usage:
        current_tokens = analysis_result.token_usage.get("summary", {}).get("total_tokens", 0)
        current_cost = analysis_result.token_usage.get("summary", {}).get("total_cost_cny", 0.0)

    return AnalysisProgressResponse(
        result_id=result_id,
        status=analysis_result.status,
        progress=progress,
        analyzed_count=analysis_result.analyzed_count,
        total_count=analysis_result.source_count,
        estimated_time_remaining=estimated_time_remaining,
        current_cost=current_cost,
        current_tokens=current_tokens,
    )


async def cancel_analysis(
    db: AsyncSession,
    result_id: int,
    current_user_id: int
) -> bool:
    """取消分析任务"""
    from celery import current_app as celery_app

    analysis_result = await get_task_analysis_result(db, result_id, current_user_id)

    if not analysis_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis result {result_id} not found"
        )

    if analysis_result.status not in ("pending", "processing"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel analysis in status: {analysis_result.status}"
        )

    # 取消Celery任务
    celery_app.control.revoke(analysis_result.celery_task_id, terminate=True)

    # 更新状态
    analysis_result.status = "failed"
    analysis_result.error_message = "Cancelled by user"
    analysis_result.completed_at = datetime.now(timezone.utc)
    await db.commit()

    return True


async def delete_analysis_result(
    db: AsyncSession,
    result_id: int,
    current_user_id: int
) -> bool:
    """删除分析结果"""
    analysis_result = await get_task_analysis_result(db, result_id, current_user_id)

    if not analysis_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis result {result_id} not found"
        )

    await db.delete(analysis_result)
    await db.commit()

    return True


# ==================== Statistics Service ====================

async def get_global_stats(
    db: AsyncSession,
    current_user_id: int
) -> AnalysisStatsResponse:
    """获取全局分析统计"""
    # 查询用户可访问的所有任务分析结果
    # 这里简化处理，实际应该关联项目权限
    stmt = select(TaskAnalysisResult)
    result = await db.execute(stmt)
    all_results = result.scalars().all()

    total_tasks = len(all_results)
    completed_tasks = sum(1 for r in all_results if r.status == "completed")
    failed_tasks = sum(1 for r in all_results if r.status == "failed")
    pending_tasks = sum(1 for r in all_results if r.status == "pending")
    processing_tasks = sum(1 for r in all_results if r.status == "processing")

    total_cost = 0.0
    total_tokens = 0
    total_time = 0

    for r in all_results:
        if r.token_usage:
            total_cost += r.token_usage.get("summary", {}).get("total_cost_cny", 0.0)
            total_tokens += r.token_usage.get("summary", {}).get("total_tokens", 0)
        if r.processing_time:
            total_time += r.processing_time

    avg_processing_time = total_time / total_tasks if total_tasks > 0 else 0

    return AnalysisStatsResponse(
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        failed_tasks=failed_tasks,
        pending_tasks=pending_tasks,
        processing_tasks=processing_tasks,
        total_cost_cny=total_cost,
        total_tokens=total_tokens,
        avg_processing_time=avg_processing_time,
    )


async def get_post_analysis(
    db: AsyncSession,
    post_id: int,
    current_user_id: int
) -> Optional[PostAnalysis]:
    """获取帖子的分析结果"""
    stmt = select(PostAnalysis).where(PostAnalysis.post_id == post_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_comment_analysis(
    db: AsyncSession,
    comment_id: int,
    current_user_id: int
) -> Optional[CommentAnalysis]:
    """获取评论的分析结果"""
    stmt = select(CommentAnalysis).where(CommentAnalysis.comment_id == comment_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
